# Engineering Report — Native A2A (RemoteA2aAgent) vs. the Poll-Based Sender

**Project:** vibeflix-audit (ADK multi-agent licensing mesh on Agent Runtime, `pokedemo-test`)
**Date:** 2026-07-31
**Author:** weimeilin
**Status:** Decided — **b-hybrid**. Native transport confined to the future HITL hop; all
request/response hops stay on the poll-based sender.

---

## TL;DR

We evaluated replacing the hand-rolled poll-based A2A sender (`a2a_engine_send` /
`direct_engine_agent`) with ADK's native `RemoteA2aAgent`, motivated by native's built-in
human-in-the-loop (HITL) `input_required` park/resume. We shipped one necessary fix (engines now
serve an A2A card) and then proved, in the cloud, that **native cannot do request/response for
long-running hops on Agent Runtime** — not because of our code, but because of a **platform-level
streaming gap**. Decision: **b-hybrid** — keep the poll-based sender for request/response, use
native only where "pause on working" is actually desired (the HITL step).

---

## Background — why we looked at native at all

The mesh's HITL today is a custom *report-status + re-submit* pattern (`needs_user` bubbles up;
the app re-submits the audit). ADK's native HITL is cleaner: a `LongRunningFunctionTool` parks
the engine task in `input_required`, and the caller resumes the *same* task. To get that, the
caller has to be `RemoteA2aAgent` (or behave like it). So the question was: **can `RemoteA2aAgent`
be the mesh's A2A client?**

Two variants of A2A exist in the mesh:
- **Cloud** — Agent Runtime reasoning engines behind an mTLS + dual-auth gateway.
- **Local** — `docker compose` services over plain JSON-RPC.

The cloud variant is the one that matters (production is 100% cloud).

---

## What shipped (kept)

**Engines now serve an A2A discovery card.** `agent_card()` in `deploy/deploy_agents_a2a.py` was
missing `supports_authenticated_extended_card=True`, so `A2aAgent.register_operations()` never
registered the `handle_authenticated_agent_card` route and `{engine}/a2a/v1/card` returned 400.
Added the flag; redeployed all 6 engines; verified all serve the card. This was a prerequisite
for *any* native client and is worth keeping regardless of the transport decision.

`VibeflixRemoteA2aAgent` (`packages/vibeflix-common/vibeflix_common/remote_agent.py`) is retained
as a dormant library for the HITL hop. It subclasses `RemoteA2aAgent` and hides: our auth
injection, the engine card-URL normalization, the mtls-host repoint, and a **brief-override** (see
Finding 3).

---

## Investigation — findings, each verified in the cloud

### 1. Card discovery — FIXED
Root cause was the missing card flag (above), not a platform limit. The codelab
`adk-a2a-agent-runtime` uses the same `A2aAgent` template and serves a card; ours didn't only
because of the flag.

### 2. Native dispatch (fast hops) — WORKS
With the flag on, all three dispatch agents (brand_style, deal_pricing, vendor_clearance) ran via
`ctx.run_node(VibeflixRemoteA2aAgent)`, every `message:send` returned 200, and each produced a full
valid report. An earlier "dispatch 400s" worry was a **laptop-harness artifact** (empty session)
and is retracted.

### 3. Native drops the explicit brief — REAL, then FIXED
`contract_finalize` sends a special `"FINALIZE-CONTRACT: …have legal execute the contract"` brief.
Native returned `cleared` with **no contract**, while the poll sender executed `LC-215400` on
identical input. Cause: `RemoteA2aAgent._construct_message_parts_from_session` rebuilds the outgoing
message from **session events**, ignoring the brief passed to `run_node`. `direct_engine_agent`
works because it sends the explicit brief (`ctx.user_content` / last user text).
**Fix:** overrode `_construct_message_parts_from_session` in `VibeflixRemoteA2aAgent` to send the
explicit brief while keeping `context_id` for HITL continuity. Verified: the reply then reflects
the sent brief.

### 4. Brief-override exposed a deeper blocker — the POLLING gap
With the override, finalize changed `cleared` → **`pending`** (native now *attempts* the finalize)
but still executed no contract; legal never ran. Cause: `RemoteA2aAgent` hardcodes the a2a client
to `polling=False` and treats a `submitted`/`working` task as a **pause**
(`_add_mock_function_call`, `remote_a2a_agent.py:536-542`), instead of polling to terminal. Our
engines are **poll-based**: `message:send` returns immediately with a still-`working` task, and the
result is retrieved by polling `GET tasks/{id}` (which is exactly what `a2a_engine_send` does). So
native abandons any *long-running* hop at `pending`. Dispatch worked only because those agents
clear fast.

### 5. Blocking `message:send` times out on long jobs
`blocking = not polling`, so native uses blocking `message:send`. The engine holds the connection
only for a bounded window: fast hops finish inside it (complete result), the slow finalize exceeds
it → the server returns a non-terminal `working` task → native reads it as a pause → `pending`.

### 6. Streaming — the ROOT limitation (platform-side)
The obvious escape hatch was `streaming=True` (consume the executor's event stream to `completed`).
`RemoteA2aAgent` hardcodes `streaming=False`; we overrode it to `True` and tested. Result:
**streaming does not deliver the result from Agent Runtime engines.** Direct probe of
`POST {engine}/a2a/v1/message:stream` (laptop, no gateway):

```
HTTP 200 · content-type: text/event-stream
+3.9s   TASK_STATE_SUBMITTED  + echoed request text
        …connection held ~25s while the task ran…
+24.9s  stream closed — NO working, NO completed, NO report
```

The task **completes** server-side (the poll path retrieves the full report), but the **SSE stream
forwards only the opening `submitted` event and then the platform drops the connection.**

> **The gap is in the Agent Runtime platform's SSE serving — the Google-managed layer between your
> executor and the wire only forwards the opening `submitted` event and then drops the
> connection.** ADK's `A2aAgentExecutor` correctly enqueues `submitted → working → completed`; the
> managed reasoning-engine HTTP/SSE layer does not stream past `submitted`. This is **not
> fixable in our agent code** — it is the managed platform, and it is why `a2a_engine_send` was
> built to poll in the first place.

---

## Decision — b-hybrid (forced by the platform, not a preference)

For Agent Runtime engines, only **one** consumption mode returns a completed long-running result:

| consumer mode | long-running result? | who does it | verdict |
|---|---|---|---|
| blocking `message:send` | ✗ times out → `working`/`pending` | native `RemoteA2aAgent` default | unusable for slow hops |
| streaming (SSE) | ✗ platform sends only `submitted` | native (overridden) | unusable — platform gap |
| **polling** `GET tasks/{id}` | ✓ | `a2a_engine_send` / `direct_engine_agent` | **the only working path** |

`RemoteA2aAgent` can't poll (it pauses on `working`). Its "pause on working" behavior — wrong for
request/response — is **exactly right for HITL**, where a `working`/`input_required` task *should*
pause. So:

- **Request/response hops** (app→orchestrator, orchestrator→dispatch, contract_finalize,
  vendor→legal): **poll-based sender** (`a2a_engine_send` / `direct_engine_agent`). Unchanged.
- **HITL hop only** (future Phase 5): **`VibeflixRemoteA2aAgent`**, where pause-on-working is the
  desired signal.

**b-strict** (native everywhere, delete the poll sender) was rejected: it would require
re-implementing the poll-to-terminal loop *inside* native (while still distinguishing a real
`input_required` pause from a slow task) — i.e., rebuilding the transport in order to delete it,
with real regression risk and **zero** functional gain on request/response hops.

---

## Current code state (all uncommitted)

- **Kept:** the card flag in `deploy/deploy_agents_a2a.py`; `VibeflixRemoteA2aAgent` (with the
  brief-override and the streaming/limitation note) in
  `packages/vibeflix-common/vibeflix_common/remote_agent.py`, dormant.
- **Removed:** the `USE_REMOTE_A2A_AGENT` flag, the native dispatch branch, the native
  `contract_finalize` branch, and the `[dispatch-native]` debug prints from
  `agents/orchestrator/agent.py`; the deploy env passthrough.
- **Production:** poll-based sender everywhere (proven; executes contracts).

---

## Forward plan

- **Phase 5 — native HITL (only place native is used):** legal emits a `LongRunningFunctionTool`
  so its engine parks `input_required`; the park tunnels up via `run_node` through
  vendor_clearance + orchestrator; the app holds `task_id`/`context_id` and resumes the same task
  with a function-response instead of the `_SESSIONS` re-submit. NOTE: the same platform SSE gap
  may affect how a parked state is observed — validate the park is retrievable via poll, not only
  via stream, before building on it.
- **Phase 6 — durability:** move the app's in-memory `_SESSIONS` pending-HITL state to Firestore so
  a paused audit survives an app restart. Valuable independently of Phase 5.

---

## Appendix — how to reproduce the platform SSE gap

```bash
# From a machine with ADC creds for pokedemo-test:
BASE="https://us-central1-aiplatform.mtls.googleapis.com/v1beta1/projects/789872749985/locations/us-central1/reasoningEngines/<ENGINE_ID>/a2a/v1"
TOK=$(gcloud auth print-access-token)
curl -sN -X POST "$BASE/message:stream" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"message":{"role":"ROLE_USER","messageId":"probe","content":[{"text":"<a brief that triggers real work>"}]}}'
# Observe: 200 text/event-stream, a TASK_STATE_SUBMITTED event, then the connection closes
# after the work window WITHOUT a TASK_STATE_COMPLETED event or the result artifact.
# Contrast: message:send + GET tasks/{id} (poll) returns the completed report.
```

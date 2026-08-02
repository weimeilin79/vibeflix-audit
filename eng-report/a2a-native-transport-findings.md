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

- **Kept:** the card flag in `deploy/deploy_agents_a2a.py`.
- **~~Kept~~ → DELETED (2026-08-01 dead-code cleanup):** `VibeflixRemoteA2aAgent` (with the
  brief-override and the streaming/limitation note) sat dormant in
  `packages/vibeflix-common/vibeflix_common/remote_agent.py` and was never wired into any
  caller, so it went with the rest of the unused code. The findings below still stand — recover
  the file from git history if native transport is revisited.
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

---

# Appendix B — the Vertex SDK *does* ship an A2A client (2026-08-01)

> **Filed upstream:** the gaps below are written up as actionable feature requests, with diagrams
> and repro, in [`UPSTREAM-FR-a2a-client-gaps.md`](UPSTREAM-FR-a2a-client-gaps.md).
> Non-technical summary for wider circulation: [`../A2A-ELI5.md`](../A2A-ELI5.md).

**Added after re-reading this report.** The body above assumes the A2A transport had to be
hand-rolled. That assumption is **wrong for one of the two SDK surfaces**, and the difference
matters. Everything below was verified against the live `vibeflix-ui-renderer` engine
(`4545326643400409088`) with the dependency set we already ship — **no ADK upgrade needed**.

## The two surfaces are not equivalent

| Surface | Module | On our `a2a-sdk 0.3.26` |
|---|---|---|
| `vertexai.agent_engines.get(...)` (legacy) | `vertexai/agent_engines/_agent_engines.py` | **Broken.** Nine a2a names imported in ONE `try/except`, taking `TransportProtocol` from `a2a.utils.constants` — a **1.x-only** location. The miss nulls all nine, so every A2A op is a `None` stub → `TypeError: 'NoneType' object is not callable`. Fails *silently* at import. |
| `vertexai.Client(...).agent_engines.get(name=…)` (`_genai`) | `vertexai/_genai/_agent_engines_utils.py` | **Works.** Version-*detects* a2a-sdk: on 0.3 it imports `TransportProtocol` from `a2a.types`; on 1.x it pulls `TaskIdParams`/`TaskQueryParams` from `a2a.compat.v0_3.types`. |

Both bind the engine's `register_operations()` — `on_message_send`, `on_get_task`,
`on_cancel_task`, `handle_authenticated_agent_card` — as real methods on the returned handle.

## Verified live (laptop + ADC → engine)

```
on_message_send(role=…, parts=[…], messageId=…, kind="message")
   → 1 chunk in 8.7s:  Task(state=submitted) + TaskStatusUpdateEvent
on_get_task(id=<task_id>)
   → t+9.2s state=completed → full agent output incl. the <a2ui-json> artifact
```

That is exactly the `message:send` → `GET tasks/{id}` pair `a2a_engine.py` implements by hand.

## What this changes — and what it doesn't

- **Finding 6 stands.** `on_message_send` returned `submitted` and nothing further; only the
  poll reached a terminal state. The **b-hybrid decision is unaffected**.
- **Corrected:** "we must hand-roll the transport" is no longer true for the app→engine hop.
  The SDK supplies both primitives. It does **not** supply the poll-to-terminal *loop*
  (`on_get_task` is a single call), so the retry/backoff/terminal-state logic stays ours —
  roughly 40 of `a2a_engine.py`'s 322 lines.
- The legacy wrapper hard-raises `"Streaming is not supported in Agent Engine"` on cards with
  `capabilities.streaming: true` (ours have it). The `_genai` path did **not** — it worked with
  our card unmodified.

## Why it still cannot replace `a2a_engine.py` for engine→engine

`_genai`'s `_wrap_a2a_operation` builds its own client:

```python
a2a_agent_card.url = f"{base_url}/{api_version}/{self.api_resource.name}/a2a"
config = ClientConfig(..., httpx_client=httpx.AsyncClient(
    headers={"Authorization": f"Bearer {…_credentials.token}"}))   # single header
```

From a **gateway-attached engine** this mesh needs two things that conflict with the above,
both measured and documented in `a2a_engine.py`:

1. **The mtls host** — the gateway authorizes only the destination it has registered; the plain
   host is refused `403 Egress request is not authorized`. → **Fixable**: `base_url` is
   overridable, e.g. `vertexai.Client(http_options=HttpOptions(base_url="https://us-central1-aiplatform.mtls.googleapis.com"))` (confirmed accepted).
2. **Dual auth** — `Proxy-Authorization` for the gateway *plus* `Authorization` for the target
   endpoint. → **Not fixable from outside**: the `httpx.AsyncClient` and its single header are
   constructed *inside* the wrapper. Sending only `Authorization` is the exact configuration
   that produced the 401s documented in `a2a_engine.py`.

Also note the SDK reads `_credentials.token` **once per call** with no re-mint, whereas
`a2a_engine._headers()` refreshes per request and force-refreshes on a 401 — relevant given the
engine credential-expiry history.

**Verdict:** viable for **app→engine** today; **not** for **engine→engine** without patching the
wrapper's client construction. Keep `a2a_engine.py`. Re-test if the wrapper ever accepts a
caller-supplied `httpx_client`.

## The documented pattern — and why it doesn't close the gap either

[`agent-registry/authenticate-toolsets`](https://docs.cloud.google.com/agent-registry/authenticate-toolsets)
documents A2A auth. Its sample is, in substance, what our (now deleted) `registry_client.py` +
`remote_agent.py` did — a `GoogleAuth(httpx.Auth)` class refreshing ADC creds and setting
`Authorization`, handed in via `httpx_client=`:

```python
registry = AgentRegistry(project_id=project_id, location=location)
httpx_client = httpx.AsyncClient(auth=GoogleAuth(), timeout=httpx.Timeout(60.0))
my_remote_agent = registry.get_remote_a2a_agent(agent_name=agent_name, httpx_client=httpx_client)
```

Both extension points exist in our installed **google-adk 2.3.0** (verified):

```
AgentRegistry.__init__(self, project_id=None, location=None,
                       header_provider: Callable[[ReadonlyContext], Dict[str,str]] | None = None)
AgentRegistry.get_remote_a2a_agent(self, agent_name, *, httpx_client: httpx.AsyncClient | None = None)
```

So **auth is fully extensible on this path** — a caller-supplied httpx client can carry
`Proxy-Authorization` and re-mint on 401, exactly as `a2a_engine._headers()` does. But it still
doesn't work for us, for two reasons this report already established and the doc doesn't touch:

1. `get_remote_a2a_agent` returns a **`RemoteA2aAgent`** → Finding 4: pauses on `working`, cannot
   poll a long-running task to terminal. Auth extensibility does not change transport semantics.
2. Registry **resolution** from inside a gateway-attached engine calls `agentregistry.mtls`, which
   the gateway filters → 403 (see `a2a_engine.py` header). The doc's sample also defaults
   `location` to `"global"`; our registry is **regional** (`us-central1`).

## The three-way picture

| Path | Custom auth headers (Proxy-Authorization, re-mint) | Polls to terminal |
|---|---|---|
| ADK `AgentRegistry.get_remote_a2a_agent(httpx_client=…)` — the documented pattern | ✅ caller owns the httpx client; `header_provider` too | ❌ `RemoteA2aAgent` pauses on `working` |
| Vertex `_genai` `agent_engines` → `on_message_send` + `on_get_task` | ❌ client built inside the wrapper; single `Authorization`; token read once per call | ✅ verified live |
| **`vibeflix_common/a2a_engine.py`** | ✅ dual header, per-request refresh, 401 re-mint | ✅ |

**Neither SDK surface provides both halves. Ours does.** That is a stronger argument for b-hybrid
than the body of this report makes: the choice isn't "hand-rolled vs. SDK", it's that the two SDK
paths each supply one half of what an in-engine, long-running A2A hop needs.

## Undocumented by Google (worth filing)

The [Agent Gateway overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview)
describes the policy model — IAP as "the default enforcement layer", IAM-authorized destinations
only, agent identities "secured by default … using mTLS and DPoP" — but documents **neither**
`Proxy-Authorization` **nor** the plain-vs-`.mtls` host choice. Both of ours were found
empirically (the 401 and the `403 Egress request is not authorized` recorded in `a2a_engine.py`),
and both are load-bearing for any in-engine A2A call.

> Not yet tested empirically: the `_genai` path invoked *from inside* a gateway-attached engine
> (the analysis above is from the wrapper's source plus this report's own measured 403/401
> findings), and a multi-minute hop — the verified poll completed in ~9s.

```python
# Reproduce the working app→engine path:
import asyncio, vertexai
eng = vertexai.Client(project="pokedemo-test", location="us-central1") \
        .agent_engines.get(name="projects/789872749985/locations/us-central1/reasoningEngines/4545326643400409088")
chunks = asyncio.run(eng.on_message_send(
    role="user", parts=[{"kind": "text", "text": "{}"}], messageId="probe", kind="message"))
task = asyncio.run(eng.on_get_task(id=chunks[0][0].id))   # poll until status.state == completed
```

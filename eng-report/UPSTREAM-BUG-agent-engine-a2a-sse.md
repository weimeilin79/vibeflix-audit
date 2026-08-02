# Upstream Bug Report — Agent Engine A2A `message:stream` drops the task lifecycle after `submitted`

**For:** Vertex AI Agent Engine / Agent Runtime team, and the ADK (`google-adk`) team
**Filed by:** vibeflix-audit (production ADK multi-agent mesh on Agent Engine)
**Date:** 2026-07-31 · last verified 2026-08-02
**Status:** OPEN upstream. Findings re-verified in-engine on 2026-08-02; the blocking-send
behaviour is sharpened below and the impact scoped to *long-running* hops.
**Severity:** High — breaks A2A runtime parity; forces every user to hand-roll polling; blocks
native `RemoteA2aAgent` for long-running request/response and native HITL on Agent Engine.

---

## Summary

An ADK agent deployed to **Agent Engine** and exposed over A2A (`A2aAgent` template +
`A2aAgentExecutor`) does **not** stream its task lifecycle over `message:stream`. The SSE response
returns HTTP 200 and the opening **`TASK_STATE_SUBMITTED`** event, holds the connection open while
the agent runs, then **closes without ever emitting `TASK_STATE_WORKING`, `TASK_STATE_COMPLETED`,
or the result artifact.** The task *does* complete server-side — the result is retrievable via the
poll path (`message:send` + `GET tasks/{id}`) — but the streamed lifecycle is truncated.

Because the same `A2aAgentExecutor` emits the full lifecycle on self-served runtimes (Cloud Run /
local), this is a **serving-layer parity bug specific to Agent Engine**: the managed layer between
the executor and the wire forwards only the first event.

---

## Affected versions

| component | version |
|---|---|
| google-adk | 2.3.0 |
| google-cloud-aiplatform | 1.159.0 |
| a2a-sdk | 0.3.26 |
| Python | 3.14.3 |
| runtime | Vertex AI Agent Engine (Reasoning Engine), region us-central1 |
| deploy template | `vertexai.preview.reasoning_engines.A2aAgent` + `A2aAgentExecutor`, card with `supports_authenticated_extended_card=True` |

---

## Expected behavior

`POST {engine}/a2a/v1/message:stream` should emit the full A2A task lifecycle as SSE events —
`submitted → working → … → completed` (plus the result artifact) — the same events
`A2aAgentExecutor` enqueues and the same events a self-served ADK A2A app (Cloud Run/local)
delivers. A standard A2A client (e.g. ADK `RemoteA2aAgent` with `streaming=True`) should receive
the completed result. **Agent Engine should not behave differently from other A2A runtimes.**

## Actual behavior

Raw probe of a deployed engine (auth elided):

```
POST {engine}/a2a/v1/message:stream
→ HTTP 200 · content-type: text/event-stream
  +3.9s   { statusUpdate: { state: "TASK_STATE_SUBMITTED", message: <echo of request> } }
          …connection held open ~25s while the agent actually runs…
  +24.9s  stream closes — NO working, NO completed, NO artifact
```

Meanwhile `POST message:send` + `GET tasks/{id}` (poll) returns the completed report normally, so
the work finished; only the **streamed** lifecycle is truncated to `submitted`.

Related secondary observation: **blocking `message:send`** (a2a client `blocking=True`) also does
not hold until terminal for long-running tasks. So neither non-poll consumption mode (streaming,
blocking) yields a completed long-running result on Agent Engine. Only explicit polling works.

> **Sharpened 2026-08-02, measured in-engine.** An earlier draft said the blocking send "returns a
> non-terminal `working` task". It is worse than that: at **~180s** (three runs: 180.4 / 180.7 /
> 180.2s) it returns **`400 FAILED_PRECONDITION` — "Reasoning Engine Execution failed", with
> `Error Details:` empty** — while the target engine is working perfectly normally (62 log lines,
> dispatching to three peers, zero errors). The same request *without* `blocking` returns in 0.9s
> with a `TASK_STATE_SUBMITTED` task that polls to completion. So the blocking path does not just
> fail to wait — **it reports a healthy engine as failed.** Full write-up: FINDING D of
> [`UPSTREAM-FR-a2a-client-gaps.md`](UPSTREAM-FR-a2a-client-gaps.md).

---

## Minimal reproduction

1. Deploy any ADK agent to Agent Engine via the `A2aAgent` template with a card advertising
   `capabilities.streaming = true` (and `supports_authenticated_extended_card=True` so the card
   route is served — see "Related" below).
2. Make the agent's work take longer than a few seconds (e.g. a couple of model calls).
3. Probe the stream:

```bash
BASE=".../reasoningEngines/<ENGINE_ID>/a2a/v1"
TOK=$(gcloud auth print-access-token)
curl -sN -X POST "$BASE/message:stream" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"message":{"role":"ROLE_USER","messageId":"probe","content":[{"text":"<prompt that triggers real work>"}]}}'
```

Observe: `200 text/event-stream`, a single `TASK_STATE_SUBMITTED` event, then the stream closes at
the end of the work window with no `completed` event or artifact.

4. Contrast: `message:send` then `GET tasks/{id}` returns the completed result.

---

## Root-cause analysis (as far as an external user can see)

- ADK's `A2aAgentExecutor.execute` (`google/adk/a2a/executor/a2a_agent_executor.py`) enqueues
  `submitted` (final=False) → `working` (final=False) → runs the agent → `completed` (final=True).
  So the **executor produces the full lifecycle**; this is correct.
- The truncation therefore occurs in the **Agent Engine managed serving layer** that sits between
  the executor's event queue and the HTTP/SSE wire. It forwards the opening `submitted` event and
  then stops relaying subsequent events, closing the stream when the invocation ends.

We cannot see inside the managed layer, but the executor-emits-full / wire-delivers-only-`submitted`
split localizes the defect to that layer.

**Test topology (rules out a proxy):** the probe above was run **from a laptop directly to
`{region}-aiplatform.mtls.googleapis.com`** with ADC credentials — i.e. the *inbound* Google API
frontend, **not** through any customer egress/mTLS gateway (which only governs engine *outbound*
traffic). The truncation reproduces on this direct path. Moreover the `submitted` event arrives
**live (~4s)** followed by silence and a close (~25s); a buffering proxy would have delayed
`submitted` as well, so this is not proxy response-buffering — the serving layer emits `submitted`
and then stops relaying. (Not yet isolated: the engine→engine path additionally crosses the
customer mTLS gateway; that is a separate potential factor, but it is not the root cause since the
truncation already occurs without it.)

---

## Impact

1. **Runtime parity is broken.** Identical agent + executor behaves differently on Agent Engine vs
   Cloud Run/local. Portable A2A code silently loses streaming when deployed to Agent Engine.
2. **`RemoteA2aAgent` is unusable for *long-running* request/response on Agent Engine.** With
   streaming truncated *and* blocking failing at ~180s, the ADK client's only remaining option
   (treating a `working` task as a HITL pause) yields a bogus `pending` — no result.
   *(Scoped 2026-08-02: hops that finish inside the ceiling work fine on the stock client — three
   run in our production mesh. The defect bites duration, not request/response as a category.)*
3. **Users must hand-roll polling.** To get a completed result we had to write a bespoke poll-based
   sender (`message:send` + `GET tasks/{id}` loop with token refresh, replica-404 handling, etc.).
   This is exactly the boilerplate the framework should own — it dirties application code and
   diverges from the documented A2A/ADK client model.
4. **Native HITL is blocked from being clean.** ADK's long-running-tool / `input_required` HITL is
   designed around `RemoteA2aAgent` consuming the task lifecycle. With the lifecycle truncated on
   Agent Engine, adopting native HITL is impossible without more custom transport work.
5. **A second, independent defect compounds this one.** The `A2aAgent` template hardcodes the
   **plain** aiplatform host into the card each engine serves, and the Agent Gateway authorizes
   only the `.mtls` host — so from a gateway-attached engine *every* standard client is refused
   `403` before any of the above even applies. Filed separately as FINDING A of
   [`UPSTREAM-FR-a2a-client-gaps.md`](UPSTREAM-FR-a2a-client-gaps.md); fixing the SSE gap alone
   would not make the stock client work engine-to-engine.

---

## Requested fix

**Primary (Agent Engine):** make the managed `message:stream` serving layer forward the **full** SSE
lifecycle (`working`, `completed`, artifacts, and any interim `input_required`) that
`A2aAgentExecutor` emits — matching self-served ADK A2A runtimes and the A2A spec. Likewise, honor
`blocking=true` on `message:send` for long-running tasks (hold until terminal), or document that
polling is required.

**Secondary / defensive (ADK):** when `RemoteA2aAgent` is talking to a server whose stream ends
without a terminal state, it should **fall back to polling `GET tasks/{id}` to a terminal state**
rather than surfacing the last non-terminal (`working`) event as a completed/paused result. Today a
non-terminal task is turned into a mock function call (`remote_a2a_agent.py:526,542` (adk 2.3.0)), which is
correct for genuine `input_required` HITL but wrong for a still-running task — the two are
indistinguishable to the client without polling.

Either fix, independently, would remove the need for user-space polling and restore runtime parity.

---

## Related (minor) — undiscoverable A2A card by default

Separately: the A2A discovery card (`{engine}/a2a/v1/card`) is **not served** unless the deployed
`AgentCard` sets `supports_authenticated_extended_card=True` (which gates
`A2aAgent.register_operations()` registering `handle_authenticated_agent_card`). Without it the
route returns HTTP 400 and no standard A2A client can discover the engine. This is easy to miss and
arguably should be the default (or clearly documented) for A2A-exposed Agent Engine deployments.

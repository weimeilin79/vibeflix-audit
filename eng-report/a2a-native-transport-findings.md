# Engineering Report — Native A2A (RemoteA2aAgent) vs. the Poll-Based Sender

**Project:** vibeflix-audit (ADK multi-agent licensing mesh on Agent Runtime, `pokedemo-test`)
**Date:** 2026-07-31
**Author:** weimeilin
**Status:** ⚠️ **SUPERSEDED IN PART (2026-08-02)** — historical record of the July-31 investigation.
Its *platform* findings (SSE truncation, blocking ceiling, polling required for long hops) still
hold. Its *conclusion* — "native is unusable, poll sender everywhere" — does **not**: the real
blocker turned out to be the agent card's host, and three hops now run the stock ADK client in
production. Read [`UPSTREAM-FR-a2a-client-gaps.md`](UPSTREAM-FR-a2a-client-gaps.md) first; it is
the current account.

> **What this report got wrong, and why it matters.** Every hop here was tested *from a laptop*
> or reasoned from source. The card-host defect only bites a **gateway-attached engine**, so it
> was invisible in that setup, and its 403s were attributed to auth and transport semantics
> instead. Three of the conclusions below (dual-auth required, registry resolution blocked,
> native unusable for request/response) were later refuted by in-engine measurement. They are
> annotated inline as ❌ **RETRACTED**. This is the origin of the standing rule that an A2A or
> gateway claim is not established until it is re-measured from inside an engine.

---

## TL;DR

We evaluated replacing the hand-rolled poll-based A2A sender (`a2a_engine_send` /
`direct_engine_agent`) with ADK's native `RemoteA2aAgent`, motivated by native's built-in
human-in-the-loop (HITL) `input_required` park/resume. We shipped one necessary fix (engines now
serve an A2A card) and then proved, in the cloud, that **native cannot do request/response for
long-running hops on Agent Runtime** — not because of our code, but because of a **platform-level
streaming gap**. Decision: **b-hybrid** — keep the poll-based sender for request/response, use
native only where "pause on working" is actually desired (the HITL step).

> **Correction (2026-08-02).** The long-hop conclusion survives; the blanket one does not.
> "Native cannot do request/response" is true only **above ~180s**. Below that the stock client
> works in-engine, once it is given a card naming the `.mtls` host — which the platform's own
> card never does. Shipped: `app → ui_renderer` (stock `RemoteA2aAgent`), `orchestrator →
> brand_style` and `orchestrator → deal_pricing` (`VibeflixRemoteA2aAgent`). The poll sender is
> retained only for hops that can exceed the ceiling: `app → orchestrator`, `contract_finalize`,
> `vendor_clearance → legal`. So the final shape is still a hybrid — but the line is drawn at
> **hop duration**, not at **HITL vs request/response**.

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

`VibeflixRemoteA2aAgent` (`packages/vibeflix-common/vibeflix_common/a2a/remote_agent.py`) is retained
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
to `polling=False` (`remote_a2a_agent.py:249`) and treats a `submitted`/`working` task as a **pause**
(`_add_mock_function_call`, `remote_a2a_agent.py:526,542` (adk 2.3.0)), instead of polling to terminal. Our
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

> ⚠️ **This decision was later revised — see the Correction in the TL;DR.** The table below is
> still correct about *what the platform does*; it is wrong that this forces the poll sender onto
> every request/response hop. The missing option is the one we eventually took: keep the stock
> client and make it send **non-blocking, then poll** (`long_running=True`). That is "polling" in
> the table's third row, but performed *by* the ADK client rather than instead of it.

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

## Code state — as of 2026-07-31 (superseded; see the next section for today)

- **Kept:** the card flag in `deploy/deploy_agents_a2a.py`.
- **~~Kept~~ → DELETED (2026-08-01 dead-code cleanup):** `VibeflixRemoteA2aAgent` (with the
  brief-override and the streaming/limitation note) sat dormant in
  `packages/vibeflix-common/vibeflix_common/a2a/remote_agent.py` and was never wired into any
  caller, so it went with the rest of the unused code.
- **Removed:** the `USE_REMOTE_A2A_AGENT` flag, the native dispatch branch, the native
  `contract_finalize` branch, and the `[dispatch-native]` debug prints from
  `agents/orchestrator/agent.py`; the deploy env passthrough.
- **Production:** poll-based sender everywhere (proven; executes contracts).

## Code state — actual, 2026-08-02 (committed `ec50304`)

`remote_agent.py` was **recovered from git history** (commit `d18c7c92`) and is now load-bearing,
not dormant:

| hop | transport | why |
|---|---|---|
| `app → ui_renderer` | stock `RemoteA2aAgent` + `a2a_card.engine_card()` | app is Cloud Run, not gateway-attached; hop is fast |
| `orchestrator → brand_style` | `VibeflixRemoteA2aAgent` | ~18s; needs the mtls repoint + brief override |
| `orchestrator → deal_pricing` | `VibeflixRemoteA2aAgent` | ~9-20s; same |
| `app → orchestrator` | `a2a_engine_send` (poll) | whole audit, minutes — over the ~180s ceiling |
| `contract_finalize` | `a2a_engine_send` (poll) | can run long |
| `vendor_clearance → legal` | `a2a_engine_send` (poll) | multi-round clarification loop |

`VibeflixRemoteA2aAgent` also gained `long_running=True`, which swaps the stock blocking send for
the non-blocking send + poll behind an identical constructor and `ctx.run_node` call. **It has no
production caller today** — the three long hops above call `a2a_engine_send` directly. It exists
so a hop can be moved across the ceiling without changing its call site.

---

## Forward plan — both phases are now CLOSED

- **Phase 5 — native HITL: ❌ investigated, NOT adopted.** The park/resume mechanism itself works
  (legal parked in `INPUT_REQUIRED` and resumed to execute `LC-928738`), but the mesh's real HITL
  moment is new-vendor onboarding, which lives in vendor_clearance's **skill-driven reasoner run
  via `ctx.run_node`** — there the LLM only sees the SkillToolset's management tools, so a
  `LongRunningFunctionTool` is not callable (`Tool 'request_operator_input' not found`). The
  existing report-based `needs_input` + re-submit HITL is retained. All experiment code was
  reverted. Full write-up: [`phase5-change-scope.md`](phase5-change-scope.md).
- **Phase 6 — durability: ✅ DONE.** The app's pending-HITL state moved from the in-memory
  `_SESSIONS` dict to Firestore (collection `audit_sessions`, `agents/app.py`), so a paused audit
  survives an app restart and is replica-safe; the dict remains as the local-dev fallback.
  Validated end-to-end.

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
   *(2026-08-02: accepted, but **it did not work** — the fetched card's interface entry still won
   inside `ClientFactory`. Overriding `base_url` alone is not sufficient; you must supply the
   `AgentCard` object. See FINDING A "Secondary" in the FR.)*
2. ~~**Dual auth** — `Proxy-Authorization` for the gateway *plus* `Authorization` for the target
   endpoint. → **Not fixable from outside**.~~
   ❌ **RETRACTED 2026-08-02.** Measured in-engine: a **single** `Authorization` header on the
   `.mtls` host returns **200**, against three peer agents, on both `message:send` and
   `message:stream`. `Proxy-Authorization` is **not** required. The 401s attributed to it were
   most likely the *missing* `Authorization` header that the same change also introduced. This
   removes the blocker — the wrapper's single-header client is fine; only the **host** was wrong.

Also note the SDK reads `_credentials.token` **once per call** with no re-mint, whereas
`a2a_engine._headers()` refreshes per request and force-refreshes on a 401 — relevant given the
engine credential-expiry history.

**Verdict:** viable for **app→engine** today; **not** for **engine→engine** without patching the
wrapper's client construction. Keep `a2a_engine.py`. Re-test if the wrapper ever accepts a
caller-supplied `httpx_client`.

> **Corrected 2026-08-02.** The verdict held for the wrong reason. Engine→engine was blocked by
> the **card's host**, not by the single `Authorization` header (see the retraction above), and it
> is reachable today — not through `_genai`, but through ADK's `RemoteA2aAgent` handed a
> self-built `AgentCard` pointing at `.mtls`. What genuinely still rules `_genai` out for
> engine→engine is that its wrapper assigns `a2a_agent_card.url` from `base_url` while the fetched
> card's interface entry takes precedence, so the host cannot be steered from outside.

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
   *(Still true — but it only disqualifies hops that run **long**. Fast hops are fine, and three
   now run on `RemoteA2aAgent` in production.)*
2. ~~Registry **resolution** from inside a gateway-attached engine calls `agentregistry.mtls`,
   which the gateway filters → 403.~~
   ❌ **RETRACTED 2026-08-02.** Measured in-engine, `list_agents()` returned **10 agents** and
   successfully built a `RemoteA2aAgent`. The original 403 was a **grant gap** — `iap.egressor`
   was missing on the `gcp-agentregistry` endpoints (all four variants), which our own
   `grant_agent_iam.sh` comments already admitted. The gateway does not filter the registry.
   *(Unretracted: the doc's sample does default `location` to `"global"` while our registry is
   regional — `us-central1`.)*

## The three-way picture

| Path | Custom auth headers (Proxy-Authorization, re-mint) | Polls to terminal |
|---|---|---|
| ADK `AgentRegistry.get_remote_a2a_agent(httpx_client=…)` — the documented pattern | ✅ caller owns the httpx client; `header_provider` too | ❌ `RemoteA2aAgent` pauses on `working` |
| Vertex `_genai` `agent_engines` → `on_message_send` + `on_get_task` | ❌ client built inside the wrapper; single `Authorization`; token read once per call | ✅ verified live |
| **`vibeflix_common/a2a/engine.py`** | ✅ dual header, per-request refresh, 401 re-mint | ✅ |

**Neither SDK surface provides both halves. Ours does.** *(Still true of the SDKs as shipped —
but the gap is bridgeable: subclassing `RemoteA2aAgent` and overriding `_run_async_impl` to send
non-blocking and poll gives you both halves without leaving the framework. That is what we
eventually did.)* That is a stronger argument for b-hybrid
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

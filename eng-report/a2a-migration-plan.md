# Migration plan — from `a2a/engine.py` to the stock ADK client

**Date:** 2026-08-02 · **Status:** ✅ **EXECUTED** — all four gates resolved; see *Outcome* below.
**Basis:** [`UPSTREAM-FR-a2a-client-gaps.md`](UPSTREAM-FR-a2a-client-gaps.md) (measured in production)

> ## Outcome
>
> Every `ctx.run_node` dispatch hop now runs on the prebuilt ADK client, through the one
> `VibeflixRemoteA2aAgent` subclass:
>
> | hop | path | why |
> |---|---|---|
> | `orchestrator → brand_style` | stock blocking send | ~18s, well inside the ceiling |
> | `orchestrator → deal_pricing` | stock blocking send | ~9-20s |
> | `orchestrator → vendor_clearance` | `long_running=True` (send + poll) | fans into legal's Q&A loop |
> | `app → ui_renderer` | stock `RemoteA2aAgent` + self-built card | app is Cloud Run, hop is fast |
> | `contract_finalize` | `a2a_engine_send` | one-shot send inside a tool — no agent to construct |
> | `app → orchestrator` | `direct_engine_agent` (poll) | driven from outside the mesh |
> | `vendor_clearance → legal` | `a2a_engine_send` | called from a tool, not a dispatch node |
>
> **G2 did not stop the migration; it shaped it.** The fix for a long hop was never "stay off the
> prebuilt client" — it was to keep the client and change the *pacing*. `long_running=True` sends
> non-blocking and polls, so no single request approaches the ceiling, and the call site is
> identical to a fast hop. The three remaining `a2a_engine_send` callers are not dispatch nodes,
> so there is no agent for the subclass to be.

## What changed

We can use the documented framework after all. The blocker was never auth, polling, or streaming
— it was that the A2aAgent template hardcodes the **plain** aiplatform host into the agent card,
and the gateway authorizes only **`.mtls`**. `RemoteA2aAgent` accepts an `AgentCard` *object*, so
we build the card ourselves and point it at the right host.

**Verified in-engine (round 4):** stock `RemoteA2aAgent` + self-built mtls card → 200, real A2UI
(1127 chars), while the same client with the platform card → 403.

## The replacement, as shipped

Two pieces. **`vibeflix_common/a2a/card.py`** builds the card the platform won't:

```python
def engine_card(engine_a2a_base: str, name: str, description: str = "") -> AgentCard:
    """An AgentCard for an Agent-Runtime engine, on the host the CALLER may use.

    The platform-served card advertises the PLAIN aiplatform host (hardcoded in
    vertexai/agent_engines/templates/a2a.py:328), which the gateway refuses with
    `403 Egress request is not authorized`.
    """
    return AgentCard(
        name=name, description=description or f"{name} over A2A",
        url=f"{engine_a2a_base.rstrip('/')}/a2a",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        preferred_transport="HTTP+JSON", skills=[])
```

> Note it takes the **caller's** base rather than hardcoding `.mtls`, because the right host
> depends on who is calling: `.mtls` from a gateway-attached engine, plain from Cloud Run. That
> is why `app → ui_renderer` can use a stock `RemoteA2aAgent` with this card and nothing else.

**`vibeflix_common/a2a/remote_agent.py`** carries the rest, so the orchestrator's factory becomes
one call with no transport branch:

```python
return VibeflixRemoteA2aAgent(name=name, description=description, agent_card=base,
                              long_running=name in _LONG_RUNNING_A2A)
```

## Gates — do not migrate a hop until its gate is green

| Gate | Question | Status |
|---|---|---|
| **G1** | Does a stock client work in-engine at all? | ✅ **PASSED** — round 4/5: real A2UI, 1127 & 1527 chars |
| **G2** | Does a **long** hop survive in-engine *on a blocking send*? | ❌ **FAILED** — 180.7s, **0 chars**, silent. **Resolved by design**, not by retry: long hops send non-blocking and poll (`long_running=True`), so the blocking ceiling is never reached. |
| **G3** | Is the explicit brief preserved? | ✅ **RESOLVED** — not by the inconclusive test below, but from ADK source: `run_node` hands `node_input` to the scheduler, never to the session, so `_construct_message_parts_from_session` provably cannot see it. The override is required; it is in the subclass. |
| **G4** | Token expiring mid-hop on a single blocking send? | ✅ **MOOT** — no hop makes a long single request any more. Fast hops finish inside the token's life; long hops poll, and `a2a_engine._headers()` re-mints per request. |

### ⚠️ G2 FAILED — and it reverses an earlier "refutation"

| caller | client | long hop → orchestrator |
|---|---|---|
| laptop (no gateway) | `RemoteA2aAgent` | ✅ 180.4s, 7590 chars |
| **in-engine (gateway-attached)** | `RemoteA2aAgent` + self-built mtls card | ❌ **180.7s, 0 chars — silent** |
| in-engine | `a2a_engine_send` | ✅ works |

The work runs (180s elapsed, same as the successful laptop run) but **no result comes back**, with
no error and no mock function call. Note what this means for the record: the earlier retraction of
*"`RemoteA2aAgent` can't complete a long-running hop"* was based on a **laptop** test. **In-engine
— the only environment that matters — the original finding holds.** Environment, not client, was
the confound.

> **Two follow-ups closed this out.** (1) The "silent" part was our own doing: FINDING D shows the
> platform *does* answer, with `400 FAILED_PRECONDITION` at ~180s — our agent swallowed it, so the
> caller saw emptiness rather than an error. (2) The row that matters is missing from the table
> above: **in-engine, `RemoteA2aAgent` sending non-blocking and polling → ✅ works.** So the
> confound was environment *and* the send mode, and only the send mode was ever the real limit.

### ⚠️ G3 — the test exercised the wrong path, so we stopped testing and read the source

Our test ran two turns through a `Runner`, where the brief **is** the session's newest event — so
`_construct_message_parts_from_session` rebuilding from history reproduces it exactly, and it
"survived" trivially. Finding 3's real scenario is a brief passed **out-of-band** to
`ctx.run_node(agent, brief)` inside a **Workflow**, where the brief is *not* in the session. A
`Runner` cannot reproduce that.

**Resolved from source instead of by experiment.** ADK's `run_node` hands `node_input` to the
scheduler and never writes it to the session, so `_construct_message_parts_from_session` cannot
see it — no measurement needed, and no measurement through a `Runner` could have settled it. The
override is mandatory for any `ctx.run_node` dispatch; it lives in the subclass, and all three
dispatch hops rely on it. **Closed.**

### G4 — the one real capability gap

`a2a/engine.py` re-mints the token **between polls**, so a hop can outlive its token. A stock
`RemoteA2aAgent` issues **one blocking `message:send`**; an `httpx.Auth` refreshes per *request*,
so there is no opportunity to refresh mid-flight. Hops that can exceed the token's remaining
lifetime (`legal` escalations, `contract_finalize`) are the exposure.

By contrast the poll loop's **replica-miss tolerance is already obsolete** — the shared
`RemoteTaskStore` made every poll a 200 (measured 49/49 in `a2a/engine.py`'s own comment). That is
not a reason to keep the sender.

## Sequenced migration — as executed

**Phase 1 — the fast dispatch hops. ✅ DONE.**
`brand_style` and `deal_pricing` migrated to the stock path; they clear in 9-20s and G1 proved the
shape works in-engine with real payloads. Verified by a full audit producing a contract id, not by
"it didn't error" — G2's failure mode is a silent empty answer.

**Phase 2 — the app→engine hops. ✅ DONE for `ui_renderer`.**
The app is Cloud Run, not gateway-attached, so a plain-host card works and a **stock**
`RemoteA2aAgent` needs no subclass at all. `app → orchestrator` was deliberately left on
`a2a_engine_send`: a whole audit runs for minutes, far past the ceiling.

**Phase 3 — the long hops. ✅ DONE differently than planned.**
The original plan said *do not migrate*, reading G2 as disqualifying. That was the wrong
conclusion from a correct measurement: G2 disqualifies the **blocking send**, not the **client**.
Adding `long_running=True` to the subclass — non-blocking send, then poll — keeps the prebuilt
client and never makes a request long enough to hit the ceiling. `vendor_clearance` (which fans
into legal's Q&A loop) now runs this way.

The two open questions this section raised are answered: (a) the in-engine long hop does not come
back "empty" — FINDING D shows it returns `400 FAILED_PRECONDITION` at ~180s while the callee
keeps working; the emptiness was our agent swallowing that error. (b) The brief-drop is real and
provable from ADK source, not just observation — `run_node` hands `node_input` to the scheduler,
never to the session.

**Phase 4 — narrow `a2a/engine.py`. ✅ DONE, as predicted.**
It survives as the helper for the three callers that are **not** `ctx.run_node` dispatch nodes —
`contract_finalize`, `app → orchestrator`, `vendor_clearance → legal` — plus the poll loop that
`long_running=True` itself calls. It is no longer the mesh's universal transport.

## What NOT to do

- **Don't migrate everything at once.** Every failure in this investigation was silent — a wrong
  answer, not an exception. Migrate one hop, run a full audit, compare the contract id.
- **Don't delete `a2a/engine.py` early.** It is the control that proves any new failure is the
  migration's fault and not the platform's.
- **Don't rely on the platform's card.** That is the defect; building the card is the fix.

## Rollback

Each phase is one factory function (`_remote_agent` in `orchestrator/agent.py`,
`_presenter_agent` in `app.py`). Revert = swap the constructor back and redeploy that engine.
Engine ids and grants are unaffected, so rollback is a single in-place redeploy.

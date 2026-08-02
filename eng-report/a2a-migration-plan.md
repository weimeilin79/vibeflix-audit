# Migration plan — from `a2a_engine.py` to the stock ADK client

**Date:** 2026-08-02 · **Status:** DRAFT — two gates still under test (F2, G)
**Basis:** [`UPSTREAM-FR-a2a-client-gaps.md`](UPSTREAM-FR-a2a-client-gaps.md) (measured in production)

## What changed

We can use the documented framework after all. The blocker was never auth, polling, or streaming
— it was that the A2aAgent template hardcodes the **plain** aiplatform host into the agent card,
and the gateway authorizes only **`.mtls`**. `RemoteA2aAgent` accepts an `AgentCard` *object*, so
we build the card ourselves and point it at the right host.

**Verified in-engine (round 4):** stock `RemoteA2aAgent` + self-built mtls card → 200, real A2UI
(1127 chars), while the same client with the platform card → 403.

## The replacement, in full

```python
# vibeflix_common/a2a_card.py  (new, ~15 lines)
from a2a.types import AgentCapabilities, AgentCard

def mtls_card(engine: str, name: str, region: str = "us-central1") -> AgentCard:
    """A card pointing at the host the Agent Gateway authorizes.

    The platform-served card advertises the PLAIN aiplatform host (hardcoded in
    vertexai/agent_engines/templates/a2a.py:328), which the gateway refuses with
    `403 Egress request is not authorized`. Building the card ourselves is the
    only way to reach a peer engine from inside a gateway-attached engine.
    """
    return AgentCard(
        name=name, description=f"{name} over A2A",
        url=f"https://{region}-aiplatform.mtls.googleapis.com/v1beta1/{engine}/a2a",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        preferred_transport="HTTP+JSON", skills=[])
```

Then `direct_engine_agent(name, desc, base)` becomes:

```python
RemoteA2aAgent(name=name, description=desc,
               agent_card=mtls_card(engine, name),
               httpx_client=a2a_httpx_client())      # our existing GoogleAuth
```

## Gates — do not migrate a hop until its gate is green

| Gate | Question | Status |
|---|---|---|
| **G1** | Does a stock client work in-engine at all? | ✅ **PASSED** — round 4/5: real A2UI, 1127 & 1527 chars |
| **G2** | Does a **long** hop survive in-engine? | ❌ **FAILED** — 180.7s, **0 chars**, silent |
| **G3** | Is the explicit brief preserved? | ⚠️ **INCONCLUSIVE** — wrong code path tested |
| **G4** | Token expiring mid-hop on a single blocking send? | ❓ untested |

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

### ⚠️ G3 INCONCLUSIVE — the test exercised the wrong path

Our test ran two turns through a `Runner`, where the brief **is** the session's newest event — so
`_construct_message_parts_from_session` rebuilding from history reproduces it exactly, and it
"survived" trivially. Finding 3's real scenario is a brief passed **out-of-band** to
`ctx.run_node(agent, brief)` inside a **Workflow**, where the brief is *not* in the session. A
`Runner` cannot reproduce that. **Still open.**

### G4 — the one real capability gap

`a2a_engine.py` re-mints the token **between polls**, so a hop can outlive its token. A stock
`RemoteA2aAgent` issues **one blocking `message:send`**; an `httpx.Auth` refreshes per *request*,
so there is no opportunity to refresh mid-flight. Hops that can exceed the token's remaining
lifetime (`legal` escalations, `contract_finalize`) are the exposure.

By contrast the poll loop's **replica-miss tolerance is already obsolete** — the shared
`RemoteTaskStore` made every poll a 200 (measured 49/49 in `a2a_engine.py`'s own comment). That is
not a reason to keep the sender.

## Sequenced migration

**Phase 1 — the fast hops only. VIABLE NOW.**
Migrate `brand_style`, `vendor_clearance`, `deal_pricing` — they clear in 9-20s and G1 proves the
shape works in-engine with real payloads. Keep `a2a_engine.py` importable; revert by swapping the
factory back. **Verify each hop by comparing a full audit's contract id, not by "it didn't error"
— G2's failure mode is a silent empty answer.**

**Phase 2 — the app→engine hops.**
The app is Cloud Run, not gateway-attached, so it can use either host. Lower risk than Phase 1,
but no urgency either — sequence it after Phase 1 has soaked.

**Phase 3 — the long hops (`legal`, `contract_finalize`). ❌ DO NOT MIGRATE.**
G2 settles this: in-engine, a long hop through the stock client returns an **empty result after
180s, silently**. `a2a_engine.py` stays for these hops — not as legacy, but because it is the only
transport measured to work for them. G3 and G4 no longer gate anything here; G2 alone is
disqualifying.

If this is ever revisited, the two things to establish first are (a) *why* the in-engine long hop
comes back empty — deadline, gateway, or task-store interaction — and (b) whether the brief-drop
(Finding 3) is real in a **Workflow** context, since `contract_finalize` depends on it.

**Phase 4 — retire or narrow `a2a_engine.py`.**
Only after Phases 1-3. Likely outcome: it survives as a *small* helper for long hops rather than
the mesh's universal transport.

## What NOT to do

- **Don't migrate everything at once.** Every failure in this investigation was silent — a wrong
  answer, not an exception. Migrate one hop, run a full audit, compare the contract id.
- **Don't delete `a2a_engine.py` early.** It is the control that proves any new failure is the
  migration's fault and not the platform's.
- **Don't rely on the platform's card.** That is the defect; building the card is the fix.

## Rollback

Each phase is one factory function (`_remote_agent` in `orchestrator/agent.py`,
`_presenter_agent` in `app.py`). Revert = swap the constructor back and redeploy that engine.
Engine ids and grants are unaffected, so rollback is a single in-place redeploy.

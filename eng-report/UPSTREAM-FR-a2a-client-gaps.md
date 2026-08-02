# Upstream Bug — the A2aAgent template advertises a host the Agent Gateway refuses

**Filed by:** vibeflix-audit (ADK multi-agent mesh on Agent Runtime, `pokedemo-test`)
**Date:** 2026-08-02 · Supersedes two earlier drafts of this file, both of which were wrong.
**Severity:** High — **no standard A2A client can make an agent-to-agent call** from a
gateway-attached engine, and the cause is not user-configurable.

## The defect in one paragraph

`vertexai/agent_engines/templates/a2a.py` hardcodes the **plain** aiplatform host into the agent
card it serves, overwriting whatever URL the deployer set. The **Agent Gateway refuses the plain
host** — it authorizes only the `.mtls` host. Every standard A2A client resolves its transport URL
from the card. So the platform advertises a destination its own gateway blocks, and the deployer
cannot change it.

```mermaid
flowchart LR
  T["A2aAgent template<br/>set_up()"] -->|"hardcodes PLAIN host<br/>into the served card"| C["📇 agent card"]
  C -->|"client reads card.url"| X["🚫 Agent Gateway<br/>403 Egress not authorized"]
  M["our a2a_engine.py<br/>ignores the card, hardcodes .mtls"] --> OK["✅ 200"]
```

## The evidence chain — every link verified

| # | Link | How established |
|---|---|---|
| 1 | The template hardcodes the plain host and overwrites the deployer's URL | **Source**: `templates/a2a.py:328` builds `https://{location}-aiplatform.googleapis.com/...`, then `:342` `self.agent_card.supported_interfaces[0].url = new_url` |
| 2 | The deploy-time card URL is genuinely ignored | **Measured**: we deployed a probe whose `agent_card(url=…)` was set to the **mtls** host; the served card still returned the **plain** host |
| 3 | The gateway refuses the plain host | **Measured in-engine**: `message:send` to the plain host with **both** `Authorization` and `Proxy-Authorization` → `403 Egress request is not authorized`, against **3 different peer agents** |
| 4 | The gateway allows the mtls host | **Measured in-engine**: same call to `.mtls` with a **single** `Authorization` header → `200`, against the same 3 peers, on **both** `message:send` and `message:stream` |
| 5 | A2A clients follow the card | **Source**: `a2a/client/transports/rest.py:57` `self.url = agent_card.url`, then `f'{self.url}/v1/message:send'` |
| 6 | Result: the SDK client 403s in-engine while a raw mtls call succeeds | **Measured in-engine**, same run, same credentials |

**The control makes this readable.** Our own `a2a_engine_send()` ran inside the same probe, in the
same execution, against the same targets, and **succeeded** — so grants, identity, targets and
deploy are all known-good. It works precisely because it ignores the card and calls `.mtls`.

## Reproduction

Deploy any ADK agent via the `A2aAgent` template to a gateway-attached engine, then from **inside**
another such engine:

```python
# fails: 403 Egress request is not authorized  (client follows the card → plain host)
eng = vertexai.Client(project=P, location=L).agent_engines.get(name=TARGET)
await eng.on_message_send(role="user", parts=[{"kind":"text","text":"hi"}],
                          messageId="x", kind="message")

# succeeds: 200  (same engine, same credential, .mtls host)
requests.post(f"https://{L}-aiplatform.mtls.googleapis.com/v1beta1/{TARGET}/a2a/v1/message:send",
              headers={"Authorization": f"Bearer {tok}"}, json=body)
```

Grants were exactly what `grant_agent_iam.sh` gives a production agent (7 project roles,
`iap.egressor` on 20 registered `GCP *` endpoints incl. all four `agentregistry` variants, and on
all six agent endpoints), plus 5 minutes for IAP propagation.

## ✅ WORKAROUND — verified in production, uses the stock framework

**You do not have to accept the platform's card.** `RemoteA2aAgent` takes an `AgentCard`
*object*, and `RestTransport` prefers an explicit url over the card's. Build the card yourself,
point it at `.mtls`, and the documented ADK client works from inside a gateway-attached engine:

```python
from a2a.types import AgentCapabilities, AgentCard
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

card = AgentCard(
    name="ui-renderer-via-mtls",
    description="...",
    url=f"https://{REGION}-aiplatform.mtls.googleapis.com/v1beta1/{ENGINE}/a2a",  # ← the fix
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"], default_output_modes=["text/plain"],
    preferred_transport="HTTP+JSON", skills=[],
)
agent = RemoteA2aAgent(name="peer", description="...", agent_card=card,
                       httpx_client=httpx.AsyncClient(auth=GoogleAuth()))
```

**Measured in the same probe run, same engine, same credentials, same target:**

| client | card | result |
|---|---|---|
| `_genai` `on_message_send` | platform's (plain host) | ❌ 403 Egress not authorized |
| `_genai` `on_message_send` (self-target) | platform's (plain host) | ❌ 403 Egress not authorized |
| **stock `RemoteA2aAgent` + Runner** | **self-built (mtls host)** | ✅ **200 — 1127 chars of real A2UI** |

That is a controlled A/B: the only variable is which host the card names.

**Caveats before adopting it wholesale** — this proves the *transport*, not a drop-in replacement:
- the in-engine test used a **fast** target (~9s). A long hop in-engine through `RemoteA2aAgent`
  is untested (a 180s hop did work from a laptop).
- **Finding 3** of `a2a-native-transport-findings.md` still applies:
  `_construct_message_parts_from_session` discards the explicit brief passed to `run_node`, which
  is what `contract_finalize` depends on. That is independent of transport.

## Requested fix

**Primary:** make the template advertise the host the gateway authorizes — the `.mtls` endpoint —
or make the card URL respect what the deployer set instead of overwriting it. Either removes the
need for every user to hand-roll a transport.

**Secondary:** `_genai`'s `_wrap_a2a_operation` assigns `a2a_agent_card.url` from the client's
`base_url`, but overriding `base_url` to `.mtls` still failed — the fetched card's interface entry
(pinned by link 1) appears to take precedence in `ClientFactory`. If the override is meant to work,
it should also update the interface list. *(This last link is read from source, not isolated by
measurement.)*

---

# Two independent findings, both measured

## FINDING B — legacy `vertexai.agent_engines` A2A ops silently become `None`

`vertexai/agent_engines/_agent_engines.py` imports nine a2a names in **one**
`try/except (ImportError, AttributeError)`, taking `TransportProtocol` from `a2a.utils.constants`
— a **1.x-only** location. On a2a-sdk 0.3.x (pinned by `google-adk[a2a] 2.3.0`) that import fails,
so **all nine become `None`** and every A2A op is a silent stub:

```
TypeError: 'NoneType' object is not callable      # _agent_engines.py:1748
```

No hint that a dependency was missing. The newer `_genai/_agent_engines_utils.py` already
version-detects correctly (`a2a.compat.v0_3.types` on 1.x). **Fix:** apply that detection to the
legacy module, or raise a clear `ImportError` naming the package.

## FINDING C — `AgentRegistry` needs `google-adk[agent-identity]`, and only says so at call time

On an Agent-Identity engine:

```
ImportError: Missing required dependencies for Agent Identity Auth Manager.
Please install with: pip install "google-adk[agent-identity]"
```

…raised at **call** time, not import. The `[a2a]` extra alone is insufficient. **Fix:** declare it
where it's used, or surface it at import.

---

# Retractions — claims from earlier drafts we no longer stand behind

Recorded so reviewers don't chase them. All were refuted by production testing.

| Earlier claim | Status |
|---|---|
| Registry resolution 403s from a gateway-attached engine | ❌ **Refuted** — `list_agents()` in-engine returned 10 agents and built a `RemoteA2aAgent`. Our original 403 was a **grant gap** (`gcp-agentregistry`, all 4 variants), which our own IAM script's comments already admit. |
| `Proxy-Authorization` is required for in-engine A2A | ❌ **Refuted** — mtls + `Authorization` alone → 200. |
| `RemoteA2aAgent` can't complete a long-running hop | ❌ **Refuted** — a 180.4s orchestrator hop returned the full 7590-char result. |
| A platform deadline truncates a blocking `message:send` | ❌ **Not reproduced** — held 180s. |
| The gateway refuses `message:stream` | ❌ **Refuted** — raw SSE to `.mtls` → 200 on all three peers. |
| The card's `capabilities.streaming: true` steers clients into a refused path | ❌ **Refuted** — a `streaming=False` target still 403'd. |

The failure that started all of this — `contract_finalize` returning `cleared` with no contract —
is best explained by our own **Finding 3**: `RemoteA2aAgent._construct_message_parts_from_session`
rebuilds the outgoing message from session events and **discards the explicit brief**.

## FINDING D — a blocking `message:send` dies at ~180s, blaming the callee

**Measured in-engine, 2026-08-02.** A `message:send` carrying
`configuration: {blocking: true}` — which is what every stock a2a client sends — held for
**180.2s** and then returned:

```json
{"error": {"code": 400, "status": "FAILED_PRECONDITION",
  "message": "Reasoning Engine Execution failed.\n…\nError Details: "}}
```

No task, no state, and **`Error Details:` empty**. Meanwhile the target engine was working
normally: 62 log lines, dispatching to three peers with trace propagation, writing to the task
store, zero errors. The same request **without** `blocking` returns in **0.9s** with a
`TASK_STATE_SUBMITTED` task, and polling `tasks/{id}` retrieves the completed result.

Three separate runs landed at 180.4s / 180.7s / 180.2s, so the boundary is consistent. We cannot
say whether it is a deadline, a proxy limit, or something in the blocking path — the platform
does not say, and **no timeout/deadline field exists** on `ReasoningEngineSpec.deploymentSpec`
(checked against the live v1beta1 discovery document: `agentGatewayConfig`, `agentServerMode`,
`containerConcurrency`, `env`, `keepAliveProbe`, `maxInstances`, `minInstances`,
`pscInterfaceConfig`, `resourceLimits`, `secretEnv` — nothing else).

**Requested:** (a) don't report a healthy engine's execution as *failed* — the message sends
users hunting a failure that never happened; (b) populate `Error Details`, or return a distinct
status such as `DEADLINE_EXCEEDED`; (c) document the limit, or expose it as deployment config;
(d) ideally, offer a non-blocking mode on the stock client so callers can poll.

## What a user has to build to work around all of this

Both defects (the plain-host card, and the 180s blocking ceiling) are absorbed in one subclass so
call sites stay idiomatic — this is the shape any team on Agent Runtime will end up writing:

```python
class VibeflixRemoteA2aAgent(RemoteA2aAgent):
    async def _resolve_agent_card(self):
        card = await super()._resolve_agent_card()
        card.url = self._mtls_base            # FINDING A: the served card names a host the
        return card                           #            gateway refuses

    def _construct_message_parts_from_session(self, ctx):
        _, context_id = super()._construct_message_parts_from_session(ctx)
        return self._parts_from(ctx.user_content), context_id   # brief, not session history

    async def _run_async_impl(self, ctx):
        if not self._long_running:
            async for e in super()._run_async_impl(ctx):        # stock path
                yield e
            return
        yield await self._send_and_poll(ctx)   # FINDING D: blocking dies at ~180s
```

`long_running=True` is needed on any hop that can exceed ~180s. In our mesh that is `legal`,
`contract_finalize` and `app → orchestrator`; the fast dispatch hops (~9-20s) run the stock path
unchanged.

## Why our workaround exists

`vibeflix_common/a2a_engine.py` calls `{mtls}/v1beta1/{engine}/a2a/v1/message:send` directly and
polls `tasks/{id}`. Given the defect above, **hardcoding the mtls URL is the only reason it works**
— it never reads the card. The poll loop is a separate, independent robustness choice.

> **Note on our own code:** `a2a_engine.py` sends `Proxy-Authorization` in-engine and its comments
> call it required. Measurement says otherwise (single `Authorization` on `.mtls` → 200). Harmless,
> but the comment overstates it; the 401 it was added to fix was most likely the *missing*
> `Authorization` header, which the same change also introduced.

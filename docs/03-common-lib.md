# The `vibeflix-common` shared library

*The plumbing every service shares — what each module does and who uses it.*

> Package: [`packages/vibeflix-common/`](../packages/vibeflix-common/) · import name
> `vibeflix_common`. Installed editable into every service (`pip install -e`).

---

## Why it exists

The mesh is ten independent services (six agents, three MCP servers, one app), but they
all need the *same* non-trivial plumbing: minting Google ID tokens for governed egress,
speaking A2A, connecting to MCP servers, emitting mesh telemetry. Rather than copy that
into every service, it lives here once.

One deliberate design choice: **the package has no hard dependencies.** Each service
installs only the extra it needs, so the two families don't drag in each other's weight:

```toml
[project.optional-dependencies]
agents = ["google-adk[a2a]==2.3.0", "google-genai", "mcp>=1,<2", ...]  # agents + app
mcp    = ["google-cloud-firestore>=2.0.0"]                             # MCP servers
```

So an MCP server never pulls `google-adk`, and an agent never pulls Firestore.

Almost everything here is **gated on `RUN_LOCAL`**: locally (docker-compose) the auth and
governance layers no-op so you can iterate without GCP; in the cloud they engage. That
single switch is why the same code runs in both places.

---

## The layout

Four subpackages. The entry rule is **who imports it** — so you can tell from the path
whether a module is yours to care about:

```
vibeflix_common/
├── a2a/         agent-to-agent transport        → agents, deploy, tests
│   card · compat · engine · remote_agent · serve · task_store
├── agent/       what you build an ADK agent from → agents ONLY
│   models · mcp_clients · memory · image_input · schema_guard · tool_guard · a2ui_format
├── mcpserver/   MCP-server-only helpers          → mcp_servers ONLY
│   otel
└── platform/    cross-cutting plumbing           → BOTH sides
    cloud_auth · telemetry · registry · health
```

Two placements are worth explaining, because the obvious guess is wrong:

- **`registry` is in `platform/`, not `mcpserver/`.** It reads Firestore for the MCP
  servers *and* for the orchestrator — the orchestrator reads its sourcing caps from the
  same `market_policy/sourcing_caps` doc `mcp_market` serves, so editing the registry
  changes the actual gate rather than just one tool's answer.
- **`telemetry` is in `platform/` too**, for the same reason: `instrument_node` is for
  agents, `instrument_fastmcp` for MCP servers. One module, both consumers.

---

## The modules, by subpackage

### `a2a/` — agent-to-agent transport

| Module | What it does | Used by |
|---|---|---|
| **`a2a.card`** | Builds an `AgentCard` **ourselves** instead of fetching the platform's. `engine_card()`.<br><br>**Why?** The `A2aAgent` template hardcodes the **plain** aiplatform host into the card it serves (`templates/a2a.py:328`), overwriting whatever the deployer set — and the Agent Gateway authorizes only the `.mtls` host, refusing the plain one with `403 Egress request is not authorized`. Standard clients follow `card.url`, so a self-built card is the only way a gateway-attached engine can reach a peer. See [`eng-report/UPSTREAM-FR-a2a-client-gaps.md`](../eng-report/UPSTREAM-FR-a2a-client-gaps.md). | app |
| **`a2a.remote_agent`** | `VibeflixRemoteA2aAgent` — ADK's stock `RemoteA2aAgent` with this mesh's specifics hidden inside, so call sites stay idiomatic. Overrides three things: the mtls repoint, a **brief override** (stock rebuilds the outgoing message from `ctx.session.events` and never sees the brief passed to `ctx.run_node`), and an opt-in `long_running=True` that swaps the stock blocking send for send-and-poll.<br><br>**Why not stock `RemoteA2aAgent`?** For a hop carrying an explicit brief, stock silently sends the wrong message; for a hop over ~180s, its blocking send dies with `400 FAILED_PRECONDITION` while the callee keeps working. | orchestrator |
| **`a2a.engine`** | The **cloud** A2A client: talks directly to Agent-Runtime engines (REST/proto), `POST message:send` then poll to completion. `a2a_engine_send`, `direct_engine_agent`.<br><br>**Why not the prebuilt ADK client for every hop?** Because it sends `blocking: true` — one long HTTP request, which Agent Runtime kills at ~180s. This never makes a long request: non-blocking send, then poll `tasks/{id}`. It is the only transport measured to survive the mesh's long hops (`app → orchestrator`, `contract_finalize`, `vendor_clearance → legal`). The fast hops **do** use the prebuilt client. | app, orchestrator, vendor_clearance |
| **`a2a.serve`** | The **local** counterpart: wraps one domain agent as a standalone A2A service. It's the `Dockerfile.agent` entrypoint (`uvicorn vibeflix_common.a2a.serve:app`). `build_app`.<br><br>**Why not a per-agent uvicorn/Starlette main?** It's one env-driven launcher (`A2A_AGENT` / `PORT` / `A2A_HOST` / `A2A_PROTOCOL`) so every agent shares a single container entrypoint and one correct agent-card config, instead of five near-identical mains that drift apart. | every agent container (compose) |
| **`a2a.task_store`** | **One** A2A task store for the whole engine fleet instead of one-per-replica — the fix for the ~87%-of-polls-404 problem. `RemoteTaskStore`, wired into `A2aAgent(task_store_builder=…)`.<br><br>**Why not ADK's built-in task store?** Its default is in-memory **per replica**, and Agent Runtime has no session affinity — so the `POST` and its poll land on different replicas and ~87% of polls `404`. This is one shared store the whole fleet reads/writes. | `deploy/deploy_agents_a2a.py` (all engines) |
| **`a2a.compat`** | Version-skew bridge — ADK 2.3 imports old `a2a.types` names while the runtime needs `a2a-sdk` 1.x. `ensure()` aliases the missing names and **must run before any `google.adk` import**.<br><br>**Why not just import the libs?** You can't — ADK 2.3 imports `a2a.types` names that `a2a-sdk` 1.x renamed, so any `google.adk` import throws `ImportError` until `ensure()` aliases them. No combination of the two versions coexists natively. | `deploy/deploy_agents_a2a.py` |

### `platform/` — cross-cutting plumbing (agents **and** MCP servers)

| Module | What it does | Used by |
|---|---|---|
| **`platform.cloud_auth`** | The big one. All Google-credential plumbing, gated by `RUN_LOCAL`: mints/pre-warms ID tokens, builds the httpx factories that attach them, resolves A2A RPC URLs, and injects W3C `traceparent`. `run_local()`, `token_for`, `GoogleAuth`, `mcp_httpx_factory`, `a2a_httpx_client`, `resolve_a2a_rpc_url`.<br><br>**Why not `google.auth` directly?** It hands you a credential, not the per-destination *token choice* this needs — an **ID** token (audience = origin) for `*.run.app`/gateway hosts vs an OAuth **access** token for `*.googleapis.com` — plus attach-per-request caching/re-mint, `RUN_LOCAL` auto-detect, and sampled-only traceparent injection. Centralized so no service re-implements it. | app, orchestrator, vendor_clearance, `deploy/make_toolspec.py` |
| **`platform.telemetry`** | Live mesh telemetry → Pub/Sub — the events that light the Workflow graph's tool **LEDs**. `emit_event`, `instrument_node` (agents), `instrument_fastmcp` (MCP servers), `set_run_id`.<br><br>**Why not native?** No native equivalent — this is app-specific: it publishes mesh events to Pub/Sub to drive the frontend graph's LEDs (fire-and-forget, no-op without `PUBSUB_TOPIC`), and `instrument_fastmcp` auto-instruments every MCP tool without editing tool bodies. (Distinct from `mcpserver.otel`, which feeds Cloud Trace, not the UI.) | orchestrator, vendor_clearance, deal_pricing + all 3 MCP servers |
| **`platform.registry`** | Semantic registry reads (vendor/trademark lookups, sourcing caps). `registry_get`.<br><br>**Why not read Firestore directly in each server?** This wraps each read with a **hardcoded fallback** baked into the calling service, so it stays self-contained (works with Firestore unset/unreachable) while the registries can still be edited in Firestore without a redeploy. **In `platform/`, not `mcpserver/`**: the orchestrator reads its volume cap and secondary addendum from the same `market_policy/sourcing_caps` doc `mcp_market` serves, so a registry edit moves the real gate. | orchestrator + mcp_brand_style + mcp_market |
| **`platform.health`** | Handshake-level mesh health probes — the check a `None` report can't give. `probe_mcp_from_env`, `banner`.<br><br>**Why not native?** No native equivalent — an agent's A2A card serves fine even when its MCP tools are dead, so a card ping isn't a real readiness signal. This does the actual handshake (open an MCP session, list tools) against every `MCP_*_URL`. | app |

### `agent/` — what you build an ADK agent from

| Module | What it does | Used by |
|---|---|---|
| **`agent.mcp_clients`** | Connects ADK agents to the decoupled MCP servers over streamable-HTTP, with the cloud auth factory attached. `mcp_toolset()`.<br><br>**Why not native ADK's `McpToolset` directly?** Locally you effectively *do* — the wrapper no-ops under `RUN_LOCAL`. It only earns its keep in the cloud, where the native toolset is flaky and undebuggable, and fixes four things (the first and last **cannot** be expressed as constructor args):<br>• **Auth hijack** — ADK's `_get_mtls_transport` authenticates MCP with the agent's *access* token and silently replaces your `httpx_client_factory`; Cloud Run remote-verifies access tokens → intermittent `401` under the concurrent fan-out. We patch it to `None` so our ID-token factory runs. *(monkeypatch)*<br>• **Right token** — attaches a per-connection, audience-bound **ID** token via `mcp_httpx_factory`; a bare-URL toolset sends nothing to our IAM-gated servers.<br>• **Handshake timeout** — ADK's 5 s default can't cover a cold agent-identity token mint routed through the gateway (surfaces as an opaque `TaskGroup` error that looks like auth); bumped to 60 s + token pre-warmed at import.<br>• **Debuggability** — mcp/ADK flatten the real socket error into `ConnectionError("…unhandled errors in a TaskGroup")`; `_DiagnosticMcpToolset` walks the `__cause__`/`__context__` chain to print the true leaf cause. *(subclass)* | brand_style, vendor_clearance, deal_pricing, legal, orchestrator |
| **`agent.tool_guard`** | Fails **closed**: if an agent's MCP toolset didn't load, the agent refuses rather than answering blind. `make_toolset_health_guard`.<br><br>**Why not native?** No native equivalent — native ADK is the *problem*: when a toolset fails to load it runs the agent **anyway** with no tools, and a compliance agent then answers from the model alone with a clean, confident, *false* verdict (we watched `status:"success", findings:[]` while the MCP was never called). This is the fail-closed check ADK lacks. | brand_style |
| **`agent.models`** | One Gemini model factory for the whole mesh, with a retry policy that survives `429`. `gemini()`.<br><br>**Why not `model="gemini-2.5-flash"` (a bare string)?** That takes ADK's default `retry_options=None`, which gives up almost immediately on `429 RESOURCE_EXHAUSTED` and kills the agent mid-run (measured 11× in two hours, all in deal_pricing's tight reasoning loop). This sets the ADK-recommended `HttpRetryOptions(attempts=5)` once, for everyone. | all 6 agents |
| **`agent.schema_guard`** | Keeps an `output_schema` agent from crashing when the model replies in prose instead of JSON. `make_schema_guard`.<br><br>**Why not native?** No native equivalent — native `output_schema` *raises* a `ValidationError` and aborts the run the moment the model answers in prose (e.g. a greeting in `adk web`). This `after_model_callback` rewrites that prose into a minimal valid instance so the run completes instead of 500-ing. | brand_style |
| **`agent.image_input`** | Builds an agent message that carries a mock-up image for the model to read, and can require an image before the model runs. `image_part`, `content_with_image`, `require_image_before_model`.<br><br>**Why not build `types.Content`/`Part` yourself?** The scheme rule is non-obvious and easy to get wrong: `gs://` travels **by reference** (a Gemini `file_data` part — Vertex loads the bytes), but `http(s)://` must be downloaded and sent **inline** (Vertex returns empty for URLs). This encodes that split plus the require-image gate. | brand_style |
| **`agent.memory`** | Session / artifact services (env-gated) + a scoped Memory Bank builder + context-cache config. `build_session_service`, `build_memory_service(agent_engine_id=…)`, `build_artifact_service`, `build_context_cache_config`.<br><br>**Why not construct `VertexAiSessionService` etc. directly?** It centralizes the choice — Vertex sessions/artifacts when `AGENT_ENGINE_ID`/`ARTIFACTS_BUCKET` are set, in-memory otherwise — and `build_memory_service` takes an **explicit engine id**, so the app can scope its Memory Bank to the *orchestrator's own engine* (the only cross-audit-recall consumer) without a dedicated memory engine or touching anything else. Local dev runs with zero setup. | app |
| **`agent.a2ui_format`** | The **A2UI contract**, wrapping the official `a2ui-agent-sdk`: `render_instruction` (build the agent's prompt from the SDK's own schema), `parse_panel` (heal + validate a reply), `rewrite_ids`, `text_of`.<br><br>**Why wrap the SDK rather than hand-roll the envelope?** The SDK's v0.8 assets *are* the wire format the frontend already renders, so no translation is needed — and `include_schema=True` is what makes the model emit spec-valid A2UI in the first place. The wrapper adds only the two recovery paths measured to be needed (~1 run in 10 each): re-wrapping a dropped `surfaceUpdate` key, and the streaming parser for a block closed one brace short. See [`A2UI.md`](../A2UI.md). | app, ui_renderer, a2ui_surface |

### `mcpserver/` — MCP-server-only

| Module | What it does | Used by |
|---|---|---|
| **`mcpserver.otel`** | OpenTelemetry trace export setup for the MCP servers (cloud-only). `setup_otel`.<br><br>**Why not configure OpenTelemetry inline per server?** This one call both exports to Cloud Trace **and** extracts inbound trace context (W3C `traceparent` + Google's `X-Cloud-Trace-Context`) so each MCP server appears as its **own** node in Application Topology rather than only as agent-side client spans; no-ops locally / when OTel isn't installed. | all 3 MCP servers |

---

## The four that carry the hard-won fixes

Most of this library is glue, but four modules encode fixes for bugs that each cost real
debugging time — worth knowing when you touch them:

- **`agent.mcp_clients`** disables ADK's built-in mTLS transport (`_get_mtls_transport → None`)
  so our ID-token factory runs instead of ADK authenticating MCP with the agent's *access*
  token — which is remote-verified and flaked under concurrency (intermittent MCP `401`).
- **`a2a.engine`** uses a `1.0s` poll pause (`_WORK_PAUSE`), not the original `5s`. Stacked
  across ~6–8 hops that idle time was 61% of a run; the shared task store makes polls
  cheap, so the shorter pause is safe (full audit `121s → ~54s`).
- **`a2a.task_store`** exists *only* because Agent Runtime replicas have no session affinity —
  see [architecture → the shared task store](./02-architecture.md#the-shared-a2a-task-store--the-one-that-looks-broken-until-you-see-it).
- **`platform.cloud_auth`** binds tokens to the engine's certificate and injects `traceparent` only
  when the span context is valid *and* sampled (injecting on an unsampled span collapses a
  68-span trace to 2).

---

> **See also:** [Architecture](./02-architecture.md) for how these modules connect the
> services, and [`deploy/docs/GOTCHAS.md`](../deploy/docs/GOTCHAS.md) for the operational
> rules several of them implement.

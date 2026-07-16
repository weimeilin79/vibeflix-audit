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

## The modules, by concern

### Auth & governed egress

| Module | What it does | Used by |
|---|---|---|
| **`cloud_auth`** | The big one. All Google-credential plumbing, gated by `RUN_LOCAL`: mints/pre-warms ID tokens, builds the httpx factories that attach them, resolves A2A RPC URLs, and injects W3C `traceparent`. `run_local()`, `token_for`, `GoogleAuth`, `mcp_httpx_factory`, `a2a_httpx_client`, `resolve_a2a_rpc_url`.<br><br>**Why not `google.auth` directly?** It hands you a credential, not the per-destination *token choice* this needs — an **ID** token (audience = origin) for `*.run.app`/gateway hosts vs an OAuth **access** token for `*.googleapis.com` — plus attach-per-request caching/re-mint, `RUN_LOCAL` auto-detect, and sampled-only traceparent injection. Centralized so no service re-implements it. | app, orchestrator, vendor_clearance, `deploy/make_toolspec.py` |
| **`a2a_compat`** | Version-skew bridge — ADK 2.3 imports old `a2a.types` names while the runtime needs `a2a-sdk` 1.x. `ensure()` aliases the missing names and **must run before any `google.adk` import**.<br><br>**Why not just import the libs?** You can't — ADK 2.3 imports `a2a.types` names that `a2a-sdk` 1.x renamed, so any `google.adk` import throws `ImportError` until `ensure()` aliases them. No combination of the two versions coexists natively. | `deploy/deploy_agents_a2a.py` |

### A2A — agent-to-agent transport

| Module | What it does | Used by |
|---|---|---|
| **`a2a_engine`** | The **cloud** A2A client: talks directly to Agent-Runtime engines (REST/proto), `POST message:send` then poll to completion. `a2a_engine_send`, `direct_engine_agent`.<br><br>**Why not ADK's `RemoteA2aAgent` / `AgentRegistry.get_remote_a2a_agent`?** From a gateway-attached engine, registry resolution must call `agentregistry.mtls` *outbound*, which the gateway filters → `403`. This calls the target engine's endpoint directly (**inbound** to the target, not egress), so any caller with aiplatform access works — app SA and agent identities alike. | app, orchestrator, vendor_clearance |
| **`serve_a2a`** | The **local** counterpart: wraps one domain agent as a standalone A2A service. It's the `Dockerfile.agent` entrypoint (`uvicorn vibeflix_common.serve_a2a:app`). `build_app`.<br><br>**Why not a per-agent uvicorn/Starlette main?** It's one env-driven launcher (`A2A_AGENT` / `PORT` / `A2A_HOST` / `A2A_PROTOCOL`) so every agent shares a single container entrypoint and one correct agent-card config, instead of five near-identical mains that drift apart. | every agent container (compose) |
| **`registry_client`** | Resolves a cloud A2A agent through the **Agent Registry** (cloud-only), the counterpart to the local `RemoteA2aAgent` wiring. `registry_remote_agent`.<br><br>**Why not a plain `RemoteA2aAgent(agent_card=<url>)`?** Cloud engines speak the platform's REST/proto A2A dialect with no `/a2a/v1/card` route (JSON-RPC vs proto), so a raw-URL agent can't reach them. The SDK's registry lookup returns a `RemoteA2aAgent` pre-wired with the right client + agent-identity auth. | cloud A2A resolution path |
| **`task_store`** | **One** A2A task store for the whole engine fleet instead of one-per-replica — the fix for the ~87%-of-polls-404 problem. `RemoteTaskStore`, wired into `A2aAgent(task_store_builder=…)`.<br><br>**Why not ADK's built-in task store?** Its default is in-memory **per replica**, and Agent Runtime has no session affinity — so the `POST` and its poll land on different replicas and ~87% of polls `404`. This is one shared store the whole fleet reads/writes. | `deploy/deploy_agents_a2a.py` (all engines) |

### MCP — agent-to-tools connectivity

| Module | What it does | Used by |
|---|---|---|
| **`mcp_clients`** | Connects ADK agents to the decoupled MCP servers over streamable-HTTP, with the cloud auth factory attached. `mcp_toolset()`.<br><br>**Why not native ADK's `McpToolset` directly?** Locally you effectively *do* — the wrapper no-ops under `RUN_LOCAL`. It only earns its keep in the cloud, where the native toolset is flaky and undebuggable, and fixes four things (the first and last **cannot** be expressed as constructor args):<br>• **Auth hijack** — ADK's `_get_mtls_transport` authenticates MCP with the agent's *access* token and silently replaces your `httpx_client_factory`; Cloud Run remote-verifies access tokens → intermittent `401` under the concurrent fan-out. We patch it to `None` so our ID-token factory runs. *(monkeypatch)*<br>• **Right token** — attaches a per-connection, audience-bound **ID** token via `mcp_httpx_factory`; a bare-URL toolset sends nothing to our IAM-gated servers.<br>• **Handshake timeout** — ADK's 5 s default can't cover a cold agent-identity token mint routed through the gateway (surfaces as an opaque `TaskGroup` error that looks like auth); bumped to 60 s + token pre-warmed at import.<br>• **Debuggability** — mcp/ADK flatten the real socket error into `ConnectionError("…unhandled errors in a TaskGroup")`; `_DiagnosticMcpToolset` walks the `__cause__`/`__context__` chain to print the true leaf cause. *(subclass)* | brand_style, vendor_clearance, deal_pricing, legal, orchestrator |
| **`tool_guard`** | Fails **closed**: if an agent's MCP toolset didn't load, the agent refuses rather than answering blind. `make_toolset_health_guard`.<br><br>**Why not native?** No native equivalent — native ADK is the *problem*: when a toolset fails to load it runs the agent **anyway** with no tools, and a compliance agent then answers from the model alone with a clean, confident, *false* verdict (we watched `status:"success", findings:[]` while the MCP was never called). This is the fail-closed check ADK lacks. | brand_style |

### Model & agent-behavior helpers

| Module | What it does | Used by |
|---|---|---|
| **`models`** | One Gemini model factory for the whole mesh, with a retry policy that survives `429`. `gemini()`.<br><br>**Why not `model="gemini-2.5-flash"` (a bare string)?** That takes ADK's default `retry_options=None`, which gives up almost immediately on `429 RESOURCE_EXHAUSTED` and kills the agent mid-run (measured 11× in two hours, all in deal_pricing's tight reasoning loop). This sets the ADK-recommended `HttpRetryOptions(attempts=5)` once, for everyone. | all 6 agents |
| **`schema_guard`** | Keeps an `output_schema` agent from crashing when the model replies in prose instead of JSON. `make_schema_guard`.<br><br>**Why not native?** No native equivalent — native `output_schema` *raises* a `ValidationError` and aborts the run the moment the model answers in prose (e.g. a greeting in `adk web`). This `after_model_callback` rewrites that prose into a minimal valid instance so the run completes instead of 500-ing. | brand_style |
| **`image_input`** | Builds an agent message that carries a mock-up image for the model to read, and can require an image before the model runs. `image_part`, `content_with_image`, `require_image_before_model`.<br><br>**Why not build `types.Content`/`Part` yourself?** The scheme rule is non-obvious and easy to get wrong: `gs://` travels **by reference** (a Gemini `file_data` part — Vertex loads the bytes), but `http(s)://` must be downloaded and sent **inline** (Vertex returns empty for URLs). This encodes that split plus the require-image gate. | brand_style |

### Telemetry & health

| Module | What it does | Used by |
|---|---|---|
| **`telemetry`** | Live mesh telemetry → Pub/Sub — the events that light the Workflow graph's tool **LEDs**. `emit_event`, `instrument_node` (agents), `instrument_fastmcp` (MCP servers), `set_run_id`.<br><br>**Why not native?** No native equivalent — this is app-specific: it publishes mesh events to Pub/Sub to drive the frontend graph's LEDs (fire-and-forget, no-op without `PUBSUB_TOPIC`), and `instrument_fastmcp` auto-instruments every MCP tool without editing tool bodies. (Distinct from `otel`, which feeds Cloud Trace, not the UI.) | orchestrator, vendor_clearance, deal_pricing + all 3 MCP servers |
| **`otel`** | OpenTelemetry trace export setup for the MCP servers (cloud-only). `setup_otel`.<br><br>**Why not configure OpenTelemetry inline per server?** This one call both exports to Cloud Trace **and** extracts inbound trace context (W3C `traceparent` + Google's `X-Cloud-Trace-Context`) so each MCP server appears as its **own** node in Application Topology rather than only as agent-side client spans; no-ops locally / when OTel isn't installed. | all 3 MCP servers |
| **`health`** | Handshake-level mesh health probes — the check a `None` report can't give. `probe_mcp_from_env`, `banner`.<br><br>**Why not native?** No native equivalent — an agent's A2A card serves fine even when its MCP tools are dead, so a card ping isn't a real readiness signal. This does the actual handshake (open an MCP session, list tools) against every `MCP_*_URL`. | app |

### Persistence & registry data

| Module | What it does | Used by |
|---|---|---|
| **`memory`** | Env-gated session / memory / artifact services + context-cache config. `build_session_service`, `build_memory_service`, `build_artifact_service`, `build_context_cache_config`.<br><br>**Why not construct `VertexAiSessionService` etc. directly?** This env-gates the choice — managed Vertex Sessions/Memory/artifacts when `AGENT_ENGINE_ID`/`MEMORY_LOCATION`/`ARTIFACTS_BUCKET` are set, in-memory fallback otherwise — so local dev runs with zero setup, and one shared `APP_NAME` unifies episodic memory across the mesh. | app |
| **`registry`** | Semantic registry reads for the MCP servers (vendor/trademark lookups). `registry_get`.<br><br>**Why not read Firestore directly in each server?** This wraps each read with a **hardcoded fallback** baked into the calling server, so the server stays self-contained (works with Firestore unset/unreachable) while the registries can still be edited in Firestore without a redeploy. | orchestrator + mcp_brand_style + mcp_market |

---

## The four that carry the hard-won fixes

Most of this library is glue, but four modules encode fixes for bugs that each cost real
debugging time — worth knowing when you touch them:

- **`mcp_clients`** disables ADK's built-in mTLS transport (`_get_mtls_transport → None`)
  so our ID-token factory runs instead of ADK authenticating MCP with the agent's *access*
  token — which is remote-verified and flaked under concurrency (intermittent MCP `401`).
- **`a2a_engine`** uses a `1.0s` poll pause (`_WORK_PAUSE`), not the original `5s`. Stacked
  across ~6–8 hops that idle time was 61% of a run; the shared task store makes polls
  cheap, so the shorter pause is safe (full audit `121s → ~54s`).
- **`task_store`** exists *only* because Agent Runtime replicas have no session affinity —
  see [architecture → the shared task store](./02-architecture.md#the-shared-a2a-task-store--the-one-that-looks-broken-until-you-see-it).
- **`cloud_auth`** binds tokens to the engine's certificate and injects `traceparent` only
  when the span context is valid *and* sampled (injecting on an unsampled span collapses a
  68-span trace to 2).

---

> **See also:** [Architecture](./02-architecture.md) for how these modules connect the
> services, and [`deploy/docs/GOTCHAS.md`](../deploy/docs/GOTCHAS.md) for the operational
> rules several of them implement.

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
| **`cloud_auth`** | The big one. All Google-credential plumbing, gated by `RUN_LOCAL`: mints/pre-warms ID tokens, builds the httpx factories that attach them, resolves A2A RPC URLs, and injects W3C `traceparent`. `run_local()`, `token_for`, `GoogleAuth`, `mcp_httpx_factory`, `a2a_httpx_client`, `resolve_a2a_rpc_url`. | app, orchestrator, vendor_clearance, `deploy/make_toolspec.py` |
| **`a2a_compat`** | Version-skew bridge — ADK 2.3 imports old `a2a.types` names while the runtime needs `a2a-sdk` 1.x. `ensure()` aliases the missing names and **must run before any `google.adk` import**. | `deploy/deploy_agents_a2a.py` |

### A2A — agent-to-agent transport

| Module | What it does | Used by |
|---|---|---|
| **`a2a_engine`** | The **cloud** A2A client: talks directly to Agent-Runtime engines (REST/proto), `POST message:send` then poll to completion. `a2a_engine_send`, `direct_engine_agent`. | app, orchestrator, vendor_clearance |
| **`serve_a2a`** | The **local** counterpart: wraps one domain agent as a standalone A2A service. It's the `Dockerfile.agent` entrypoint (`uvicorn vibeflix_common.serve_a2a:app`). `build_app`. | every agent container (compose) |
| **`registry_client`** | Resolves a cloud A2A agent through the **Agent Registry** (cloud-only), the counterpart to the local `RemoteA2aAgent` wiring. `registry_remote_agent`. | cloud A2A resolution path |
| **`task_store`** | **One** A2A task store for the whole engine fleet instead of one-per-replica — the fix for the ~87%-of-polls-404 problem. `RemoteTaskStore`, wired into `A2aAgent(task_store_builder=…)`. | `deploy/deploy_agents_a2a.py` (all engines) |

### MCP — agent-to-tools connectivity

| Module | What it does | Used by |
|---|---|---|
| **`mcp_clients`** | Connects ADK agents to the decoupled MCP servers over the network (streamable-HTTP), with the cloud auth factory attached. `mcp_toolset()`. | brand_style, vendor_clearance, deal_pricing, legal, orchestrator |
| **`tool_guard`** | Fails **closed**: if an agent's MCP toolset didn't load, the agent refuses rather than answering blind. `make_toolset_health_guard`. | brand_style |

### Model & agent-behavior helpers

| Module | What it does | Used by |
|---|---|---|
| **`models`** | One Gemini model factory for the whole mesh, with a retry policy that survives `429`. `gemini()`. | all 6 agents |
| **`schema_guard`** | Keeps an `output_schema` agent from crashing when the model replies in prose instead of JSON. `make_schema_guard`. | brand_style |
| **`image_input`** | Builds an agent message that carries a mock-up image for the model to read, and can require an image before the model runs. `image_part`, `content_with_image`, `require_image_before_model`. | brand_style |

### Telemetry & health

| Module | What it does | Used by |
|---|---|---|
| **`telemetry`** | Live mesh telemetry → Pub/Sub — the events that light the Workflow graph's tool **LEDs**. `emit_event`, `instrument_node` (agents), `instrument_fastmcp` (MCP servers), `set_run_id`. | orchestrator, vendor_clearance, deal_pricing + all 3 MCP servers |
| **`otel`** | OpenTelemetry trace export setup for the MCP servers (cloud-only). `setup_otel`. | all 3 MCP servers |
| **`health`** | Handshake-level mesh health probes — the check a `None` report can't give. `probe_mcp_from_env`, `banner`. | app |

### Persistence & registry data

| Module | What it does | Used by |
|---|---|---|
| **`memory`** | Env-gated session / memory / artifact services + context-cache config. `build_session_service`, `build_memory_service`, `build_artifact_service`, `build_context_cache_config`. | app |
| **`registry`** | Semantic registry reads for the MCP servers (vendor/trademark lookups). `registry_get`. | orchestrator + mcp_brand_style + mcp_market |

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

# topology.md — cloud security topology (agents, MCP, gateway, IAM)

The approved target state for the pokedemo-test deployment. Everything is
**deny-by-default**: a connection exists only if a grant below creates it.

```
                                   ┌──────────────────────────────┐
 browser ──HTTPS (public) ───────► │ CONSOLE APP  (Cloud Run)      │
                                   │ frontend + FastAPI only       │
                                   │ SA: vibeflix-app              │
                                   └───┬───────────────┬──────────┘
                        A2A via GATEWAY│INGRESS ✅      │ (client-to-agent mode)
                                       ▼               ▼
                             ┌───────────────┐  ┌─────────────┐
                             │ ORCHESTRATOR  │  │ ui_renderer │      6 engines on
                             │  engine #1    │  │  engine #6  │      AGENT RUNTIME,
                             └──┬────┬────┬──┘  └─────────────┘      each with its own
                         A2A ✅ │    │    │  (fan-out — the ONLY     AGENT IDENTITY
               ┌────────────────┘    │    │   caller of the 3
               ▼                     ▼    └──────────┐  domain agents)
         brand_style       vendor_clearance      deal_pricing
          engine #2           engine #3            engine #4
               │                 │  │                  │
               │                 │  └── A2A ✅ ─► legal (engine #5)
               │                 │        (ONLY vendor_clearance may)
               ▼                 ▼                     ▼
         ════════ AGENT GATEWAY · mTLS/PSC · IAP policies (egress) ════════
               ▼                 ▼                     ▼
        mcp-brand-style   mcp-licensing + mcp-market      (Cloud Run: only the
                                 ▲                         invoker SA may invoke)
   app ── direct MCP, plain IAM ─┘  (read-set; the app cannot ride mTLS/PSC)
```

## A2A matrix (agent-to-agent, deny-by-default)

| Caller | May call | Enforced by |
|---|---|---|
| console app | orchestrator, ui_renderer | gateway **client-to-agent ingress** on those 2 engines (⚠️ ingress governs only `query`/`streamQuery`) |
| orchestrator | brand_style, vendor_clearance, deal_pricing | egress grants to the 3 agents' registry entries |
| vendor_clearance | legal | ONE egress grant (endpoint-scoped IAP binding) |
| everyone else | nothing | no grant = denied |

## MCP matrix (through the gateway, per deploy/policies.yaml)

| Caller | Server | Tools |
|---|---|---|
| brand_style | mcp-brand-style | `run_brand_audit` |
| deal_pricing | mcp-licensing | `get_license_pricing` |
| vendor_clearance | mcp-licensing | 8 clearance/onboarding tools |
| vendor_clearance | mcp-market | 3 tools |
| legal | mcp-licensing | 5 tools incl. `upsert_contract` (sole contract writer) |
| **orchestrator** | mcp-licensing | read-only set (its `note_responder` registry Q&A) |
| ui_renderer | — | nothing |
| console app | mcp-licensing | read-set + `dump_stores`/`reset_vendors`/`upsert_contract` (admin stamp) — **direct IAM**, not gateway |

## Identities & roles (how to make it happen)

| Identity | Kind | Roles / grants |
|---|---|---|
| 6 × agent principals (`principal://…/reasoningEngines/<id>`) | Agent Identity (enabled per engine, v1beta1 `identity_type`) | baseline via `principalSet://…/projects/<PN>`: `roles/aiplatform.expressUser`, `roles/serviceusage.serviceUsageConsumer`, `roles/browser`; topic-scoped `roles/pubsub.publisher` on `vibeflix-mesh-events`; per-agent `roles/iap.egressor` bindings (tool CEL per matrix above; endpoint-scoped for the A2A rows) |
| `vibeflix-mcp-invoker` SA | plain SA (gateway backend egress; passed at engine attach) | `roles/run.invoker` on the 3 MCP Cloud Run services — **the only invoker** |
| `vibeflix-mcp-licensing` SA | MCP runtime (licensing service) | `roles/datastore.user` (vendors CRUD), topic-scoped `pubsub.publisher`, `roles/cloudtrace.agent` (OTel spans) |
| `vibeflix-mcp-readonly` SA | MCP runtime (market + brand-style) | `roles/datastore.viewer`, topic-scoped `pubsub.publisher`, `roles/cloudtrace.agent` (OTel spans) |
| `vibeflix-app` SA | console app (Cloud Run) | `roles/aiplatform.user` (reach the gateway-governed engines), `roles/datastore.user` (audit history), `roles/storage.objectAdmin` on the upload bucket, `roles/pubsub.publisher` (topic) + `subscriber` on `vibeflix-mesh-events-app-cloud`, `roles/run.invoker` on mcp-licensing (direct read-set) |
| your user | operator | temporary `run.invoker` for step-2 verification — **remove after 4e works** |

Enforcement layers, outermost first:
1. **Cloud Run IAM** — only `vibeflix-mcp-invoker` (+ app on licensing) can invoke the MCP services at all.
2. **Agent Gateway (egress)** — every agent's outbound MCP/A2A call is mTLS-identified, then
3. **IAP `REQUEST_AUTHZ`** evaluates the `roles/iap.egressor` bindings (CEL on `mcp.toolName`; endpoint-scoped for A2A) — deny-by-default.
4. **Gateway ingress (client-to-agent)** — the app's calls to orchestrator/ui_renderer are gateway-governed too (demo choice; note the query/streamQuery-only limitation).
5. **Registry** — destinations not registered in Agent Registry are blocked outright.

## Verified deployment facts (learned live, 2026-07-10)

These are the non-obvious truths a fresh run must respect — none are in Google's docs:

- **Two `A2aAgent` classes.** Use `vertexai.preview.reasoning_engines.A2aAgent`
  (works with a2a-sdk 0.3.x + google-adk 2.3), NOT
  `vertexai.agent_engines.templates.a2a.A2aAgent` (needs a2a-sdk ≥1.0, which
  breaks ADK). `deploy_agents_a2a.py` uses the preview class.
- **Engine config:** `identity_type=AGENT_IDENTITY` and `service_account` are
  MUTUALLY EXCLUSIVE (400 if both). Identity wins → engines run as their own
  `principal://…` and get baseline roles via the step-3a `principalSet://…`
  grant, not via a per-engine SA.
- **`extra_packages`** ships root-relative dir names only; `vibeflix_common`
  must be copied to the repo root at deploy time (nested `packages/…` paths fail
  in-engine with `No module named vibeflix_common`).
- **`.gitignore` must anchor** `/vibeflix_common/` (root only) — an unanchored
  pattern excludes the real `packages/vibeflix-common/vibeflix_common/` from
  Cloud Build uploads, silently shipping an empty package.
- **Engine A2A is REST/proto**, not JSON-RPC: `POST …/<engine>/a2a/v1/message:send`
  with a PROTO body (`role:ROLE_USER`, `content:[{text}]` — NOT pydantic `parts`),
  then poll `…/a2a/v1/tasks/{id}`. There is NO `/a2a/v1/card` route in this
  generation (card 404 is normal). The orchestrator's `RemoteA2aAgent`/JSON-RPC
  client therefore CANNOT call these engines yet — a REST/proto client shim is
  the outstanding code task before end-to-end audits work.
- **Gateway attachment** = PATCH `spec.deploymentSpec.agentGatewayConfig`
  (`agentToAnywhereConfig.agentGateway`). Verify with the GET (describe)
  endpoint — the LIST endpoint omits `deploymentSpec` and always reads null.
- **IAP policies** created via `gcloud iap web add-iam-policy-binding` at PROJECT
  scope enforce correctly but DON'T appear on the console's Agent-Platform
  Policies page (that page shows per-registry-resource bindings —
  `--resource-type=agent-registry --endpoint=<id>` is the console-visible form).
- **Gateway is default-deny for Google's OWN endpoints** — register + grant
  egress to aiplatform/telemetry/logging/pubsub BEFORE attaching, or agents lose
  Gemini/telemetry.
- **Attribute keys** (codelab-verbatim): `mcp.toolName` (camelCase),
  `mcp.tool.isReadOnly`. There is NO documented `mcp.server` attribute — tool
  names are unique across the 3 servers, so tool-name scoping is sufficient.

## Local development — unaffected

The compose mesh keeps running exactly as today: `RUN_LOCAL` auto-detect keeps
every hop plain-http, the orchestrator runs **in-process in the app** locally
(the engine split is cloud-only — the app keeps its ADK `Runner` path when
local and switches to the remote orchestrator engine when deployed), and no
gateway/IAM exists locally. The one code prerequisite this adds: the app needs
that runner-vs-remote-orchestrator switch before step 5 of the cloud runbooks.

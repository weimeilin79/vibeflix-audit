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

## Local development — unaffected

The compose mesh keeps running exactly as today: `RUN_LOCAL` auto-detect keeps
every hop plain-http, the orchestrator runs **in-process in the app** locally
(the engine split is cloud-only — the app keeps its ADK `Runner` path when
local and switches to the remote orchestrator engine when deployed), and no
gateway/IAM exists locally. The one code prerequisite this adds: the app needs
that runner-vs-remote-orchestrator switch before step 5 of the cloud runbooks.

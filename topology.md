# topology.md — cloud security topology (agents, MCP, gateway, IAM)

> Operational rules (never delete an engine, the two A2A hosts, the invoker-SA
> impersonation, `principalSet` matching nothing) live in
> **[`deploy/docs/GOTCHAS.md`](deploy/docs/GOTCHAS.md)** — the single source of truth.
> This file is the *topology*: who may call whom, and what enforces it.


The approved target state for the pokedemo-test deployment. Everything is
**deny-by-default**: a connection exists only if a grant below creates it.

```
                                   ┌──────────────────────────────┐
 browser ──HTTPS (public) ───────► │ CONSOLE APP  (Cloud Run)      │
                                   │ frontend + FastAPI only       │
                                   │ SA: vibeflix-app              │
                                   └───┬───────────────┬──────────┘
                    DIRECT A2A (plain IAM │ — NOT the gateway; see the A2A matrix)
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
| console app | orchestrator, ui_renderer | ⚠️ **NOT the gateway — plain IAM.** See below. |
| orchestrator | brand_style, vendor_clearance, deal_pricing | egress grants to the 3 agents' registry entries |
| vendor_clearance | legal | ONE egress grant (endpoint-scoped IAP binding) |
| everyone else | nothing | no grant = denied |

> ⚠️ **The app→engine hop is NOT governed by the gateway.** This row used to claim
> "client-to-agent ingress"; that is wrong and the doc misled us for a while. Per Google's
> Agent Gateway docs, **IAM is not enforced and IAP is not supported during ingress**, and
> ingress can only govern `query`/`streamQuery` — which these engines do not even expose
> (`api_mode=a2a_extension` ⇒ only `on_message_send`). What actually authorizes the app is
> its own **project-level IAM** (`roles/aiplatform.user` + `roles/aiplatform.agentContextEditor`)
> on a DIRECT A2A call (`vibeflix_common/a2a_engine.py`). The gateway governs **EGRESS only**
> — agent→agent, agent→MCP, agent→Google API, agent→task store. That is still the whole
> demo; it just isn't ingress.
>
> Also note the console app itself is deployed `--allow-unauthenticated` (the browser has to
> load it), so **anyone with the URL can run an audit**. Only the task-store endpoints are
> gated (shared secret). Fine for a demo; not a security boundary.

## Shared A2A task store (every engine → the app)

| Caller | May call | Enforced by |
|---|---|---|
| **all 6 agents** | `vibeflix-app` `/api/taskstore/*` | `gcp-vibeflix-app` registry Service + `roles/iap.egressor` on it (granted by `grant_agent_iam.sh` step 0+2), and `run.invoker` for `vibeflix-mcp-invoker` |

**Why:** the A2A task store used to be in-memory **per replica**, so `GET /a2a/v1/tasks/{id}`
missed **86.8%** of the time. The engines now persist tasks in the app
(`vibeflix_common/task_store.py`). Full story + the two load-bearing constraints (one app
instance; the shared-secret gate):
[G3](deploy/docs/GOTCHAS.md#g3--the-engines-are-deployed-twice-with-the-app-in-between) ·
[G5](deploy/docs/GOTCHAS.md#g5--the-app-must-be---min-instances1---max-instances1) ·
[G8](deploy/docs/GOTCHAS.md#g8--the-agent-gateway-governs-http-egress-only).

**Auth is the MCP story reused verbatim** — an AGENT_IDENTITY engine has no service account, so
it impersonates `MCP_INVOKER_SA` to mint an audience-bound ID token
([G9](deploy/docs/GOTCHAS.md#g9--an-agent_identity-engine-has-no-service-account)). HTTPS is the
*only* reason it works at all ([G8](deploy/docs/GOTCHAS.md#g8--the-agent-gateway-governs-http-egress-only)).

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
| 6 × agent principals (`principal://…/reasoningEngines/<id>`) | Agent Identity (set at create, `identity_type=AGENT_IDENTITY`) | ⚠️ **grant to the SPECIFIC `principal://`, never `principalSet://`** — a principalSet binds without error and **matches nothing** ([G10](deploy/docs/GOTCHAS.md#g10--principalset-grants-do-not-match-agent-identities)). Project roles: `aiplatform.user`, `aiplatform.agentDefaultAccess`, **`aiplatform.agentContextEditor`** ([G12](deploy/docs/GOTCHAS.md#g12--rolesaiplatformagentcontexteditor-is-required--and-easy-to-forget)), `agentregistry.viewer`, `logging.logWriter`, `monitoring.metricWriter`, `browser`; topic-scoped `pubsub.publisher` on `vibeflix-mesh-events`; `iam.serviceAccountTokenCreator` on the MCP invoker SA ([G9](deploy/docs/GOTCHAS.md#g9--an-agent_identity-engine-has-no-service-account)); per-agent `iap.egressor` (tool CEL per the matrix above). Audit with `./deploy/verify_deployment.sh 4s`. |
| `vibeflix-mcp-invoker` SA | plain SA — how an agent identity authenticates to Cloud Run ([G9](deploy/docs/GOTCHAS.md#g9--an-agent_identity-engine-has-no-service-account)) | **no project roles.** `roles/run.invoker` on the 3 MCP services **and on `vibeflix-app`** (the shared task store). Each agent principal holds `iam.serviceAccountTokenCreator` on it. |
| `vibeflix-mcp-licensing` SA | MCP runtime (licensing) | `roles/datastore.user` (vendors CRUD), `roles/cloudtrace.agent`; topic-scoped `pubsub.publisher` on `vibeflix-mesh-events` |
| `vibeflix-mcp-readonly` SA | MCP runtime (market + brand-style) | `roles/datastore.viewer` (least privilege), `roles/cloudtrace.agent`; topic-scoped `pubsub.publisher` |
| `vibeflix-app` SA | console app (Cloud Run) | `roles/aiplatform.user`, **`roles/aiplatform.agentContextEditor`** ([G12](deploy/docs/GOTCHAS.md#g12--rolesaiplatformagentcontexteditor-is-required--and-easy-to-forget) — without it every task poll 401s and the slow agents hang forever), `roles/aiplatform.agentDefaultAccess`, `roles/agentregistry.viewer`, `roles/datastore.user`; topic-scoped `pubsub.publisher` + `pubsub.subscriber` on `vibeflix-mesh-events-app-cloud`; `storage.objectAdmin` on `gs://vibeflix-request-image` |
| your user | operator | `run.invoker` on the 3 MCP services — still granted, used for step-2 verification |

### ⚠️ Cruft currently in the cluster (documented so it isn't mistaken for design)

Real, verified against `pokedemo-test` today. None of it breaks anything; all of it is
over-privilege or dead weight that a fresh deploy should NOT reproduce:

| what | why it's there | action |
|---|---|---|
| `vibeflix-app` SA holds project-level **`roles/pubsub.editor`** | granted for a per-instance mesh subscription that was **reverted**. The app already has topic-scoped `publisher` + subscription-scoped `subscriber`, which is all it needs. | **remove** — it is unused over-privilege |
| **`vibeflix-agents` SA** still exists (topic `publisher`, bucket `objectViewer`) | the pre-Agent-Identity shared service account. The engines now run as **agent identities** and never use it. | dead — remove once confirmed unused |
| the MCP invoker SA has 12 `tokenCreator` members for 6 agents | **NOT cruft** — 6 are the live engine principals, 1 is a platform `principalSet://`, and **5 are Google-managed service agents** (`gcp-sa-agentgateway`, `gcp-sa-iap`, `gcp-sa-ns-authz`, `gcp-sa-dep`). | **leave them alone** — removing the service agents would likely break the gateway |
| operator (`user:…`) still holds `run.invoker` on the 3 MCPs | step-2 verification grant | fine to keep for a demo; remove for a locked-down environment |


Enforcement layers, outermost first:
1. **Cloud Run IAM** — only `vibeflix-mcp-invoker` (+ app on licensing) can invoke the MCP services at all.
2. **Agent Gateway (egress)** — every agent's outbound MCP/A2A call is mTLS-identified, then
3. **IAP `REQUEST_AUTHZ`** evaluates the `roles/iap.egressor` bindings (CEL on `mcp.toolName`; endpoint-scoped for A2A) — deny-by-default.
4. ~~Gateway ingress (client-to-agent)~~ — **NOT enforced.** IAM is not applied and IAP is not supported during ingress, and ingress can only govern `query`/`streamQuery`, which these `a2a_extension` engines do not expose. The app→engine hop is authorized by the app's own project IAM on a DIRECT A2A call. The gateway governs **EGRESS only**.
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
every hop plain-http, and no gateway/IAM exists locally.

**The orchestrator is its OWN container locally too** (`orchestrator`, :8006) — it is no
longer in-process in the app. The app is a **thin client** in both worlds: it calls the
orchestrator over A2A exactly the way it calls ui_renderer, so what you exercise locally is
the same topology you deploy. (The in-process ADK `Runner` path survives only as a fallback
when `ORCHESTRATOR_A2A_URL` is unset.)

The one code prerequisite this adds: the app needs
that runner-vs-remote-orchestrator switch before step 5 of the cloud runbooks.

## Token Exchange & Routing Flow (Gateway Egress)

Here is a sequence and flow diagram explaining how the tokens are obtained, routed, and translated from the Reasoning Engine to the MCP server on Cloud Run:

```text
+-------------------------------------------------------------------------------------------------+
|                                     TOKEN EXCHANGE & ROUTING                                    |
+-------------------------------------------------------------------------------------------------+

 [ Vertex AI Reasoning Engine ]
         (Agent Container)
                |
                | 1. Read Workload Identity credentials (metadata server)
                v
       [ google.auth.default() ]
                |
                | 2. Obtain federated OAuth2 Access Token (ya29...)
                v
       [ cloud_auth.py Hook ]
                |
                | 3. Set Proxy-Authorization: Bearer <Access Token>
                |    (Keep Authorization header empty)
                |
                v  (DNS routes to PSC IP of Agent Gateway)
 +------------------------------------------------------------------------------------------------+
 | [ Agent Gateway (IAP Egress Proxy) ]                                                           |
 |                                                                                                |
 |  4. Authenticate & Authorize:                                                                  |
 |     IAP validates the Access Token. Checks if the agent principal has                          |
 |     the `roles/iap.egressor` role on the target registry endpoint.                             |
 |                                                                                                |
 |  5. Strip Proxy Header:                                                                        |
 |     Proxy-Authorization header is stripped from the outgoing request.                          |
 |                                                                                                |
 |  6. Sign outbound request:                                                                     |
 |     Gateway mints a standard Google OIDC ID Token (signed by google.com)                       |
 |     for the target Cloud Run service audience using the gateway's service account.             |
 |     Attaches: Authorization: Bearer <Google OIDC ID Token>                                     |
 +------------------------------------------------------------------------------------------------+
                |
                v  (Request sent over public internet or VPC)
 [ Cloud Run Backend (MCP Server) ]
                |
                | 7. Validate Invocation:
                |    Cloud Run verifies the OIDC ID Token signature against google.com.
                |    Checks that the gateway's service account has `roles/run.invoker` on the service.
                v
        [ 200 OK Response ]
```


# Deploying the Vibeflix audit mesh

> ⚠️ **[`GOTCHAS.md`](GOTCHAS.md) is the single source of truth for the hard-won rules.**
> This file is the *contract*: what the services are and which env vars wire them.


The system is split into **10 independently deployable services**:

| Service | Role | Protocol | Local port |
|---|---|---|---|
| `app` | frontend (static) + FastAPI — a **thin A2A client** (it calls `orchestrator` exactly the way it calls `ui_renderer`) + the **shared A2A task store** (`/api/taskstore/*`) | HTTP | 8000 |
| `orchestrator` | Sourcing Orchestrator — an **independent agent** (deterministic Workflow graph). It fans out to the 3 domain agents **under its own agent identity**, so the gateway's A2A egress policies are genuinely in the path. It is NOT a library inside the app. | A2A/HTTP | 8006 |
| `brand_style` | Brand Style agent (A2A **server**) | A2A/HTTP | 8001 |
| `vendor_clearance` | Vendor & Licensing Clearance agent (A2A **server**) | A2A/HTTP | 8002 |
| `deal_pricing` | Deal Pricing agent (A2A **server**) | A2A/HTTP | 8003 |
| `ui_renderer` | A2UI presenter agent (A2A **server**) | A2A/HTTP | 8004 |
| `legal` | Legal Clearance agent (private to vendor_clearance) | A2A/HTTP | 8005 |
| `mcp_licensing` | Vendor/trademark/exclusivity/contract registry MCP server | streamable-HTTP | 9002 |
| `mcp_market` | Market & telemetry MCP server | streamable-HTTP | 9003 |
| `mcp_brand_style` | Brand compliance checks (typo, printed-medium, asset-source) | streamable-HTTP | 9004 |

Wiring is entirely by environment variable, so the same images run locally
(compose) or on Cloud Run.

```
   app ──A2A──> orchestrator ──A2A──> brand_style      ──HTTP──> mcp_brand_style
   app ──A2A──> ui_renderer               (reports → A2UI panels, no MCP)
                             ──A2A──> vendor_clearance ──HTTP──> mcp_licensing, mcp_market
                                      vendor_clearance ──A2A───> legal ──HTTP──> mcp_licensing
                             ──A2A──> deal_pricing     ──HTTP──> mcp_licensing

   every engine ──HTTPS──> app /api/taskstore/*   (the SHARED A2A task store)
```

## Environment contract

**app** (thin A2A client + the shared A2A task store)
- `ORCHESTRATOR_A2A_URL`, `UI_RENDERER_A2A_URL` — the app is a **thin client**: it calls the orchestrator over A2A exactly as it calls ui_renderer. (`BRAND_STYLE_A2A_URL` etc. remain for the readiness probe / local fallback.)
- `PORT` — serves UI + `/api/*`.
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI=true` — the app calls Gemini for the A2UI presenter fallback, so it needs Vertex access. On Cloud Run its SA needs `roles/aiplatform.user` **and `roles/aiplatform.agentContextEditor`** (without the latter, `GET /a2a/v1/tasks/{id}` 401s and the slow agents appear to hang forever).
- `REQUEST_IMAGE_BUCKET` (default `vibeflix-request-image`) — target for `/api/upload`; SA needs write.
- `TASK_STORE_KEY` — shared secret gating `/api/taskstore/*`. The app is deployed
  `--allow-unauthenticated` (the browser must load the console), so without it the agents'
  A2A task state would be world-readable and world-writable.
- ⚠️ **`--min-instances=1 --max-instances=1` is LOAD-BEARING, not cost control.** The task
  store is a dict in this process: a second app instance splits it and every task poll that
  lands on the wrong one 404s — the exact bug the store exists to kill. One instance also
  keeps the Pub/Sub mesh subscription on a single consumer (a subscription is a
  *competing-consumer* queue — 2+ instances split the telemetry and the console's workflow
  graph renders only a fraction of its nodes).

**agents** (`orchestrator` / `brand_style` / `vendor_clearance` / `deal_pricing` / `ui_renderer` / `legal`)
- `A2A_AGENT` — which agent this container serves.
- `A2A_HOST`, `A2A_PROTOCOL`, `PORT` — shape the URL published in the agent card.
- `MCP_BRAND_STYLE_URL` / `MCP_LICENSING_URL` / `MCP_MARKET_URL` — only the groups the agent uses.
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI=true` — Vertex AI.
- `TASK_STORE_URL` + `TASK_STORE_KEY` — where the engine keeps its A2A tasks (the app). Without
  these it silently falls back to a **per-replica** in-memory store and task polls 404 (measured
  86.8% miss rate). See the README's *Shared A2A Task Store*.

**Observability flags** (set in `deploy/.env`, consumed by `deploy/deploy_agents_a2a.py`)

| Flag | Default | What it does |
|---|---|---|
| `TELEMETRY` | **`on` (default)** | OTel traces → Cloud Trace + the console's Observability panel. **The traces ARE the demo — every agent is traced, always.** Only an explicit `TELEMETRY=off` disables it. It used to be *opt-in* (defaulting to `false`), which is a trap: a redeploy that merely FORGOT the flag untraced the whole fleet, reported success and exited 0 — that happened, and every trace vanished silently. The default is now the safe state. Also sets `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` (the switch the console reads for prompt/response content) and forces the gRPC exporter (the HTTP one crashes on the py3.14 base). **Still read the flag back from all six engines after a deploy — never trust the exit code.** |
| `A2A_TRACE_PROPAGATION` | `on` | Propagates the W3C `traceparent` across every A2A hop, so Cloud Trace stitches the mesh into **one** trace and the console's **Agent Platform → Topology** page can draw edges (without it: "No recent trace connections detected"). ⚠️ Only a **valid AND sampled** context is injected — see below. |
| `A2A_SDK_SPANS` | `off` | The A2A SDK's own spans (`a2a.server.*`). **Deliberately off.** They carry **no attributes** (`"attributes": []` — they name no peer and describe no hop), so they cannot populate any topology query, while `EventQueue.dequeue_event` emits one span per 0.5s of *waiting* per in-flight task. Measured with them on: **504 of 560 spans (90%) were A2A plumbing, `dequeue_event` alone 46%**, burying the agent spans. Tested and reverted. |

> **Why `A2A_TRACE_PROPAGATION` guards on the sampling flag.** A first attempt injected the
> `traceparent` unconditionally and made tracing far *worse* — per-engine traces collapsed from
> 68 spans to 2-span fragments — and was reverted as "propagation doesn't work here". **That
> diagnosis was wrong.** A bare `inject()` propagates whatever context is current, *including an
> unsampled one* (`…-00`), and the callee honours that flag and drops nearly all of its own
> spans. The remote parent was never the problem; the sampling bit was. Guarding on
> *valid + sampled* (`vibeflix_common/a2a_engine.py`) gives, measured on one run: **one trace,
> 63 spans, 5 services, 56 agent spans** — richer than the 32-agent-span best case when every
> engine traced itself in isolation.

**mcp servers**
- `MCP_TRANSPORT=streamable-http`, `HOST`, `PORT` — serves MCP at `/mcp`.

## Persistence & memory

**Sessions — durable, automatic, no setup.** Every engine's sessions are backed by its OWN
Agent Engine via `VertexAiSessionService`: Agent Runtime injects `GOOGLE_CLOUD_AGENT_ENGINE_ID`
into each engine, and `deploy/deploy_agents_a2a.py` wires the session service to it. This is
what gives HITL resume and survive-a-replica-restart. Nothing to provision.

**Memory Bank — cross-audit recall, scoped to the orchestrator.** The only consumer of memory
is the note-responder (its `load_memory` tool), and it runs in the **app**. The app backs its
memory with the **orchestrator's own Agent Engine Memory Bank**, resolved automatically from
`ORCHESTRATOR_A2A_URL` (`agents/app.py` → `memory.build_memory_service(agent_engine_id=…)`). So
there is **no dedicated memory engine, no `AGENT_ENGINE_ID`, and no `setup_memory.sh` step** —
deploy the app after the orchestrator (`deploy/deploy_app.sh` sets `ORCHESTRATOR_A2A_URL`) and
it works. `agents/app.py::_persist_audit` writes each finished audit into that Bank, and
`note_responder`'s `load_memory` reads it back across sessions. Locally (no engine URL) it falls
back to in-memory, so `adk web` / `run_local.sh` keep working with zero setup.

The other agents use no Memory Bank, and the app's own sessions stay in-memory (it's a thin
client) — only the orchestrator's cross-audit memory is made durable.

**Artifacts — optional.** Set `ARTIFACTS_BUCKET` on the app to persist reports/images to GCS
(`GcsArtifactService`); unset → in-memory. `ContextCacheConfig` is on regardless.

## Semantic registries (Firestore — Phase 2)

The MCP servers' "what's true" facts — approved media/sources, brand terms, style
guidelines, exclusivity contracts, trademarks, and sourcing caps — are read from
**Firestore** via `vibeflix_common.registry.registry_get`, falling back to the
hardcoded defaults in each server when `FIRESTORE_DATABASE` is unset. So the mesh
runs with no Firestore, and setting one env var makes the registries live-editable
without a redeploy (legal/market read per-request; brand_style at server start).

The same database also stores the **audit history**: the app writes one document per
audit ORDER (a run_token chain of submits — re-submits update the same doc) to the
`audit_history` collection, which backs the console's **Audit History** tab. Falls
back to `data/app/audit_history.jsonl` when `FIRESTORE_DATABASE` is unset/unreachable.

Setup (enables the API, creates the dedicated database, seeds the registries, and
smoke-tests the `audit_history` collection) — config from `deploy/.env`:

```bash
./deploy/setup_firestore.sh          # or: PROJECT=… REGION=… DATABASE=… ./deploy/setup_firestore.sh
```

(`deploy/setup_registry.sh` is a compatibility wrapper for the same script.
Equivalent manual steps: `gcloud firestore databases create --database=vibeflix-registry
--location=us-central1 --type=firestore-native`, then
`GOOGLE_CLOUD_PROJECT=… FIRESTORE_DATABASE=vibeflix-registry python deploy/seed_firestore.py`.)

Enable it:
- **Local:** `export FIRESTORE_DATABASE=vibeflix-registry` before `./run_local.sh mcp`
  (uses your ADC).
- **Mesh/compose:** the **app** service defaults to `vibeflix-registry` for the audit
  history; the registry servers (`mcp_market`, `mcp_brand_style`) opt in
  via `FIRESTORE_DATABASE=vibeflix-registry docker compose up` (var + ADC mount);
  (mcp_licensing's vendors use the same database).
- **Cloud Run:** set `FIRESTORE_DATABASE` on the app + those services; runtime SA needs
  `roles/datastore.user`.

Collections: `brand_style_registry/{brand_terms,printed_media,approved_sources}` (as
`{items:[...]}`), `legal_registry/{style_guidelines_grogu, exclusivity_grogu_<territory>,
trademark_grogu}`, `market_policy/sourcing_caps`, `vendors/{VND-####}` (mcp_licensing's
**CRUD store** — `create_vendor`/`update_vendor` write here, so onboarded vendors and
categories survive restarts; auto-seeded from the in-code defaults on first use, and
`RESET_VENDORS=1 python deploy/seed_firestore.py` restores the pristine records), and
`audit_history/{<order_id>}` (the app's completed audits — inputs, per-workflow reports,
executed contract). Edit a registry doc → the check reflects it (e.g. bump
`market_policy/sourcing_caps.authorized_max_skus` to change the vendor cap).

## Cloud phase 1 — MCP servers on Cloud Run (Terraform)

The three MCP servers run on Cloud Run, owned by **`deploy/terraform/mcp/`** (the
source of truth for the tier — services, runtime SAs, IAM).
`deploy/deploy_mcp_cloudrun.sh` builds the images (Cloud Build) and applies it.

### How to run it

**0. Prerequisites (one-time)**

```bash
gcloud auth login && gcloud auth application-default login
brew tap hashicorp/tap && brew install hashicorp/tap/terraform   # if not installed

./deploy/setup_firestore.sh     # registries + vendors + audit_history live here
./deploy/setup_pubsub.sh        # telemetry topic — Terraform binds publishers to it
```

**1. Pick the project + region.** Both are plain variables; set them in
`deploy/.env` (used by every deploy script):

```bash
PROJECT=pokedemo-test
REGION=us-central1
```

…or override per-run on the command line — no file edits needed:

```bash
PROJECT=my-other-project REGION=europe-west1 ./deploy/deploy_mcp_cloudrun.sh
```

> The Firestore db and Pub/Sub topic must exist in whatever project you target
> (step 0). The local Terraform state tracks ONE deployment at a time — if you
> switch project/region, the next apply builds the new target from scratch
> (destroy the old one first, or use `terraform workspace` to keep both).

**2. Deploy**

```bash
./deploy/deploy_mcp_cloudrun.sh              # gcloud builds ×3 → terraform apply
./deploy/deploy_mcp_cloudrun.sh --no-build   # infra/IAM changes only, reuse images
```

It prints the three MCP endpoints when done (again anytime with
`terraform -chdir=deploy/terraform/mcp output mcp_urls`).

**3. Verify**

```bash
# anonymous must be rejected (IAM-gated):
curl -s -o /dev/null -w '%{http_code}\n' -X POST <MCP_LICENSING_URL>   # → 403
# authenticated reaches the MCP server:
curl -s -o /dev/null -w '%{http_code}\n' -X POST <MCP_LICENSING_URL> \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"       # → 4xx≠403 (handshake, not IAM)
```

**4. Undo everything** (services, IAM, service accounts, image repo):

```bash
terraform -chdir=deploy/terraform/mcp destroy \
  -var project=<PROJECT> -var region=<REGION> -var deployer=user:<you@example.com>
```

### IAM (least privilege — what each server actually touches)

| Service | Runtime SA | IAM |
|---|---|---|
| `vibeflix-mcp-licensing` | `vibeflix-mcp-licensing@…` | `datastore.user` (vendors CRUD) + `pubsub.publisher` on the telemetry topic only |
| `vibeflix-mcp-market` | `vibeflix-mcp-readonly@…` | `datastore.viewer` (registry reads) + topic-scoped `pubsub.publisher` |
| `vibeflix-mcp-brand-style` | `vibeflix-mcp-readonly@…` | same as market |

Deliberately **no GCS / no Vertex** bindings — the MCP servers use neither. All
three deploy `--no-allow-unauthenticated`: callers need `roles/run.invoker` on the
service plus an ID token (`Authorization: Bearer`). Grant the agents' runtime SA
at the agents phase via `TF_VAR_invoker_members='["serviceAccount:…"]'` (or the
`invoker_members` var) and re-apply.

Caveats: `mcp_licensing` keeps trademarks/exclusivity/**contracts** in-memory →
pinned to `max_instances=1`; executed contracts still reset on instance recycle
(the app's audit history snapshots them — durable fix later is moving `_CONTRACTS`
to Firestore). The cloud services publish telemetry to the SAME topic as local —
a locally running app's bridge will consume those events.

## Pub/Sub (live mesh telemetry → the Workflow graph)

Agents, MCP servers, and app functions emit fine-grained events (started ·
tool_call · needs_input · completed · handoff) onto one topic; the app pulls and
relays them to the console, so the Workflow graph renders from REAL mesh signals.
The graph's connections don't change — events only drive each node's state/detail.

```bash
./deploy/setup_pubsub.sh   # enables the API, creates topic + pull subscription, smoke-tests
```

Env contract: `PUBSUB_TOPIC=vibeflix-mesh-events` (emitters),
`PUBSUB_SUBSCRIPTION=vibeflix-mesh-events-app` (the app's bridge). The event JSON
schema lives in the script header — `{run_id, source, node, event, status, detail,
ts}` with `source`/`event` mirrored as message attributes. On Cloud Run, emitters
need `roles/pubsub.publisher` on the topic and the app `roles/pubsub.subscriber`
on the subscription.

**Reset to the original demo state** — either the **Reset database** button in the
console's Audit History tab (calls `POST /api/reset`: default vendors, contracts
cleared, history wiped, uploaded mockups deleted from `gs://vibeflix-request-image`)
or, standalone:

```bash
./deploy/reset_firestore.sh        # registries + vendors + audit_history + uploads (+ local JSONL)
```

## Approved-assets bucket (Cloud Storage)

The `brand_style` agent reads mockup images by **`gs://` reference** (a Gemini
`file_data` `file_uri`) and its `check_asset_source` gate only accepts links from
`_APPROVED_ASSET_SOURCES` (e.g. `gs://vibeflix-approved-assets/`). Create that
bucket **private** — nothing here needs public access:

- **Enforce public access prevention** ✅ — images are loaded server-side by Vertex
  via IAM, never over public HTTP, so public access is unnecessary (and the whole
  point of an "approved source" is a controlled, private bucket).
- **Uniform bucket-level access (UBLA)** ✅ — pairs with the above; disables
  per-object ACLs so nothing can be individually exposed.
- Grant read via **IAM**, not public: give `roles/storage.objectViewer` to the
  identity your app authenticates as (your ADC principal locally, or the Cloud Run
  **runtime service account** in the mesh).

```bash
gcloud storage buckets create gs://vibeflix-approved-assets \
  --project=pokedemo-test --location=us-central1 \
  --uniform-bucket-level-access --public-access-prevention

gcloud storage buckets add-iam-policy-binding gs://vibeflix-approved-assets \
  --member="serviceAccount:<runtime-sa>@pokedemo-test.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

Notes:
- If Vertex reports it can't read the object, also grant `objectViewer` to the
  Vertex AI service agent
  (`service-<project-number>@gcp-sa-aiplatform.iam.gserviceaccount.com`). Start with
  the caller SA and add the service agent only if you hit a permission error.
- Private access only affects **real `gs://` loads**, not the `check_asset_source`
  gate — that just string-matches the URI prefix.
- The code also lists `https://assets.vibeflix.com/` as an approved source, but
  public https URLs are the opposite trust model (Vertex won't load them by
  reference; they get downloaded + inlined). For an all-private setup, standardize
  on `gs://` and drop the https prefix from `_APPROVED_ASSET_SOURCES` in
  `mcp_servers/mcp_brand_style/server.py`.

## Local (docker compose)

```bash
gcloud auth application-default login     # agents call Vertex
./run_local.sh up                         # or: docker compose up --build
# open http://localhost:8000  → "Run Live Audit (Backend)"
```

Local ADC is mounted read-only into the agent containers (see `docker-compose.yml`).

## Cloud Run

Each service becomes one Cloud Run service. Cloud Run injects `$PORT` (8080) and
all entrypoints honor it. Deploy MCP + agents first, then wire their URLs into
the dependents.

```bash
PROJECT=pokedemo-test REGION=us-central1
REPO=us-central1-docker.pkg.dev/$PROJECT/vibeflix

# 1) Build & push images (Cloud Build or local docker buildx)
gcloud builds submit --tag $REPO/mcp-legal     --config /dev/stdin <<< "steps: [{name: gcr.io/cloud-builders/docker, args: [build, -f, deploy/Dockerfile.mcp, --build-arg, GROUP=mcp_legal, -t, $REPO/mcp-legal, .]}]"
# ...repeat for mcp_market, mcp_brand_style (Dockerfile.mcp, different GROUP),
#    the agents (Dockerfile.agent), and app (Dockerfile.app).

# 2) Deploy MCP servers (set MCP_TRANSPORT so they serve HTTP, not stdio)
gcloud run deploy mcp-legal --image $REPO/mcp-legal --region $REGION \
  --set-env-vars MCP_TRANSPORT=streamable-http --allow-unauthenticated
# capture: MCP_LEGAL_URL=https://mcp-legal-XXXX.run.app/mcp   (note the /mcp path)

# 3) Deploy agents — Vertex ADC comes from the runtime service account.
gcloud run deploy brand-style --image $REPO/agent-brand-style --region $REGION \
  --set-env-vars A2A_AGENT=brand_style,A2A_PROTOCOL=https,A2A_PORT=443,\
A2A_HOST=brand-style-XXXX.run.app,\
GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=true,\
MCP_LICENSING_URL=$MCP_LICENSING_URL \
  --allow-unauthenticated
# A2A_HOST must be this service's own *.run.app host so the published agent card
# advertises the externally reachable URL.

# 4) Deploy app with the agent URLs
gcloud run deploy app --image $REPO/app --region $REGION \
  --set-env-vars BRAND_STYLE_A2A_URL=https://brand-style-XXXX.run.app,\
IP_COUNSEL_A2A_URL=https://ip-counsel-XXXX.run.app,\
STORYLINE_A2A_URL=https://storyline-XXXX.run.app \
  --allow-unauthenticated
```

> **Auth note:** `--allow-unauthenticated` keeps the demo simple. To lock it down,
> make the agent/MCP services require invocation and have callers attach an ID
> token (Cloud Run IAM `roles/run.invoker`); pass the token via `McpToolset`
> headers and a `RemoteA2aAgent` `httpx_client` with an auth interceptor.

## Vertex AI Agent Engine (alternative for the agents)

The three domain agents are plain ADK `LlmAgent`s, so each can instead be
deployed to **Agent Engine** (`adk deploy agent_engine` / `agents-cli deploy`).
Agent Engine exposes its own managed endpoint rather than a raw A2A card, so if
you go that route the orchestrator should call those agents through the Agent
Engine client instead of `RemoteA2aAgent`. For a uniform A2A mesh, Cloud Run
(above) is the most direct mapping; mixing Agent Engine is best done one agent at
a time. See `/google-agents-cli-deploy` for the Agent Engine workflow.

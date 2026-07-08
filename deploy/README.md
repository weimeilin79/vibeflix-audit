# Deploying the Vibeflix audit mesh

The system is split into **7 independently deployable services**:

| Service | Role | Protocol | Local port |
|---|---|---|---|
| `app` | frontend (static) + FastAPI + Sourcing Orchestrator (A2A **client**) | HTTP | 8000 |
| `brand_style` | Brand Style agent (A2A **server**) | A2A/HTTP | 8001 |
| `ip_counsel` | IP Counsel agent (A2A **server**) | A2A/HTTP | 8002 |
| `storyline` | Storyline agent (A2A **server**) | A2A/HTTP | 8003 |
| `mcp_vision_ui` | Mockup parse + A2UI canvas helpers | streamable-HTTP | 9001 |
| `mcp_legal` | Legal/compliance MCP server | streamable-HTTP | 9002 |
| `mcp_market` | Market & telemetry MCP server | streamable-HTTP | 9003 |
| `mcp_brand_style` | Brand compliance checks (typo, printed-medium, asset-source) | streamable-HTTP | 9004 |

Wiring is entirely by environment variable, so the same images run locally
(compose) or on Cloud Run.

```
orchestrator ──A2A──> brand_style ──HTTP──> mcp_brand_style, mcp_vision_ui
            ──A2A──> ip_counsel  ──HTTP──> mcp_legal, mcp_market
            ──A2A──> storyline   (local FunctionTool, no MCP)
```

## Environment contract

**app** (orchestrator / A2A client **+ in-process UI-Render agent**)
- `BRAND_STYLE_A2A_URL`, `IP_COUNSEL_A2A_URL`, `STORYLINE_A2A_URL` — base URLs of the agent services.
- `PORT` — serves UI + `/api/*`.
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI=true` — **the app now calls Gemini itself** for the in-process A2UI presenter (`agents/ui_renderer`), so it needs Vertex access. In compose these come from the `x-vertex-env` anchor + the ADC mount; **on Cloud Run the app's runtime service account needs `roles/aiplatform.user`** (it didn't before — the orchestrator alone made no model calls). Optional `PRESENTER_MODEL` (default `gemini-flash-latest`). If Vertex is unreachable, the presenter falls back to a rule-based summary, so the UI still renders.
- `REQUEST_IMAGE_BUCKET` (default `vibeflix-request-image`) — target for `/api/upload`; SA needs write.
- The UI-Render agent runs **in-process** (no service/port of its own) — its code + skill ship inside the app image (`COPY agents/`).

**agents** (`brand_style` / `ip_counsel` / `storyline`)
- `A2A_AGENT` — which agent this container serves.
- `A2A_HOST`, `A2A_PROTOCOL`, `PORT` — shape the URL published in the agent card (what the orchestrator calls).
- `MCP_BRAND_STYLE_URL` / `MCP_VISION_UI_URL` / `MCP_LEGAL_URL` / `MCP_MARKET_URL` — only the groups the agent uses (brand_style → brand_style + vision_ui; ip_counsel → legal + market).
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI=true` — Vertex AI.

**mcp servers**
- `MCP_TRANSPORT=streamable-http`, `HOST`, `PORT` — serves MCP at `/mcp`.

## Persistence memory (Phase 1)

Durable episodic memory uses **managed Vertex services**: `VertexAiSessionService`
(session event trail) + `VertexAiMemoryBankService` (cross-session recall), backed
by an **Agent Engine** instance, plus `GcsArtifactService` (images/reports).

> The Agent Engine instance is **not** where your agents run — they stay in the
> A2A mesh. It's only the managed backend the two services talk to, scoped by an
> `agent_engine_id`. The instance is empty (no deployed agent code).

Provision it (bucket + Agent Engine) with:

```bash
PROJECT=pokedemo-test REGION=us-central1 BUCKET=vibeflix-artifacts \
  ./deploy/setup_memory.sh
```

It enables the APIs, creates the private artifacts bucket, and creates the Agent
Engine instance, then prints the env the app reads:

```bash
export AGENT_ENGINE_ID=<numeric id>
export MEMORY_LOCATION=us-central1     # ⚠️ a REGION — Agent Engine can't use "global"
export ARTIFACTS_BUCKET=vibeflix-artifacts
```

**Locally**, put these three in `agents/orchestrator/.env` (gitignored) — `agents/memory.py`
loads it automatically, so no manual `export` is needed. **In containers/Cloud Run**
set them as real env vars. With them set the app uses `VertexAiSessionService` +
`VertexAiMemoryBankService` + `GcsArtifactService`, and after each audit
`agents/app.py::_persist_audit` sends the session to Memory Bank and stores the
report as a GCS artifact. Unset → in-memory (local dev), nothing persists.
`ContextCacheConfig` is on regardless.

**Agent Engine creation is a Vertex SDK call, not `gcloud`.** The script uses
`agent_engines.create()` (`pip install "google-cloud-aiplatform[agent_engines]"`).
If your SDK version differs, create it via REST instead:

```bash
curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/pokedemo-test/locations/us-central1/reasoningEngines" \
  -d '{"displayName":"vibeflix-memory"}'
# returns a long-running operation → poll it → the reasoningEngines/<NNN> id is AGENT_ENGINE_ID
```

Without these env vars the app falls back to in-memory services (local dev / adk
web keep working, nothing persists). No Agent Engine needed for sessions-only if
you prefer `DatabaseSessionService` (self-managed Postgres) — Memory Bank's
auto-generation is the part that requires Agent Engine.

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
  history; the 3 registry servers (`mcp_legal`, `mcp_market`, `mcp_brand_style`) opt in
  via `FIRESTORE_DATABASE=vibeflix-registry docker compose up` (var + ADC mount);
  `mcp_vision_ui` has no registries.
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
# ...repeat for mcp_vision_ui, mcp_market (Dockerfile.mcp, different GROUP),
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
MCP_VISION_UI_URL=$MCP_VISION_UI_URL,MCP_LEGAL_URL=$MCP_LEGAL_URL \
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

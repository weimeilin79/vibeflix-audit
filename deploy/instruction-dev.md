# Vibeflix cloud deployment — developer walkthrough (step-by-step gcloud)

The manual route: every resource created by hand so you can see exactly what
exists and why. Same 5 steps and same end state as
[`instruction-sre.md`](instruction-sre.md) (the Terraform/scripts route) — pick
one route per environment, don't mix (Terraform won't know about hand-made
resources).

Set your target once; every command below uses these:

```bash
export PROJECT=pokedemo-test
export REGION=us-central1
gcloud config set project $PROJECT
gcloud auth login && gcloud auth application-default login
```

---

## Step 1 — Foundations: Pub/Sub, database, seed

```bash
# APIs
gcloud services enable firestore.googleapis.com pubsub.googleapis.com \
  run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com

# 1a. Firestore — a DEDICATED named db (not "(default)")
gcloud firestore databases create --database=vibeflix-registry \
  --location=$REGION --type=firestore-native

# 1b. Seed it: semantic registries (brand/legal/market policy), the vendors
#     CRUD store, and rate-card-adjacent data. The seeder is idempotent.
GOOGLE_CLOUD_PROJECT=$PROJECT FIRESTORE_DATABASE=vibeflix-registry \
  python deploy/seed_firestore.py

# 1c. Pub/Sub — the live-telemetry backbone (every agent node + MCP tool emits here)
gcloud pubsub topics create vibeflix-mesh-events
gcloud pubsub subscriptions create vibeflix-mesh-events-app-cloud \
  --topic vibeflix-mesh-events --ack-deadline 10 \
  --message-retention-duration 10m --expiration-period never
# (local dev uses its own subscription, vibeflix-mesh-events-app — see setup_pubsub.sh)

# 1d. Legal RAG corpus (the legal agent has no doc volume in the cloud)
./deploy/setup_legal_rag.sh          # note the printed RAG_CORPUS resource name
```

---

## Step 2 — MCP servers → Cloud Run (with credentials)

**2a. Image registry + builds** (Cloud Build → Artifact Registry):

```bash
gcloud artifacts repositories create vibeflix --location=$REGION --repository-format=docker
export AR=$REGION-docker.pkg.dev/$PROJECT/vibeflix

for G in mcp_licensing mcp_market mcp_brand_style; do
  gcloud builds submit . --config deploy/cloudbuild-mcp.yaml \
    --substitutions "_GROUP=$G,_IMAGE=$AR/${G//_/-}"
done
```

**2b. Runtime credentials — two least-privilege service accounts.** Licensing
WRITES Firestore (vendor onboarding); market/brand_style only READ registries.
Neither touches GCS or Vertex, so they get neither:

```bash
gcloud iam service-accounts create vibeflix-mcp-licensing --display-name "Vibeflix MCP licensing (Firestore RW)"
gcloud iam service-accounts create vibeflix-mcp-readonly  --display-name "Vibeflix MCP market/brand (Firestore RO)"
sleep 30   # SA creation is eventually consistent — bind too fast and it 404s

gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:vibeflix-mcp-licensing@$PROJECT.iam.gserviceaccount.com --role roles/datastore.user
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:vibeflix-mcp-readonly@$PROJECT.iam.gserviceaccount.com --role roles/datastore.viewer

# telemetry publish — scoped to THE TOPIC, not the project:
for SA in vibeflix-mcp-licensing vibeflix-mcp-readonly; do
  gcloud pubsub topics add-iam-policy-binding vibeflix-mesh-events \
    --member serviceAccount:$SA@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.publisher
done
```

**2c. Deploy the three services — IAM-gated (no public access):**

```bash
common="MCP_TRANSPORT=streamable-http,HOST=0.0.0.0,GOOGLE_CLOUD_PROJECT=$PROJECT,FIRESTORE_DATABASE=vibeflix-registry,PUBSUB_TOPIC=vibeflix-mesh-events"

gcloud run deploy vibeflix-mcp-licensing --image $AR/mcp-licensing --region $REGION \
  --service-account vibeflix-mcp-licensing@$PROJECT.iam.gserviceaccount.com \
  --no-allow-unauthenticated --memory 512Mi --max-instances 1 --set-env-vars "$common"
  # max 1: contracts/trademarks/exclusivity are in-memory → single writer

gcloud run deploy vibeflix-mcp-market --image $AR/mcp-market --region $REGION \
  --service-account vibeflix-mcp-readonly@$PROJECT.iam.gserviceaccount.com \
  --no-allow-unauthenticated --memory 512Mi --max-instances 2 --set-env-vars "$common"

gcloud run deploy vibeflix-mcp-brand-style --image $AR/mcp-brand-style --region $REGION \
  --service-account vibeflix-mcp-readonly@$PROJECT.iam.gserviceaccount.com \
  --no-allow-unauthenticated --memory 512Mi --max-instances 2 --set-env-vars "$common"
```

**2d. Who may call them?** For now just you (verification). In step 4 the Agent
Gateway's SA replaces every direct grant and becomes the single point of access
control:

```bash
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  gcloud run services add-iam-policy-binding $S --region $REGION \
    --member user:$(gcloud config get-value account) --role roles/run.invoker
done
```

**2e. Verify:**

```bash
URL=$(gcloud run services describe vibeflix-mcp-licensing --region $REGION --format 'value(status.url)')
curl -s -o /dev/null -w '%{http_code}\n' -X POST $URL/mcp                       # 403 — IAM gate works
curl -s -o /dev/null -w '%{http_code}\n' -X POST $URL/mcp \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"                # non-403 — you're in
```

---

## Step 3 — Agents → Agent Runtime + agent identity

> Code prerequisite: the repo's cloud-auth changes (identity-token headers on
> `mcp_clients` + A2A calls; `_CONTRACTS` in Firestore) must be merged first.

**3a. Runtime identity + grants** (agents call Gemini + RAG on Vertex, publish
telemetry, and read the licensed-asset buckets by gs:// reference):

```bash
gcloud iam service-accounts create vibeflix-agents --display-name "Vibeflix agents runtime"
sleep 30
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:vibeflix-agents@$PROJECT.iam.gserviceaccount.com --role roles/aiplatform.user
gcloud pubsub topics add-iam-policy-binding vibeflix-mesh-events \
  --member serviceAccount:vibeflix-agents@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.publisher
for B in vibeflix-request-image vibeflix-approved-assets; do
  gcloud storage buckets add-iam-policy-binding gs://$B \
    --member serviceAccount:vibeflix-agents@$PROJECT.iam.gserviceaccount.com --role roles/storage.objectViewer
done
# temporary direct MCP access until the gateway exists (step 4 revokes this):
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  gcloud run services add-iam-policy-binding $S --region $REGION \
    --member serviceAccount:vibeflix-agents@$PROJECT.iam.gserviceaccount.com --role roles/run.invoker
done
```

**3b. Deploy each agent as its own reasoning engine** (source-based, A2A mode;
Agent Runtime is REGIONAL — Gemini inside the agents stays `global`):

```bash
gsutil mb -p $PROJECT -l $REGION gs://$PROJECT-vibeflix-agent-staging

export MCP_LICENSING_URL=$(gcloud run services describe vibeflix-mcp-licensing --region $REGION --format 'value(status.url)')/mcp
export MCP_MARKET_URL=$(gcloud run services describe vibeflix-mcp-market --region $REGION --format 'value(status.url)')/mcp
export MCP_BRAND_STYLE_URL=$(gcloud run services describe vibeflix-mcp-brand-style --region $REGION --format 'value(status.url)')/mcp

COMMON="RUN_LOCAL=false,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,PUBSUB_TOPIC=vibeflix-mesh-events"

.venv/bin/adk deploy agent_engine agents/brand_style  --project $PROJECT --region $REGION \
  --staging_bucket gs://$PROJECT-vibeflix-agent-staging \
  --service_account vibeflix-agents@$PROJECT.iam.gserviceaccount.com \
  --display_name vibeflix-brand-style --a2a \
  --env_vars "$COMMON,MCP_BRAND_STYLE_URL=$MCP_BRAND_STYLE_URL"

# repeat for: deal_pricing (MCP_LICENSING_URL), ui_renderer (no MCP),
# legal (MCP_LICENSING_URL + RAG_CORPUS=<step 1d> + RAG_LOCATION=$REGION),
# then vendor_clearance LAST with MCP_LICENSING_URL + MCP_MARKET_URL +
# LEGAL_A2A_URL=<legal engine's A2A card URL from the deploy output>.
```

Each deploy takes 5–10 min (continues server-side if the CLI times out). Note
every engine's resource name + A2A card URL (`…/.well-known/agent-card.json`).

**3c. Agent identity (preview).** Give each engine its own principal — this is
what step 4's per-agent policies bind to:

```bash
agents-cli deploy --agent-identity …    # per engine, or the Agent Platform console
```

Fallback if the preview misbehaves: keep the shared `vibeflix-agents` SA and
bind policies per registered-agent entry (coarser but works today).

**3d. Verify:** `agents-cli run --url <engine url> --mode a2a "ping"`.

---

## Step 4 — Agent Gateway + policies

⚠️ **Preview surfaces** — verify exact command spellings against
`gcloud alpha gemini-enterprise --help` / the Agent Platform console.

```bash
# 4a. Register the assets in the Agent Registry:
#     - 3 MCP servers (their run.app /mcp URLs from step 2)
#     - 5 agents (their A2A card URLs from step 3)
# 4b. Create the gateway attached to the 3 MCP entries:
#     gcloud alpha gemini-enterprise gateways create vibeflix-gateway \
#       --location $REGION --mcp-servers vibeflix-mcp-licensing,vibeflix-mcp-market,vibeflix-mcp-brand-style
#     → note the GATEWAY ENDPOINT and its service agent SA.
# 4c. Apply deploy/policies.yaml — deny-by-default, per-agent tool allowlists
#     (brand_style → run_brand_audit only; legal = sole upsert_contract writer;
#      the app → read-only set + demo reset).
```

**4d. Flip MCP access control to the gateway** — remove every direct invoker and
grant ONLY the gateway SA, so all MCP traffic must pass the policy check:

```bash
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  gcloud run services remove-iam-policy-binding $S --region $REGION \
    --member serviceAccount:vibeflix-agents@$PROJECT.iam.gserviceaccount.com --role roles/run.invoker
  gcloud run services add-iam-policy-binding $S --region $REGION \
    --member serviceAccount:<GATEWAY_SA> --role roles/run.invoker
done
```

**4e. Re-point the agents at the gateway** — redeploy each engine (step 3b) with
`MCP_*_URL` set to the gateway endpoint. Auth flow from here:
*agent (own identity token) → gateway (policy check) → gateway OIDC → Cloud Run MCP.*
Agents hold no per-MCP credentials.

Optional: publish each agent to Gemini Enterprise:

```bash
agents-cli publish gemini-enterprise --registration-type a2a \
  --agent-card-url <card url> --gemini-enterprise-app-id <GE app> --display-name "Vibeflix <agent>"
```

---

## Step 5 — Frontend (console app) → Cloud Run

```bash
# 5a. app runtime SA — Vertex (engine A2A calls), Firestore (audit history),
#     upload bucket admin (upload + reset-clean), its own telemetry subscription:
gcloud iam service-accounts create vibeflix-app --display-name "Vibeflix console app"
sleep 30
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/aiplatform.user
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/datastore.user
gcloud storage buckets add-iam-policy-binding gs://vibeflix-request-image \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/storage.objectAdmin
gcloud pubsub topics add-iam-policy-binding vibeflix-mesh-events \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.publisher
gcloud pubsub subscriptions add-iam-policy-binding vibeflix-mesh-events-app-cloud \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.subscriber

# 5b. build + deploy
gcloud builds submit . --config deploy/cloudbuild-app.yaml --substitutions "_IMAGE=$AR/app"
gcloud run deploy vibeflix-app --image $AR/app --region $REGION \
  --service-account vibeflix-app@$PROJECT.iam.gserviceaccount.com \
  --memory 1Gi --max-instances 2 --allow-unauthenticated \
  --set-env-vars "RUN_LOCAL=false,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=global,\
FIRESTORE_DATABASE=vibeflix-registry,PUBSUB_TOPIC=vibeflix-mesh-events,PUBSUB_SUBSCRIPTION=vibeflix-mesh-events-app-cloud,\
REQUEST_IMAGE_BUCKET=vibeflix-request-image,\
BRAND_STYLE_A2A_URL=<engine url>,VENDOR_CLEARANCE_A2A_URL=<engine url>,DEAL_PRICING_A2A_URL=<engine url>,UI_RENDERER_A2A_URL=<engine url>,\
MCP_LICENSING_URL=<gateway url>,MCP_MARKET_URL=<gateway url>,MCP_BRAND_STYLE_URL=<gateway url>"
```

(`--allow-unauthenticated` = demo console; front with IAP for real use.)

**End-to-end verify:** open the app URL → run a standard audit → three reports
render, graph LEDs light (events via `-app-cloud` subscription), contract in
Audit History, Database tab dumps the cloud Firestore.

---

## Teardown (reverse order)

```bash
gcloud run services delete vibeflix-app --region $REGION
# delete the 5 reasoning engines (console / vertexai SDK) + gateway/registry entries
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  gcloud run services delete $S --region $REGION; done
for SA in vibeflix-mcp-licensing vibeflix-mcp-readonly vibeflix-agents vibeflix-app; do
  gcloud iam service-accounts delete $SA@$PROJECT.iam.gserviceaccount.com --quiet; done
gcloud artifacts repositories delete vibeflix --location $REGION --quiet
gcloud pubsub subscriptions delete vibeflix-mesh-events-app-cloud
```

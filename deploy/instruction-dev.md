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

gcloud projects add-iam-policy-binding $PROJECT --condition=None \
  --member serviceAccount:vibeflix-mcp-licensing@$PROJECT.iam.gserviceaccount.com --role roles/datastore.user
gcloud projects add-iam-policy-binding $PROJECT --condition=None \
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
gcloud projects add-iam-policy-binding $PROJECT --condition=None \
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

**3b. Deploy each agent as its own reasoning engine.** The ADK 2.3 CLI packages
the agent FOLDER + a generated Dockerfile; the engine serves **A2A automatically**
(no flag). Three things to know about this CLI:

- it installs `agents/<name>/requirements.txt` from INSIDE the folder — each
  agent has one (it pins `google-adk[a2a]==2.3.0` and pulls `vibeflix-common`
  from the repo's git URL; private repo → publish the package to an Artifact
  Registry python repo and swap that line);
- env vars go in a file passed via `--env_file`; the runtime `service_account`
  goes in a JSON passed via `--agent_engine_config_file`;
- **without `--agent_engine_id` every run CREATES a new engine** — pass the
  existing ID (from the list command below) to update instead.

```bash
export MCP_LICENSING_URL=$(gcloud run services describe vibeflix-mcp-licensing --region $REGION --format 'value(status.url)')/mcp
export MCP_MARKET_URL=$(gcloud run services describe vibeflix-mcp-market --region $REGION --format 'value(status.url)')/mcp
export MCP_BRAND_STYLE_URL=$(gcloud run services describe vibeflix-mcp-brand-style --region $REGION --format 'value(status.url)')/mcp
export RAG_CORPUS=<from step 1d>

# engine config: the runtime SA (identity comes in 3c)
cat > /tmp/engine_config.json <<EOF
{"service_account": "vibeflix-agents@$PROJECT.iam.gserviceaccount.com"}
EOF

# 1/5 — brand_style (vision + deterministic brand checks)
printf 'RUN_LOCAL=false\nGOOGLE_GENAI_USE_VERTEXAI=true\nPUBSUB_TOPIC=vibeflix-mesh-events\nMCP_BRAND_STYLE_URL=%s\n' "$MCP_BRAND_STYLE_URL" > /tmp/env_brand_style
.venv/bin/adk deploy agent_engine agents/brand_style --project $PROJECT --region $REGION \
  --display_name vibeflix-brand-style \
  --env_file /tmp/env_brand_style --agent_engine_config_file /tmp/engine_config.json

# 2/5 — deal_pricing (rate-card reconciliation)
printf 'RUN_LOCAL=false\nGOOGLE_GENAI_USE_VERTEXAI=true\nPUBSUB_TOPIC=vibeflix-mesh-events\nMCP_LICENSING_URL=%s\n' "$MCP_LICENSING_URL" > /tmp/env_deal_pricing
.venv/bin/adk deploy agent_engine agents/deal_pricing --project $PROJECT --region $REGION \
  --display_name vibeflix-deal-pricing \
  --env_file /tmp/env_deal_pricing --agent_engine_config_file /tmp/engine_config.json

# 3/5 — ui_renderer (A2UI presenter + form designer; no MCP)
printf 'RUN_LOCAL=false\nGOOGLE_GENAI_USE_VERTEXAI=true\nPUBSUB_TOPIC=vibeflix-mesh-events\n' > /tmp/env_ui_renderer
.venv/bin/adk deploy agent_engine agents/ui_renderer --project $PROJECT --region $REGION \
  --display_name vibeflix-ui-renderer \
  --env_file /tmp/env_ui_renderer --agent_engine_config_file /tmp/engine_config.json

# 4/5 — legal (RAG-discovered process; NO doc volume in the cloud → RAG_CORPUS)
printf 'RUN_LOCAL=false\nGOOGLE_GENAI_USE_VERTEXAI=true\nPUBSUB_TOPIC=vibeflix-mesh-events\nMCP_LICENSING_URL=%s\nRAG_CORPUS=%s\nRAG_LOCATION=%s\n' \
  "$MCP_LICENSING_URL" "$RAG_CORPUS" "$REGION" > /tmp/env_legal
.venv/bin/adk deploy agent_engine agents/legal --project $PROJECT --region $REGION \
  --display_name vibeflix-legal \
  --env_file /tmp/env_legal --agent_engine_config_file /tmp/engine_config.json
```

(`GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` are deliberately absent from the
env files — the CLI intercepts them; Gemini's `global` location ships in each
agent folder's own `.env`.)

Each deploy takes 5–10 min (continues server-side if the CLI times out). List
the engines and capture their ids:

```bash
.venv/bin/python - <<'PY'
import os, vertexai
client = vertexai.Client(project=os.environ["PROJECT"], location=os.environ["REGION"])
for e in client.agent_engines.list():
    r = e.api_resource
    print(f"{r.display_name:28s} {r.name}")
PY
```

An engine's A2A base is
`https://$REGION-aiplatform.googleapis.com/v1/<engine resource name>` and its
agent card hangs off that base (`…/a2a/…/.well-known/agent-card.json` — the deploy
output prints the exact card URL; `agents-cli run --url <resource name> --mode a2a`
resolves it for you if in doubt).

```bash
# 5/5 — vendor_clearance LAST: it needs legal's A2A card URL for the hand-off
export LEGAL_A2A_URL=<legal's A2A base from the list above>

printf 'RUN_LOCAL=false\nGOOGLE_GENAI_USE_VERTEXAI=true\nPUBSUB_TOPIC=vibeflix-mesh-events\nMCP_LICENSING_URL=%s\nMCP_MARKET_URL=%s\nLEGAL_A2A_URL=%s\n' \
  "$MCP_LICENSING_URL" "$MCP_MARKET_URL" "$LEGAL_A2A_URL" > /tmp/env_vendor_clearance
.venv/bin/adk deploy agent_engine agents/vendor_clearance --project $PROJECT --region $REGION \
  --display_name vibeflix-vendor-clearance \
  --env_file /tmp/env_vendor_clearance --agent_engine_config_file /tmp/engine_config.json
```

**3c. Agent identity (preview).** Give each engine its own principal — this is
what step 4's per-agent policies bind to. Identity is an **engine config field**
(`identity_type: types.IdentityType.AGENT_IDENTITY`, v1beta1 API); since `adk
deploy agent_engine` doesn't expose it, flip it on with an UPDATE after deploy:

```bash
PROJECT=$PROJECT REGION=$REGION python deploy/enable_agent_identity.py
```

…which runs, per vibeflix engine (equivalent SDK call, per the
[agent-identity docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity)):

```python
import vertexai
from vertexai import types

client = vertexai.Client(project=PROJECT, location=REGION,
                         http_options=dict(api_version="v1beta1"))
client.agent_engines.update(
    name="projects/…/locations/…/reasoningEngines/<ID>",
    config={"identity_type": types.IdentityType.AGENT_IDENTITY},
)
# principal = engine.api_resource.spec.effective_identity
```

Each agent's principal looks like
`principal://agents.global.org-<ORG_ID>.system.id.goog/resources/aiplatform/projects/<PN>/locations/<REGION>/reasoningEngines/<ID>`
(the script writes them all to `deploy/agent_identities.json`). Grant the
recommended baseline to ALL agents in the project in one go, then per-agent
grants where needed:

```bash
ORG=$(gcloud organizations list --format 'value(ID)' | head -1)
AGENTS_SET="principalSet://agents.global.org-$ORG.system.id.goog/attribute.platformContainer/aiplatform/projects/$PN"
for ROLE in roles/aiplatform.expressUser roles/serviceusage.serviceUsageConsumer roles/browser; do
  gcloud projects add-iam-policy-binding $PROJECT --condition=None \
    --member "$AGENTS_SET" --role $ROLE
done
# telemetry publish for all agents:
gcloud pubsub topics add-iam-policy-binding vibeflix-mesh-events \
  --member "$AGENTS_SET" --role roles/pubsub.publisher
```

Fallback if the preview misbehaves: keep the shared `vibeflix-agents` SA from 3a
and bind step-4 policies per registered-agent entry (coarser but works today).

**3d. Verify each engine** answers over A2A:

```bash
for E in $(.venv/bin/python -c "
import os, vertexai
c = vertexai.Client(project=os.environ['PROJECT'], location=os.environ['REGION'])
print(' '.join(e.api_resource.name for e in c.agent_engines.list()))"); do
  echo "── $E"
  agents-cli run --url "$E" --mode a2a "ping — reply with your agent name"
done
```

---

## Step 4 — Agent Gateway + policies

⚠️ **Preview surfaces.** Agent Registry / Agent Gateway are Gemini Enterprise
Agent Platform preview features; the exact CLI spelling depends on your gcloud
release. Each sub-step below gives the gcloud form AND the REST form — if the
gcloud surface differs (`gcloud alpha gemini-enterprise --help` is the source of
truth), the REST call is the stable fallback. `$TOKEN` below is
`$(gcloud auth print-access-token)`; the API host is the Agent Platform endpoint
shown in your console (`geminienterprise.googleapis.com` unless your onboarding
says otherwise); `$PN` is the project number
(`gcloud projects describe $PROJECT --format 'value(projectNumber)'`).

**4a. Register the 3 MCP servers in the Agent Registry:**

```bash
for S in licensing market brand-style; do
  URL=$(gcloud run services describe vibeflix-mcp-$S --region $REGION --format 'value(status.url)')/mcp
  # gcloud form:
  gcloud alpha gemini-enterprise agent-registry mcp-servers register vibeflix-mcp-$S \
    --project $PROJECT --location $REGION --uri "$URL" \
    --description "Vibeflix $S MCP server (Cloud Run, IAM-gated)" \
  || # REST fallback:
  curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "https://geminienterprise.googleapis.com/v1alpha/projects/$PN/locations/$REGION/mcpServers?mcpServerId=vibeflix-mcp-$S" \
    -d "{\"displayName\":\"vibeflix-mcp-$S\",\"uri\":\"$URL\"}"
done
```

**4b. Register the 5 agents (A2A cards from step 3):**

```bash
for A in brand-style vendor-clearance deal-pricing legal ui-renderer; do
  CARD=<vibeflix-$A engine's agent-card URL>
  gcloud alpha gemini-enterprise agent-registry agents register vibeflix-$A \
    --project $PROJECT --location $REGION --agent-card-url "$CARD" \
  || curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "https://geminienterprise.googleapis.com/v1alpha/projects/$PN/locations/$REGION/agents?agentId=vibeflix-$A" \
    -d "{\"displayName\":\"vibeflix-$A\",\"a2aAgentCard\":{\"uri\":\"$CARD\"}}"
done
```

**4c. Create the gateway over the 3 MCP entries, then apply the policies:**

```bash
gcloud alpha gemini-enterprise gateways create vibeflix-gateway \
  --project $PROJECT --location $REGION \
  --mcp-servers vibeflix-mcp-licensing,vibeflix-mcp-market,vibeflix-mcp-brand-style
# → note two things from the output / console:
#    GATEWAY_URL (the governed MCP endpoint the agents will use)
#    GATEWAY_SA  (its service agent, e.g. service-$PN@gcp-sa-<gateway>.iam.gserviceaccount.com)

# Policies — one binding per row of deploy/policies.yaml (deny-by-default:
# an agent with no binding for a tool gets REJECTED at the gateway). Example,
# brand_style may call run_brand_audit and nothing else:
gcloud alpha gemini-enterprise gateways policies create allow-brand-style \
  --project $PROJECT --location $REGION --gateway vibeflix-gateway \
  --caller "principal://…/agents/vibeflix-brand-style" \
  --mcp-server vibeflix-mcp-brand-style --allow-tools run_brand_audit
# Repeat for every entry in deploy/policies.yaml:
#   vibeflix-deal-pricing     → mcp-licensing: get_license_pricing
#   vibeflix-vendor-clearance → mcp-licensing: get_vendor,find_vendors,create_vendor,
#                               update_vendor,list_trademarks,verify_trademark_record,
#                               scan_global_exclusivity_clauses,check_vendor_eligibility
#   vibeflix-vendor-clearance → mcp-market: scan_ecom_marketplaces,check_sku_volume_caps,capture_audit_map
#   vibeflix-legal            → mcp-licensing: get_vendor,verify_trademark_record,
#                               scan_global_exclusivity_clauses,upsert_contract,get_contract
#   vibeflix-app              → mcp-licensing: list_trademarks,get_vendor,find_vendors,
#                               verify_trademark_record,scan_global_exclusivity_clauses,
#                               get_contract,upsert_contract,dump_stores,reset_vendors
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

**4e. Re-point the agents at the gateway** — re-run the step-3b deploy commands
with the MCP env vars swapped to the gateway endpoint (updating an existing
display-name redeploys the same engine):

```bash
export MCP_LICENSING_URL=$GATEWAY_URL/mcp-servers/vibeflix-mcp-licensing/mcp
export MCP_MARKET_URL=$GATEWAY_URL/mcp-servers/vibeflix-mcp-market/mcp
export MCP_BRAND_STYLE_URL=$GATEWAY_URL/mcp-servers/vibeflix-mcp-brand-style/mcp
# (exact per-server path per the gateway's console page)
# then re-run each `adk deploy agent_engine …` command from 3b unchanged.
```

Auth flow from here:
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
gcloud projects add-iam-policy-binding $PROJECT --condition=None \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/aiplatform.user
gcloud projects add-iam-policy-binding $PROJECT --condition=None \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/datastore.user
gcloud storage buckets add-iam-policy-binding gs://vibeflix-request-image \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/storage.objectAdmin
gcloud pubsub topics add-iam-policy-binding vibeflix-mesh-events \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.publisher
gcloud pubsub subscriptions add-iam-policy-binding vibeflix-mesh-events-app-cloud \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.subscriber

# 5b. collect the wiring: each agent's A2A base URL from its engine resource name
declare -A ENGINE
while read -r NAME RES; do ENGINE[$NAME]=$RES; done < <(.venv/bin/python - <<'PY'
import os, vertexai
c = vertexai.Client(project=os.environ["PROJECT"], location=os.environ["REGION"])
for e in c.agent_engines.list():
    r = e.api_resource
    print(r.display_name, r.name)
PY
)
A2A_BASE="https://$REGION-aiplatform.googleapis.com/v1"
BRAND_URL=$A2A_BASE/${ENGINE[vibeflix-brand-style]}
VENDOR_URL=$A2A_BASE/${ENGINE[vibeflix-vendor-clearance]}
PRICING_URL=$A2A_BASE/${ENGINE[vibeflix-deal-pricing]}
UI_URL=$A2A_BASE/${ENGINE[vibeflix-ui-renderer]}
# MCP_*_URL: the gateway per-server endpoints from step 4e (still exported).

# 5c. build + deploy
gcloud builds submit . --config deploy/cloudbuild-app.yaml --substitutions "_IMAGE=$AR/app"
gcloud run deploy vibeflix-app --image $AR/app --region $REGION \
  --service-account vibeflix-app@$PROJECT.iam.gserviceaccount.com \
  --memory 1Gi --max-instances 2 --allow-unauthenticated \
  --set-env-vars "RUN_LOCAL=false,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=global,\
FIRESTORE_DATABASE=vibeflix-registry,PUBSUB_TOPIC=vibeflix-mesh-events,PUBSUB_SUBSCRIPTION=vibeflix-mesh-events-app-cloud,\
REQUEST_IMAGE_BUCKET=vibeflix-request-image,AUDIT_HISTORY_DIR=/tmp,\
BRAND_STYLE_A2A_URL=$BRAND_URL,VENDOR_CLEARANCE_A2A_URL=$VENDOR_URL,DEAL_PRICING_A2A_URL=$PRICING_URL,UI_RENDERER_A2A_URL=$UI_URL,\
MCP_LICENSING_URL=$MCP_LICENSING_URL,MCP_MARKET_URL=$MCP_MARKET_URL,MCP_BRAND_STYLE_URL=$MCP_BRAND_STYLE_URL"

echo "console: $(gcloud run services describe vibeflix-app --region $REGION --format 'value(status.url)')"
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

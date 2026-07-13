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

## ⚠️ Five rules that will break a fresh build if you ignore them

Verified end-to-end (all 4 layers) on 2026-07-13. Each of these cost us hours:

1. **⛔ NEVER DELETE AN ENGINE.** The engine id is baked into its `principal://…/reasoningEngines/<ID>`.
   Redeploying the same display name *updates in place* and keeps the id (Agent Runtime makes
   a new immutable **revision**, not a new engine). Delete + recreate ⇒ NEW id ⇒ NEW principal
   ⇒ every IAM grant and registry endpoint silently points at a dead principal, while the
   console still looks correct.
2. **Deploy the engines SERIALLY** (step 3). One process is safe; several in parallel race on
   the vendored `vibeflix_common/` dir and a deploy fails **silently**, leaving that engine on
   its OLD code.
3. **⏱️ Wait 2–5 minutes after any registry/IAM change before you judge it.** Propagation is
   not instant. We discarded a *correct* fix twice by testing ~40s in, seeing a 403, and
   concluding it hadn't worked.
4. **Verify from the BACKEND's log, never the agent's reply.** An agent whose toolset failed
   to load still emits a confident, clean verdict — brand_style reported `status:"success"`,
   `findings:[]` and a plausible `checks_run` while the MCP server had logged **zero**
   `CallToolRequest` (the model was inventing the check names). See `tests/a2a/README.md`.
5. **Step 4's grants are not optional and must come AFTER the engines exist** (they key off
   `agent_identities.json`). The mesh fails in confusing, unrelated-looking ways without them.

---

## Step 1 — Foundations: Pub/Sub, database, seed

```bash
# 1-0. Enable EVERY API the walkthrough touches (one shot, idempotent):
gcloud services enable --project=$PROJECT \
  firestore.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  agentregistry.googleapis.com networkservices.googleapis.com \
  networksecurity.googleapis.com iap.googleapis.com \
  observability.googleapis.com apphub.googleapis.com \
  cloudtrace.googleapis.com telemetry.googleapis.com

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

# OTel traces (Cloud Trace exporter in the servers):
for SA in vibeflix-mcp-licensing vibeflix-mcp-readonly; do
  gcloud projects add-iam-policy-binding $PROJECT --condition=None \
    --member serviceAccount:$SA@$PROJECT.iam.gserviceaccount.com --role roles/cloudtrace.agent
done
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

✅ **Verify all 3 services exist before continuing** (a lost paste of one
deploy command is easy to miss — the IAM step below fails on a missing service):

```bash
gcloud run services list --project=$PROJECT --region=$REGION \
  --filter="metadata.name:vibeflix-mcp" --format="table(metadata.name,status.url)"
# expect EXACTLY these three, each with a URL:
#   vibeflix-mcp-licensing · vibeflix-mcp-market · vibeflix-mcp-brand-style
# missing one? its image is likely already built (gcloud builds list) —
# just re-run that service's `gcloud run deploy …` command from 2c.
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

> ### ⛔ NEVER DELETE THE ENGINES
> An `AGENT_IDENTITY` engine runs as
> `principal://…/reasoningEngines/<ENGINE_ID>` — **the engine id is baked into the
> principal.** Redeploying the same display name *updates in place* and keeps the
> id (Agent Runtime creates a new immutable *revision*, not a new engine — see
> [manage revisions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/manage-revisions-and-traffic)).
> Delete + recreate mints a NEW id → a NEW principal → **every IAM grant and every
> Agent Registry endpoint silently points at a dead principal.** The mesh then
> fails with 401/403s while the console policies still *look* correct. This cost
> us most of a day. If you ever do delete: re-run `collect_agent_identities.py`,
> then `deploy/grant_agent_iam.sh`, then re-point the registry endpoints.

> ### 🔑 The A2A auth rule (TWO parties authenticate ONE request)
> An engine→engine call passes through the gateway on its way to the callee, and **both**
> need a credential:
>
> | header | who reads it | what it does |
> |---|---|---|
> | `Proxy-Authorization: Bearer <token>` | the **Agent Gateway** | egress authorization (agent identity) |
> | `Authorization: Bearer <token>` | the **target engine's** aiplatform endpoint | identifies the caller |
>
> Same token in both. `a2a_engine.py` used to send only `Proxy-Authorization` inside an
> engine, so the callee received **no credential at all** and answered `401` — which we
> spent a long time misreading as a missing client certificate.
>
> **Read the status code as a distance signal:**
> - **`403 Egress request is not authorized`** → the **gateway** refused you. The request
>   never left; the callee's log is empty. Cause: the destination URL doesn't match a
>   registered Service you hold `iap.egressor` on.
> - **`401 Unauthorized`** → the gateway **let you through** and the **target** refused you.
>   Cause: missing/wrong credential for the callee.
>
> (Same pattern on the MCP hop, with Cloud Run as the target: no token → `403`; an *access*
> token where an *ID* token is required → `401`; correct ID token → `200`.)

> ### 🔑 The MCP auth rule (agent identity ⇒ impersonation)
> Cloud Run only accepts an **audience-bound OIDC ID token** (verified: access
> token → `401 "the access token could not be verified"`, ID token → `200`, no
> token → `403`). An `AGENT_IDENTITY` engine has **no service account behind the
> metadata server**, so `google.oauth2.id_token.fetch_id_token()` *cannot work* —
> and the Agent Gateway does **not** inject a credential for you (there is no
> invoker-SA field on `agentToAnywhereConfig`, on the registry service, or in
> gcloud). The engine must therefore mint its own token by **impersonating an
> invoker SA**, exactly as the Agent Gateway codelab's `--mcp-invoker-sa` does
> (it just sets an env var: `deploy_config["env_vars"]["MCP_INVOKER_SA"] = …`).
> Wired here as `MCP_INVOKER_SA` (deploy_agents_a2a.py) →
> `cloud_auth._id_token_via_impersonation()` → `impersonated_credentials.IDTokenCredentials`.
> Three things must ALL be true (3f + 4c-vi below): env var set, agent principal
> holds `roles/iam.serviceAccountTokenCreator` on the SA, and the principal holds
> `roles/iap.egressor` on the `gcp-iamcredentials*` endpoints (the gateway is
> default-deny, so even the token-minting call needs an allowlist entry).

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

**3b. Deploy each agent via the A2A TEMPLATE — one at a time, in dependency
order.** `deploy/deploy_agents_a2a.py` wraps each `root_agent` in the SDK's
`A2aAgent` template, so the engine's container genuinely serves platform A2A
(`/a2a/v1/card`, `message/send`) — the `adk deploy agent_engine` CLI cannot
(its container only implements the streamQuery contract; see the README
comparison). Identity + service account + OTel are set AT CREATE — no
post-deploy configure pass needed. Re-running a name UPDATES the same engine.

```bash
# everything explicit — no personal env files (deploy/.env is gitignored and
# machine-specific; a fresh clone must work from these lines alone):
export PROJECT=${PROJECT:-pokedemo-test}
export REGION=${REGION:-us-central1}
export RAG_LOCATION=$REGION
# legal's RAG corpus (step 1d) — resolved live:
export RAG_CORPUS=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/$REGION/ragCorpora" \
  | jq -r '[.ragCorpora[] | select(.displayName=="vibeflix-legal-kb")][0].name')
echo "RAG_CORPUS=$RAG_CORPUS"   # must print projects/…, not null

# staging bucket for the SDK's source tarballs (create once; harmless if it exists):
gsutil mb -p $PROJECT -l $REGION gs://$PROJECT-vibeflix-agent-staging 2>/dev/null || true

export MCP_LICENSING_URL=$(gcloud run services describe vibeflix-mcp-licensing --region $REGION --format 'value(status.url)')/mcp
export MCP_MARKET_URL=$(gcloud run services describe vibeflix-mcp-market --region $REGION --format 'value(status.url)')/mcp
export MCP_BRAND_STYLE_URL=$(gcloud run services describe vibeflix-mcp-brand-style --region $REGION --format 'value(status.url)')/mcp

# 1/6 — brand_style
.venv/bin/python deploy/deploy_agents_a2a.py brand_style
# 2/6 — deal_pricing
.venv/bin/python deploy/deploy_agents_a2a.py deal_pricing
# 3/6 — ui_renderer
.venv/bin/python deploy/deploy_agents_a2a.py ui_renderer
# 4/6 — legal
.venv/bin/python deploy/deploy_agents_a2a.py legal
```

✅ **Verify after EACH deploy** — the script prints the engine's card URL; fetch
it (this is the exact surface the old CLI path could never serve — 200 = the
gap is closed for that agent):

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" "<card url printed above>" | jq .name
```

**3c. Deploy vendor_clearance** (needs legal's A2A base):

```bash
BASE=https://$REGION-aiplatform.googleapis.com/v1beta1
A2A_BASE=https://$REGION-aiplatform.mtls.googleapis.com/v1beta1
ENGINES_JSON=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$BASE/projects/$PROJECT/locations/$REGION/reasoningEngines")
eng() { jq -r --arg n "$1" '[.reasoningEngines[] | select(.displayName==$n)][0].name' <<< "$ENGINES_JSON"; }
export LEGAL_A2A_URL=$A2A_BASE/$(eng vibeflix-legal)

.venv/bin/python deploy/deploy_agents_a2a.py vendor_clearance
```

✅ **Verify:** its card fetch returns 200, like 3b.

**3d. Deploy the ORCHESTRATOR — last** (needs the three domain engines):

```bash
ENGINES_JSON=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$BASE/projects/$PROJECT/locations/$REGION/reasoningEngines")
export BRAND_STYLE_A2A_URL=$A2A_BASE/$(eng vibeflix-brand-style)
export VENDOR_CLEARANCE_A2A_URL=$A2A_BASE/$(eng vibeflix-vendor-clearance)
export DEAL_PRICING_A2A_URL=$A2A_BASE/$(eng vibeflix-deal-pricing)
printf '%s\n' "$BRAND_STYLE_A2A_URL" "$VENDOR_CLEARANCE_A2A_URL" "$DEAL_PRICING_A2A_URL"  # no "/null"

.venv/bin/python deploy/deploy_agents_a2a.py orchestrator
```

**3e. Record identities for step 4** (identity was already enabled at create — this only READS principals into `deploy/agent_identities.json` for step 4; do NOT run enable_agent_identity_and_a2a.py on template engines, they already serve A2A):

```bash
PROJECT=$PROJECT REGION=$REGION .venv/bin/python deploy/collect_agent_identities.py
```

**3f. Grant Project-level IAM Roles to Agent Principals:**
Since each reasoning engine is deployed with `identity_type = AGENT_IDENTITY`, they execute as their own unique `principal://...` identity rather than using the shared `vibeflix-agents` service account. Therefore, you must grant the necessary Google Cloud permissions directly to each agent's principal.

```bash
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  P=$(jq -r --arg k "vibeflix-$A" '.[$k].principal' deploy/agent_identities.json)
  for R in roles/aiplatform.user \
           roles/aiplatform.agentDefaultAccess \
           roles/aiplatform.agentContextEditor \
           roles/logging.logWriter \
           roles/monitoring.metricWriter \
           roles/browser \
           roles/agentregistry.viewer; do
    gcloud projects add-iam-policy-binding $PROJECT --member="$P" --role="$R" --condition=None
  done
done
```

✅ **Verify** (each principal must show 7 roles — `0` means the grants missed, e.g. because
the engines were deleted and recreated and these point at dead principals):

```bash
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  P=$(jq -r --arg k "vibeflix-$A" '.[$k].principal' deploy/agent_identities.json)
  N=$(gcloud projects get-iam-policy $PROJECT --flatten="bindings[].members" \
        --filter="bindings.members:$P" --format="value(bindings.role)" | wc -l)
  echo "  $A: $N roles"
done
```

⚠️ Two traps this encodes:
- **`agentContextEditor` is required, not optional.** It's what lets an agent
  read/write *its own* sessions. Without it ADK's `VertexAiSessionService.create_session()`
  fails and the A2A executor dies in `_prepare_session` *before your agent code runs* —
  which surfaces as an opaque `TASK_STATE_FAILED`, not as a permissions error.
- **`principalSet://…` grants DO NOT MATCH agent identities.** They bind without
  error and match nothing. Always grant the **specific** `principal://…/reasoningEngines/<id>`
  from `deploy/agent_identities.json`.

**3g. Impersonation grant for MCP access** (see "The MCP auth rule" above — the
engine mints its own Cloud Run ID token by impersonating this SA):

```bash
gcloud iam service-accounts create vibeflix-mcp-invoker \
  --display-name "Vibeflix MCP invoker (agent-identity ID-token source)" || true
SA=vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com
# the SA must be able to invoke the MCPs …
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  gcloud run services add-iam-policy-binding $S --region $REGION \
    --member="serviceAccount:$SA" --role=roles/run.invoker
done
# … and each agent principal must be able to impersonate it:
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  P=$(jq -r --arg k "vibeflix-$A" '.[$k].principal' deploy/agent_identities.json)
  gcloud iam service-accounts add-iam-policy-binding "$SA" \
    --member="$P" --role=roles/iam.serviceAccountTokenCreator --condition=None
done
```

---

## Step 4 — Agent Gateway + policies

Surfaces per the [Agent Gateway codelab](https://codelabs.developers.google.com/cloudnet-agent-gateway)
(⚠️ preview — verify spellings against your gcloud release).

**4a. Register the 3 MCP servers in the Agent Registry.** Each registration
carries a **tool spec** (generated from the live server so it never drifts)
plus the server's URL as a JSONRPC interface:

```bash
mkdir -p deploy/toolspecs
for S in licensing market brand-style; do
  URL=$(gcloud run services describe vibeflix-mcp-$S --region $REGION --format 'value(status.url)')/mcp
  .venv/bin/python deploy/make_toolspec.py "$URL" > deploy/toolspecs/$S.json
  gcloud alpha agent-registry services create vibeflix-mcp-$S \
    --project=$PROJECT --location=$REGION \
    --display-name="Vibeflix MCP $S" \
    --mcp-server-spec-type=tool-spec \
    --mcp-server-spec-content=deploy/toolspecs/$S.json \
    --interfaces=url=$URL,protocolBinding=JSONRPC
done
gcloud alpha agent-registry services list --project=$PROJECT --location=$REGION \
  --format="value(displayName,name)"
```

**4a-ii. Register the 5 AGENTS in the Agent Registry.** Agents are separate
registry entries (step 4a covered only the MCP servers) — without these the
console's agent list is empty, gateway A2A policies have nothing to bind to,
and attached agents can't be reached (unregistered destinations are blocked).
⚠️ Two rules learned the hard way: (1) this step REQUIRES step 3 completed
first (`deploy/agent_identities.json` supplies each engine path); (2) interface
URLs must be UNIQUE across the registry — each agent's URL is the mTLS
aiplatform host **plus its own engine path**. If an earlier attempt registered
an agent with the bare host URL, delete it first
(`gcloud alpha agent-registry services delete <name> --location=$REGION --quiet`)
or every later registration collides with "Interface URL already in use":

```bash
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' deploy/agent_identities.json)
  gcloud alpha agent-registry services create vibeflix-$A-agent \
    --project=$PROJECT --location=$REGION \
    --display-name="Vibeflix $A agent" \
    --endpoint-spec-type=no-spec \
    --interfaces='[{url="https://'$REGION'-aiplatform.mtls.googleapis.com/v1beta1/'$ENG'",protocolBinding="jsonrpc"}]'
done
gcloud alpha agent-registry services list --project=$PROJECT --location=$REGION
```

✅ **Verify:** the list shows **9 entries** — 3 `vibeflix-mcp-*` + 6 `vibeflix-*-agent`.

**4b. Create the gateway** — a YAML import on the `network-services` surface,
bound to the project's registry (our MCP backends are public run.app URLs, so
the codelab's `networkConfig`/DNS-peering block for private-VPC backends is
omitted):

```bash
cat > deploy/agent-gateway.yaml <<EOF
name: vibeflix-gateway
protocols: [MCP]
googleManaged:
  governedAccessPath: AGENT_TO_ANYWHERE
registries:
  - "//agentregistry.googleapis.com/projects/$PROJECT/locations/$REGION"
EOF
gcloud alpha network-services agent-gateways import vibeflix-gateway \
  --source=deploy/agent-gateway.yaml --location=$REGION --project=$PROJECT
gcloud alpha network-services agent-gateways describe vibeflix-gateway \
  --location=$REGION --project=$PROJECT
# → note the GATEWAY ENDPOINT and its service agent SA from the output
```

**4c. Policies — IAP authz extension + per-agent egress grants.** Access
control is IAP: attach a `REQUEST_AUTHZ` extension to the gateway, then grant
each agent identity `roles/iap.egressor` scoped by CEL conditions —
[`deploy/policies.yaml`](policies.yaml) is the row-by-row mapping, identities
come from `deploy/agent_identities.json`:

```bash
cat > deploy/iap-authz-extension.yaml <<EOF
name: vibeflix-gateway-iap-authz
service: iap.googleapis.com
failOpen: true
timeout: 5s
metadata:
  iapPolicyVersion: "V1"
EOF
gcloud beta service-extensions authz-extensions import vibeflix-gateway-iap-authz \
  --source=deploy/iap-authz-extension.yaml --location=$REGION --project=$PROJECT
```

**4c-ii. Bind the extension to the gateway** — an AuthzPolicy (`REQUEST_AUTHZ`
profile) targeting the gateway, referencing the extension (networksecurity
v1alpha1; no gcloud surface yet):

```bash
curl -fsS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -X POST "https://networksecurity.googleapis.com/v1alpha1/projects/$PROJECT/locations/$REGION/authzPolicies?authz_policy_id=vibeflix-gateway-iap-policy" \
  -d '{
    "name": "vibeflix-gateway-iap-policy",
    "policyProfile": "REQUEST_AUTHZ",
    "action": "CUSTOM",
    "target": {
      "resources": [
        "projects/'"$PROJECT"'/locations/'"$REGION"'/agentGateways/vibeflix-gateway"
      ]
    },
    "customProvider": {
      "authzExtension": {
        "resources": [
          "projects/'"$PROJECT"'/locations/'"$REGION"'/authzExtensions/vibeflix-gateway-iap-authz"
        ]
      }
    }
  }'
```

**4c-iii. Grant each caller egress to its MCP servers.** The bindings live on
the project's **IAP web** IAM resource (`roles/iap.egressor`; the Agent Registry
API has no IAM surface — all scoping is in the CEL condition via
`mcp.toolName`, the tool allowlist; tool names are unique across the three
servers, so no server attribute is needed). Members: agents use
their identity `principal://` from `deploy/agent_identities.json`; the console
app uses its `serviceAccount:` (Cloud Run has no agent identity).

By default the grants are **resource-scoped** — bound to each MCP server's
Agent-Registry entry, so they appear on the console's Agent-Platform → Policies
page (associated with that server). ⚠️ `--resource-type=agent-registry` is a
preview surface; if your gcloud rejects it, re-run with `--project-scope`
(enforces identically, but NOT shown in the console).

Fastest route — apply every [`deploy/policies.yaml`](policies.yaml) row at once:

```bash
./deploy/grant_mcp_egress.sh --dry-run        # preview
./deploy/grant_mcp_egress.sh                  # resource-scoped (console-visible)
# fallback if the preview flag is unsupported:
./deploy/grant_mcp_egress.sh --project-scope
```

Manual route — all seven grants spelled out (zsh users: run
`setopt interactive_comments` first, or the `#` comment lines execute as
commands when pasted). Each is **resource-scoped** — bound to the target MCP
server's Agent-Registry resource via `--mcp-server` (so it shows on the console
Policies page). Note the command is **`gcloud alpha iap web`** (`--mcp-server`
is not in the GA track), and the `--mcp-server` value is the server's
registryResource id (`agentregistry-…`), which the `mcpid` helper resolves:

```bash
# grant <member> <mcp-server-shortname> <title> <CEL expression>
grant() {
  printf 'expression: >-\n  %s\ntitle: %s\n' "$4" "$3" > /tmp/cond.yaml
  gcloud alpha iap web add-iam-policy-binding --project=$PROJECT --region=$REGION \
    --resource-type=agent-registry --mcp-server="$(mcpid "$2")" \
    --member="$1" --role=roles/iap.egressor --condition-from-file=/tmp/cond.yaml
}
M()     { jq -r ".\"$1\".principal" deploy/agent_identities.json; }      # agent → principal
mcpid() { gcloud alpha agent-registry services describe "$1" --project=$PROJECT \
            --location=$REGION --format='value(registryResource)' | xargs basename; }  # → agentregistry-…

# 1. brand_style → brand-style server, one tool
grant "$(M vibeflix-brand-style)" vibeflix-mcp-brand-style brand-style \
  "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['run_brand_audit']"

# 2. deal_pricing → licensing, rate card only
grant "$(M vibeflix-deal-pricing)" vibeflix-mcp-licensing deal-pricing \
  "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['get_license_pricing']"

# 3. vendor_clearance → licensing (clearance + onboarding writes)
grant "$(M vibeflix-vendor-clearance)" vibeflix-mcp-licensing vendor-clearance-licensing \
  "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['get_vendor', 'find_vendors', 'create_vendor', 'update_vendor', 'list_trademarks', 'verify_trademark_record', 'scan_global_exclusivity_clauses', 'check_vendor_eligibility']"

# 4. vendor_clearance → market
grant "$(M vibeflix-vendor-clearance)" vibeflix-mcp-market vendor-clearance-market \
  "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['scan_ecom_marketplaces', 'check_sku_volume_caps', 'capture_audit_map']"

# 5. legal → licensing (the ONLY caller allowed upsert_contract besides the app's admin stamp)
grant "$(M vibeflix-legal)" vibeflix-mcp-licensing legal \
  "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['get_vendor', 'verify_trademark_record', 'scan_global_exclusivity_clauses', 'upsert_contract', 'get_contract']"

# 6. orchestrator → licensing, READ-ONLY — its note_responder answers registry
#    questions ("what can VND-1008 produce?"):
grant "$(M vibeflix-orchestrator)" vibeflix-mcp-licensing orchestrator \
  "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['get_vendor', 'find_vendors', 'list_trademarks', 'verify_trademark_record', 'scan_global_exclusivity_clauses', 'get_contract']"

# 7. the console app → licensing (pickers, Database tab, contract reads,
#    volume-annotation upsert, demo reset) — serviceAccount, not principal://
#    ⚠️ requires the vibeflix-app SA, which step 5a creates. Either create it
#    now (gcloud iam service-accounts create vibeflix-app + sleep 30) or run
#    this one grant after 5a.
grant "serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com" vibeflix-mcp-licensing app \
  "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['list_trademarks', 'get_vendor', 'find_vendors', 'verify_trademark_record', 'scan_global_exclusivity_clauses', 'get_contract', 'upsert_contract', 'dump_stores', 'reset_vendors']"
```

(ui_renderer has no MCP dependencies → no grant, which under deny-by-default
means it can reach nothing. Attribute keys are codelab-verbatim: `mcp.toolName`
and `mcp.tool.isReadOnly` — the inconsistent casing is Google's, not a typo.
For the console-invisible fallback, swap the `grant()` body for
`gcloud iap web add-iam-policy-binding --project=$PROJECT …` with no
`--resource-type`/`--mcp-server`.)

**4c-iv. A2A egress grants (agent → agent) — ALL-TO-ALL.** Governed agent-to-agent calls
need `iap.egressor` on the TARGET agent's registry ENDPOINT. Agents registered with
`--endpoint-spec-type=no-spec` are ENDPOINT-type entries → use `--endpoint`
(NOT `--mcp-server`, NOT `--agent`, which 404s). ALPHA track:

```bash
for T in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  EP=$(gcloud alpha agent-registry services describe "vibeflix-$T-agent" --project=$PROJECT \
        --location=$REGION --format='value(registryResource)' | xargs basename)
  for C in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
    P=$(jq -r --arg k "vibeflix-$C" '.[$k].principal' deploy/agent_identities.json)
    gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry \
      --endpoint="$EP" --region=$REGION --project=$PROJECT \
      --member="$P" --role=roles/iap.egressor
  done
done
```

⚠️ **Grant ALL-TO-ALL, not just the pairs you expect** (orchestrator→domain, vendor→legal).
An *agent* endpoint advertising the aiplatform host **shadows** the `GCP aiplatform` Service
for every engine's **OWN model call** — so an engine holding no grant on the agent endpoints
gets `403 Egress request is not authorized` on its own Gemini call and dies inside
`_prepare_session` before a single line of agent code runs. Granting only the "real" A2A
pairs took our whole fleet down and looked exactly like random gateway flakiness.

⚠️ **A2A must target the MTLS url** — the one the agent endpoints are REGISTERED with
(`https://$REGION-aiplatform.mtls.googleapis.com/v1beta1/<engine>`). The gateway only
authorizes the destination it has registered: a call to the **plain** host is refused with
`403 Egress request is not authorized` *even after* adding that URL as an interface AND
granting `iap.egressor` on the endpoint (measured repeatedly — not a propagation delay).


**4c-v. Google APIs egress grants (agent → Google APIs).** Because the gateway governs all outbound connections (default-deny), the engines' own Vertex AI and logging calls (e.g. `us-central1-aiplatform.mtls.googleapis.com`) will be blocked unless explicitly granted. Grant `roles/iap.egressor` on each Google-managed registry endpoint to all 6 agent principals:

# Egress grants for regional Google APIs (Vertex AI, Logging, Telemetry):
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  P=$(jq -r --arg k "vibeflix-$A" '.[$k].principal' deploy/agent_identities.json)
  for G in gcp-aiplatform gcp-aiplatform-mtls gcp-telemetry gcp-telemetry-mtls gcp-cloudtrace gcp-cloudtrace-mtls gcp-logging gcp-logging-mtls; do
    EP=$(gcloud alpha agent-registry services describe "$G" --project=$PROJECT --location=$REGION --format='value(registryResource)' | xargs basename)
    gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry \
      --endpoint="$EP" --region=$REGION --project=$PROJECT \
      --member="$P" --role=roles/iap.egressor
  done
done

# Egress grants for global Google APIs (Pub/Sub, global Agent Registry):
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  P=$(jq -r --arg k "vibeflix-$A" '.[$k].principal' deploy/agent_identities.json)
  for G in gcp-pubsub gcp-agentregistry-global gcp-agentregistry-mtls-global; do
    EP=$(gcloud alpha agent-registry services describe "$G" --project=$PROJECT --location=global --format='value(registryResource)' | xargs basename)
    gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry \
      --endpoint="$EP" --region=global --project=$PROJECT \
      --member="$P" --role=roles/iap.egressor
  done
done

**4c-vi. iamcredentials egress (REQUIRED for MCP).** The gateway is default-deny
over *everything* outbound — including the call the engine makes to MINT its MCP
token. Without these two endpoints registered + granted, `IDTokenCredentials.refresh()`
is itself blocked and every MCP call 401s with no obvious cause:

```bash
for pair in "gcp-iamcredentials|https://iamcredentials.googleapis.com" \
            "gcp-iamcredentials-mtls|https://iamcredentials.mtls.googleapis.com"; do
  N="${pair%%|*}"; U="${pair##*|}"
  gcloud alpha agent-registry services create "$N" --project=$PROJECT --location=$REGION \
    --display-name="GCP ${N#gcp-}" --endpoint-spec-type=no-spec \
    --interfaces="[{url=\"$U\",protocolBinding=\"jsonrpc\"}]"
done
for N in gcp-iamcredentials gcp-iamcredentials-mtls; do
  EP=$(gcloud alpha agent-registry services describe "$N" --project=$PROJECT \
        --location=$REGION --format='value(registryResource)' | xargs basename)
  for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
    P=$(jq -r --arg k "vibeflix-$A" '.[$k].principal' deploy/agent_identities.json)
    gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry \
      --endpoint="$EP" --region=$REGION --project=$PROJECT \
      --member="$P" --role=roles/iap.egressor
  done
done
```

(`deploy/grant_agent_iam.sh` re-applies the egressor half of this on every run.)

⚠️ **OPEN (tests/a2a/README.md):** the CONSOLE APP (a plain SA, not an agent
identity) making governed A2A calls returns `403 Egress` even after granting it.
The app must reach orchestrator/ui_renderer by a NON-governed path (direct engine
A2A, or gateway INGRESS) — the egress grants above do NOT fix the app. Last item.

**4d. Point MCP invocation at a dedicated invoker SA.** The gateway has no
backend-egress SA of its own (its `serviceExtensionsServiceAccount` only calls
the IAP hook) — per the codelab, backend calls ride a **user-supplied MCP
invoker SA**, passed when agents attach to the gateway (`--mcp-invoker-sa`).
Create it and make it (plus the console app) the only invokers:

```bash
gcloud iam service-accounts create vibeflix-mcp-invoker --display-name "Vibeflix MCP invoker (gateway egress)"
sleep 30
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  gcloud run services add-iam-policy-binding $S --region $REGION \
    --member serviceAccount:vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com --role roles/run.invoker
done
# (the console app ALSO keeps direct access — that grant is in step 5a, where
#  its service account is created)
# remove any leftover direct grants (yours, the agents') once the gateway path works:
#   gcloud run services remove-iam-policy-binding … --role roles/run.invoker
```

**4e. Attach the agents to the gateway — this governs A2A too.** Per the
[Agent Gateway overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview),
the gateway proxies **"all HTTP-based traffic, including MCP and A2A"** — so
attachment isn't only about tools: it's the enforcement point for
**agent-to-agent calls**. Concretely for this mesh: register the agents
themselves in the Agent Registry (agents register like MCP servers —
`agent-registry services create … --agent-spec-type/--agent-spec-content` with
the A2A card), and then, since **unregistered destinations are blocked and
registered ones are deny-by-default**, `vibeflix-legal` becomes uncallable
except by principals you explicitly grant — per `policies.yaml`'s
`a2a_policies`, ONLY vendor_clearance:

```bash
# A2A egress grant — same mechanism as 4c-iii: a condition YAML scoping the
# grant to the legal destination. ⚠️ The A2A destination attribute key is NOT
# in public docs yet (verified MCP keys: mcp.toolName, mcp.tool.isReadOnly).
# Verify the key from the gateway's IAP request logs on first call, then:
cat > /tmp/cond_vc_to_legal.yaml <<EOF
expression: >-
  api.getAttribute('iap.googleapis.com/<A2A destination attribute>', '') == 'vibeflix-legal'
title: vendor-clearance-to-legal-only
EOF
gcloud iap web add-iam-policy-binding --project=$PROJECT \
  --member="$(jq -r '."vibeflix-vendor-clearance".principal' deploy/agent_identities.json)" \
  --role=roles/iap.egressor \
  --condition-from-file=/tmp/cond_vc_to_legal.yaml
# Deny-by-default protects legal even before this grant exists — the grant is
# what ALLOWS vendor_clearance, not what blocks the others.
```

The gateway itself has **no public URL** —
its surface is an mTLS **Private Service Connect** attachment, consumed by
Agent Runtime on the agent's behalf. So agents are not "re-pointed at a gateway
URL": they are **attached by reference at deploy time**, and then discover MCP
servers from the Agent Registry through the gateway (no `MCP_*_URL` env needed
at all). Per the codelab's agent deploy:

⚠️ **BEFORE attaching**: the gateway is default-deny for ALL egress — including
Google's own endpoints. An attached agent loses Gemini/telemetry/sessions unless
the platform endpoints are registered + granted first:
```bash
# (while-read, not `set -- $VAR` — zsh doesn't word-split variables)
# We support an optional third column to override location (defaulting to $REGION)
# Global resolve services like Pub/Sub and global Agent Registry MUST be global.
while read -r NAME URL LOC; do
  LOC=${LOC:-$REGION}
  gcloud alpha agent-registry services create "gcp-$NAME" \
    --project=$PROJECT --location=$LOC --display-name="GCP $NAME" \
    --endpoint-spec-type=no-spec \
    --interfaces='[{url="'$URL'",protocolBinding="JSONRPC"}]' \
    || echo "  (gcp-$NAME may already exist)"
done <<EOF
aiplatform https://$REGION-aiplatform.googleapis.com
aiplatform-mtls https://$REGION-aiplatform.mtls.googleapis.com
agentregistry https://$REGION-agentregistry.googleapis.com
agentregistry-mtls https://$REGION-agentregistry.mtls.googleapis.com
agentregistry-global https://agentregistry.googleapis.com global
agentregistry-mtls-global https://agentregistry.mtls.googleapis.com global
telemetry https://telemetry.googleapis.com
telemetry-mtls https://telemetry.mtls.googleapis.com
cloudtrace https://cloudtrace.googleapis.com
cloudtrace-mtls https://cloudtrace.mtls.googleapis.com
logging https://logging.googleapis.com
logging-mtls https://logging.mtls.googleapis.com
pubsub https://pubsub.googleapis.com global
EOF
# NOTE: the -mtls variants matter — gateway-attached engines egress over mTLS,
# so plain telemetry.googleapis.com being registered isn't enough for traces.
# egress to them for EVERY agent (principalSet — REBUILT here; a fresh shell
# won't have $AGENTS_SET from 3a, and an empty ORG/PN silently matches nothing):
ORG=$(gcloud organizations list --format 'value(ID)' | head -1)
PN=$(gcloud projects describe $PROJECT --format 'value(projectNumber)')
AGENTS_SET="principalSet://agents.global.org-$ORG.system.id.goog/attribute.platformContainer/aiplatform/projects/$PN"
echo "$AGENTS_SET"   # sanity: BOTH numbers filled
gcloud iap web add-iam-policy-binding --project=$PROJECT --condition=None \
  --member="$AGENTS_SET" --role=roles/iap.egressor
# CALLER agents (orchestrator, vendor_clearance) list the registry at runtime to
# resolve engines via AgentRegistry — grant the whole agent set read access:
gcloud projects add-iam-policy-binding $PROJECT --condition=None \
  --member="$AGENTS_SET" --role=roles/agentregistry.viewer
```

**Attach each engine** (PATCH its deployment spec; repeat per engine or loop):

```bash
GW="projects/$PROJECT/locations/$REGION/agentGateways/vibeflix-gateway"
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' deploy/agent_identities.json)
  curl -s -X PATCH -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d '{"spec":{"deploymentSpec":{"agentGatewayConfig":{"agentToAnywhereConfig":{"agentGateway":"'$GW'"}}}}}' \
    "https://$REGION-aiplatform.googleapis.com/v1beta1/$ENG?updateMask=spec.deploymentSpec.agentGatewayConfig" \
    | jq -r '"'$A': " + (if .error then "⚠️ " + .error.message else "attached (op " + (.name|split("/")|last) + ")" end)'
done
```

✅ **Verify:** every engine shows a non-null gateway binding:

```bash
# ⚠️ FIRST wait for the attach operations — the PATCH returns immediately but
# the attachment only lands when its LRO completes (~2-4 min, an engine redeploy).
# Verifying too soon shows NOT ATTACHED. Poll them, or just wait a few minutes.
# NOTE: the LIST endpoint omits deploymentSpec — must GET each engine:
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' deploy/agent_identities.json)
  GW=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://$REGION-aiplatform.googleapis.com/v1beta1/$ENG" \
    | jq -r '.spec.deploymentSpec.agentGatewayConfig.agentToAnywhereConfig.agentGateway // "NOT ATTACHED"')
  echo "vibeflix-$A → $(basename $GW)"
done   # all 6 should print vibeflix-gateway
```

The plain `adk deploy agent_engine` CLI has no gateway flag yet — gateway
attachment goes through the engine's config (the same surface the codelab's
`deploy_agent.py` drives). Until your agents are attached, they keep working
via their direct `MCP_*_URL` env (grant `vibeflix-agents` `run.invoker` on the
three services if you removed it). Once attached, the flow becomes:
*agent (its own identity, mTLS) → gateway (IAP policy check per 4c) →
vibeflix-mcp-invoker OIDC → Cloud Run MCP* — agents hold no per-MCP credentials.

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
# app resolves ui_renderer via the Agent Registry (AgentRegistry.list_agents):
gcloud projects add-iam-policy-binding $PROJECT --condition=None \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/agentregistry.viewer
gcloud storage buckets add-iam-policy-binding gs://vibeflix-request-image \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/storage.objectAdmin
gcloud pubsub topics add-iam-policy-binding vibeflix-mesh-events \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.publisher
gcloud pubsub subscriptions add-iam-policy-binding vibeflix-mesh-events-app-cloud \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/pubsub.subscriber
# direct MCP access (the app cannot ride the gateway's mTLS/PSC surface):
gcloud run services add-iam-policy-binding vibeflix-mcp-licensing --region $REGION \
  --member serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com --role roles/run.invoker

# 5b. collect the wiring: each agent's A2A base URL from its engine resource name
#     (no gcloud surface for Agent Runtime — REST + jq)
#     ⚠️ Always use the mtls.googleapis.com endpoint so that container egress
#     routes correctly through the Agent Gateway over the mTLS secure path.
A2A_BASE="https://$REGION-aiplatform.mtls.googleapis.com/v1beta1"
BASE="https://$REGION-aiplatform.googleapis.com/v1beta1"
ENGINES_JSON=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$BASE/projects/$PROJECT/locations/$REGION/reasoningEngines")
eng() { jq -r --arg n "$1" '[.reasoningEngines[] | select(.displayName==$n)][0].name' <<< "$ENGINES_JSON"; }
BRAND_URL=$A2A_BASE/$(eng vibeflix-brand-style)
VENDOR_URL=$A2A_BASE/$(eng vibeflix-vendor-clearance)
PRICING_URL=$A2A_BASE/$(eng vibeflix-deal-pricing)
UI_URL=$A2A_BASE/$(eng vibeflix-ui-renderer)
# MCP_*_URL: the DIRECT run.app /mcp URLs (step 2) — the app cannot ride the
# gateway's mTLS/PSC surface; its access is IAM + the read-only IAP grant.

# 5c. build + deploy
export AR=$REGION-docker.pkg.dev/$PROJECT/vibeflix   # (re-set; step-2 var may be gone)
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


## Step 6

> **Engine traces (OTEL → Cloud Trace / Observability panel).** Engine OTLP export
> is OFF by default: on the py3.14 engine base its HTTP exporter crashes
> (pyOpenSSL "Context has already been used") and egresses over mTLS. To enable:
> (1) register the -mtls telemetry/logging/cloudtrace egress endpoints (step 4);
> (2) redeploy engines with `TELEMETRY=on ./deploy/deploy_agents_a2a.py <agent>`,
> which sets `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true` +
> `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` (gRPC exporter avoids the pyOpenSSL/HTTP path).
> ⚠️ gRPC-exporter fix is coded but NOT yet live-verified — confirm traces land.

## Step 6 — Application Topology (agents + MCP in Cloud Monitoring)

The Monitoring [Application Topology](https://docs.cloud.google.com/monitoring/docs/application-topology)
view has native **Agent** and **MCP server** nodes; edges come from OTel traces.

```bash
gcloud services enable observability.googleapis.com apphub.googleapis.com \
  cloudtrace.googleapis.com telemetry.googleapis.com --project=$PROJECT
gcloud apphub applications create vibeflix-mesh \
  --location=$REGION --scope-type=REGIONAL \
  --display-name="Vibeflix mesh" --project=$PROJECT
# then register the Cloud Run services (app + 3 MCPs) into it:
#   gcloud apphub applications services list/create — or console: App Hub →
#   vibeflix-mesh → Services → register discovered services.
```

- Engines already emit traces (`--otel_to_cloud` in step 3) → they appear as Agent nodes.
- MCP servers appear via trace DISCOVERY (agent tool-call spans) — per the doc's
  limitations, MCP connections show only when App Hub status is `discovered`.
- Viewers need `roles/apphub.viewer` + the App Topology Viewer role.

✅ **Verify:** Monitoring → Application Topology shows agent nodes with edges to
MCP-server nodes after a few audits' worth of traffic.

---

## Troubleshooting A2A Routing & Authentication

If you observe `403 Forbidden` or `default_denied` errors during agent-to-agent (A2A) calls:

1. **Verify A2A Endpoint Domains (`mtls.googleapis.com`)**:
   - Ensure A2A base URLs are configured to use `https://<region>-aiplatform.mtls.googleapis.com` rather than `googleapis.com`.
   - The default `googleapis.com` resolves to a private IP (`240.0.0.2`) inside Reasoning Engine containers and gets blocked by the Agent Gateway's default egress policies.
   
2. **Workload Identity OIDC Limitations**:
   - Engines running under `AGENT_IDENTITY` (rather than a Google Service Account) cannot generate/sign OpenID Connect (OIDC) ID tokens via the metadata server for Cloud Run targets.
   - Outbound requests through the Agent Gateway must authenticate using the principal's OAuth2 access token (`google.auth.default()`). The Agent Gateway (IAP) accepts and validates this access token, then signs the request to the target Cloud Run service on the agent's behalf.

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

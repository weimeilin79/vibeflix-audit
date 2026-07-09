# Vibeflix cloud deployment — SRE runbook (Terraform + scripts)

Automated, repeatable route driven by **Terraform modules**
(`deploy/terraform/{mcp,agents}`) and **shell scripts** (`deploy/*.sh`). Project
and region are variables throughout. For the command-by-command learning route,
see [`instruction-dev.md`](instruction-dev.md).

```
browser → app (Cloud Run) → 5 agents (Agent Runtime, agent identities)
                              → Agent Gateway (policies.yaml) → 3 MCPs (Cloud Run)
          foundations underneath: Firestore (seeded) · Pub/Sub · GCS · RAG corpus
```

**Tooling (one-time):**

```bash
gcloud auth login && gcloud auth application-default login
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
uv tool install google-agents-cli

cat >> deploy/.env <<'EOF'    # every script + module reads these
PROJECT=pokedemo-test
REGION=us-central1
EOF
```

> **Code prerequisite (once, before step 3):** the cloud-auth changes must be in
> the repo — identity-token headers on `mcp_clients` + the A2A calls, and
> `_CONTRACTS` moved to Firestore. Steps 1–2 work without them.

---

## Step 1 — Foundations: Pub/Sub, database, seed

```bash
./deploy/setup_firestore.sh      # creates the vibeflix-registry db + SEEDS it:
                                 #   registries (brand/legal/market policy),
                                 #   vendors (CRUD store), audit_history smoke test
./deploy/setup_pubsub.sh         # telemetry topic + the local bridge subscription
./deploy/setup_legal_rag.sh      # legal RAG corpus → note RAG_CORPUS for step 3
```

Re-seed anytime with `deploy/reset_firestore.sh` (restores pristine demo state,
also clears the upload bucket). The cloud app's *own* telemetry subscription is
created by Terraform in step 3 (`vibeflix-mesh-events-app-cloud`).

---

## Step 2 — MCP servers → Cloud Run (with credentials)

Owned by `deploy/terraform/mcp/`: 3 services, 2 least-privilege runtime SAs
(licensing = Firestore RW; market/brand_style = RO; both topic-scoped Pub/Sub
publish; **no GCS, no Vertex**), all `--no-allow-unauthenticated`.

```bash
./deploy/deploy_mcp_cloudrun.sh              # 3 × Cloud Build → terraform apply
terraform -chdir=deploy/terraform/mcp output mcp_urls
```

Verify: anonymous `curl -X POST <url>` → **403**; authed
(`-H "Authorization: Bearer $(gcloud auth print-identity-token)"`) → non-403.

Access control today = IAM `run.invoker` per caller. **In step 4 the Agent
Gateway takes this over** — its SA becomes the only invoker and per-tool policies
apply. Until then, grant the agents temporary direct access when you reach step 3:

```bash
terraform -chdir=deploy/terraform/mcp apply \
  -var project=$PROJECT -var region=$REGION -var deployer=user:$(gcloud config get-value account) \
  -var 'invoker_members=["serviceAccount:vibeflix-agents@'$PROJECT'.iam.gserviceaccount.com"]'
```

---

## Step 3 — Agents → Agent Runtime + agent identity

**3a. IAM (Terraform).** `deploy/terraform/agents/` creates the runtime
identities and grants — agents: Vertex (Gemini + RAG) + topic-scoped publish +
asset-bucket read; app: Vertex, Firestore, upload bucket, its own subscription:

```bash
terraform -chdir=deploy/terraform/agents init
terraform -chdir=deploy/terraform/agents apply -var project=$PROJECT -var region=$REGION
```

**3b. Deploy the 5 engines.** `deploy_agents.sh` drives the ADK 2.3 CLI: each
agent folder (with its own `requirements.txt`; the script VENDORS `vibeflix-common`
into each folder — the private repo can't be pip-cloned) becomes one engine; A2A serving is automatic; the script passes the
runtime SA via the engine-config file, ships env via `--env_file`, and re-runs
UPDATE the same engine (it resolves `--agent_engine_id` by display name instead
of duplicating). Engines are regional; Gemini's `global` location ships in each
agent's own `.env` — those files are gitignored, so on a fresh clone the script
**creates any missing `agents/<name>/.env`** from `$PROJECT` automatically:

```bash
export $(terraform -chdir=deploy/terraform/mcp output -json mcp_urls | jq -r 'to_entries[] | "\(.key)=\(.value)"')
export RAG_CORPUS=<from setup_legal_rag>

./deploy/deploy_agents.sh                    # brand_style, deal_pricing, ui_renderer, legal
export LEGAL_A2A_URL=<legal's A2A card URL — printed above>
./deploy/deploy_agents.sh vendor_clearance
```

Deploys take 5–10 min each and continue server-side if the CLI times out.

**3c. Agent identity & A2A routing (preview).** `deploy_agents.sh` finishes by running
`deploy/enable_agent_identity_and_a2a.py`, which sets the engine config field
`identity_type = types.IdentityType.AGENT_IDENTITY` (v1beta1 update), configures `agent_framework = "a2a"`, and embeds the A2A class methods on every
vibeflix engine. It writes each agent's `principal://…` to
`deploy/agent_identities.json` — those principals are what step 4's policies and
per-agent IAM bind to. Re-run it standalone anytime:

```bash
PROJECT=$PROJECT REGION=$REGION python deploy/enable_agent_identity_and_a2a.py
```

If the preview misbehaves, the shared `vibeflix-agents` SA from 3a is the
fallback (policies then bind per registered-agent entry instead — coarser).

Verify each engine: `agents-cli run --url https://$REGION-aiplatform.googleapis.com/v1beta1/<engine resource name> --mode adk "ping"`.

---

## Step 4 — Agent Gateway + policies

```bash
./deploy/setup_gateway.sh
```

⚠️ **Preview surfaces** — the script prints each sub-step's intent + current
command shape; adjust to your gcloud release if a surface moved. Sub-steps:

1. **Register** the 3 MCP servers (run.app `/mcp` URLs) and the 5 agents (A2A
   card URLs) in the **Agent Registry**.
2. **Create the gateway** (`vibeflix-gateway`) attached to the 3 MCP entries;
   note its endpoint + service agent SA.
3. **Apply [`deploy/policies.yaml`](policies.yaml)** — deny-by-default per-agent
   tool allowlists (brand_style → `run_brand_audit` only; legal is the sole
   `upsert_contract` writer; the app gets the read-only set + demo reset).
4. **Rewire MCP auth to the gateway** — gateway SA becomes the *only* invoker:

```bash
terraform -chdir=deploy/terraform/mcp apply \
  -var project=$PROJECT -var region=$REGION -var deployer=user:$(gcloud config get-value account) \
  -var 'invoker_members=["serviceAccount:<GATEWAY_SA>"]'
```

Then redeploy the agents with `MCP_*_URL` = the **gateway** endpoints
(re-run `./deploy/deploy_agents.sh` with new exports). MCP auth is now:
*agent → its own identity token → gateway → policy check → gateway OIDC → Cloud Run.*
No agent ever holds per-MCP credentials.

Optional Gemini Enterprise visibility, per agent:

```bash
agents-cli publish gemini-enterprise --registration-type a2a \
  --agent-card-url <card url> --gemini-enterprise-app-id <GE app> --display-name "Vibeflix <agent>"
```

---

## Step 5 — Frontend (console app) → Cloud Run

```bash
gcloud builds submit . --config deploy/cloudbuild-app.yaml \
  --substitutions "_IMAGE=$REGION-docker.pkg.dev/$PROJECT/vibeflix/app"

gcloud run deploy vibeflix-app \
  --image "$REGION-docker.pkg.dev/$PROJECT/vibeflix/app" \
  --region "$REGION" --service-account "vibeflix-app@$PROJECT.iam.gserviceaccount.com" \
  --memory 1Gi --min-instances 0 --max-instances 2 --allow-unauthenticated \
  --set-env-vars "RUN_LOCAL=false,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=global,\
FIRESTORE_DATABASE=vibeflix-registry,PUBSUB_TOPIC=vibeflix-mesh-events,PUBSUB_SUBSCRIPTION=vibeflix-mesh-events-app-cloud,\
REQUEST_IMAGE_BUCKET=vibeflix-request-image,\
BRAND_STYLE_A2A_URL=<engine url>,VENDOR_CLEARANCE_A2A_URL=<engine url>,DEAL_PRICING_A2A_URL=<engine url>,UI_RENDERER_A2A_URL=<engine url>,\
MCP_LICENSING_URL=<gateway url>,MCP_MARKET_URL=<gateway url>,MCP_BRAND_STYLE_URL=<gateway url>"
```

(`--allow-unauthenticated` for the demo console; front with IAP for real use.)

**End-to-end verify:** open the app URL, run a standard audit — reports render,
graph LEDs light from the `-app-cloud` subscription, contract lands in history.

---

## Teardown (reverse order)

```bash
gcloud run services delete vibeflix-app --region $REGION
# delete the 5 reasoning engines + gateway/registry entries (console or CLI)
terraform -chdir=deploy/terraform/agents destroy -var project=$PROJECT -var region=$REGION
terraform -chdir=deploy/terraform/mcp destroy -var project=$PROJECT -var region=$REGION -var deployer=user:<you>
```

## IAM summary

| Identity | Grants |
|---|---|
| `vibeflix-mcp-licensing` | Firestore RW, topic-scoped publish |
| `vibeflix-mcp-readonly` | Firestore RO, topic-scoped publish |
| agent identities (or `vibeflix-agents`) | Vertex (Gemini+RAG), topic-scoped publish, asset-bucket read, gateway access per policies.yaml |
| `vibeflix-app` | Vertex (engine A2A), Firestore RW, upload-bucket admin, own subscription pull, gateway read-only set |
| gateway SA | **sole** `run.invoker` on the 3 MCP services |

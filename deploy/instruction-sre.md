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
# enable every API used across the runbook (idempotent):
gcloud services enable --project=$PROJECT firestore.googleapis.com pubsub.googleapis.com \
  storage.googleapis.com run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com aiplatform.googleapis.com agentregistry.googleapis.com \
  networkservices.googleapis.com networksecurity.googleapis.com iap.googleapis.com \
  observability.googleapis.com apphub.googleapis.com cloudtrace.googleapis.com telemetry.googleapis.com

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

**3b. Deploy each agent via the A2A TEMPLATE — one at a time, in dependency order.**
`deploy/deploy_agents_a2a.py` wraps each `root_agent` in the SDK's `A2aAgent` template, so the engine's container genuinely serves platform A2A (`/a2a/v1/card`, `message/send`). Identity + service account + OTel are set at create time — no post-deploy configure pass needed. Re-running a name updates the same engine.

First, resolve `RAG_CORPUS`:
```bash
export RAG_CORPUS=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/$REGION/ragCorpora" \
  | jq -r '[.ragCorpora[] | select(.displayName=="vibeflix-legal-kb")][0].name')
echo "RAG_CORPUS=$RAG_CORPUS"

# Staging bucket for source tarballs:
gsutil mb -p $PROJECT -l $REGION gs://$PROJECT-vibeflix-agent-staging 2>/dev/null || true

export MCP_LICENSING_URL=$(gcloud run services describe vibeflix-mcp-licensing --region $REGION --format 'value(status.url)')/mcp
export MCP_MARKET_URL=$(gcloud run services describe vibeflix-mcp-market --region $REGION --format 'value(status.url)')/mcp
export MCP_BRAND_STYLE_URL=$(gcloud run services describe vibeflix-mcp-brand-style --region $REGION --format 'value(status.url)')/mcp

# Deploy first 4 agents:
.venv/bin/python deploy/deploy_agents_a2a.py brand_style
.venv/bin/python deploy/deploy_agents_a2a.py deal_pricing
.venv/bin/python deploy/deploy_agents_a2a.py ui_renderer
.venv/bin/python deploy/deploy_agents_a2a.py legal
```

**3c. Deploy vendor_clearance** (requires legal's A2A base):
```bash
BASE=https://$REGION-aiplatform.googleapis.com/v1beta1
A2A_BASE=https://$REGION-aiplatform.mtls.googleapis.com/v1beta1
ENGINES_JSON=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$BASE/projects/$PROJECT/locations/$REGION/reasoningEngines")
eng() { jq -r --arg n "$1" '[.reasoningEngines[] | select(.displayName==$n)][0].name' <<< "$ENGINES_JSON"; }
export LEGAL_A2A_URL=$A2A_BASE/$(eng vibeflix-legal)

.venv/bin/python deploy/deploy_agents_a2a.py vendor_clearance
```

**3d. Deploy the ORCHESTRATOR last** (requires the domain engines):
```bash
ENGINES_JSON=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$BASE/projects/$PROJECT/locations/$REGION/reasoningEngines")
export BRAND_STYLE_A2A_URL=$A2A_BASE/$(eng vibeflix-brand-style)
export VENDOR_CLEARANCE_A2A_URL=$A2A_BASE/$(eng vibeflix-vendor-clearance)
export DEAL_PRICING_A2A_URL=$A2A_BASE/$(eng vibeflix-deal-pricing)

.venv/bin/python deploy/deploy_agents_a2a.py orchestrator
```

**3e. Record identities for step 4** (identity was enabled at creation — this reads principals into `deploy/agent_identities.json`):
```bash
PROJECT=$PROJECT REGION=$REGION .venv/bin/python deploy/collect_agent_identities.py
```

**3f. Grant Project-level IAM Roles to Agent Principals:**
Since each reasoning engine is deployed with `identity_type = AGENT_IDENTITY`, they execute as their own unique `principal://...` identity rather than using the shared `vibeflix-agents` service account. Therefore, you must grant the necessary Google Cloud permissions directly to each agent's principal:

```bash
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  P=$(jq -r --arg k "vibeflix-$A" '.[$k].principal' deploy/agent_identities.json)
  for R in roles/aiplatform.user roles/aiplatform.agentDefaultAccess roles/logging.logWriter roles/monitoring.metricWriter roles/browser roles/agentregistry.viewer; do
    gcloud projects add-iam-policy-binding $PROJECT --member="$P" --role="$R" --condition=None
  done
done
```

Verify each engine: `agents-cli run --url https://$REGION-aiplatform.googleapis.com/v1beta1/<engine resource name> --mode adk "ping"`.

---

## Step 4 — Agent Gateway + policies

```bash
./deploy/setup_gateway.sh
```

Surfaces per the [Agent Gateway codelab](https://codelabs.developers.google.com/cloudnet-agent-gateway)
(⚠️ still preview — spellings can drift). Run sub-steps individually with
`./deploy/setup_gateway.sh registry|gateway|policies|rewire`. Sub-steps:

1. **Registry** — `gcloud alpha agent-registry services create` per MCP server AND per agent (`vibeflix-<name>-agent`, `--endpoint-spec-type=no-spec`; each agent's interface URL = mTLS aiplatform host + its OWN engine path from `agent_identities.json`, since interface URLs are unique registry-wide — 8 entries total; requires step 3 done first, the script skips agents and tells you if identities are missing)
   AND per agent (agents use `--agent-spec-type` with their A2A card) — the
   gateway governs **A2A between agents too** (deny-by-default: only
   vendor_clearance gets egress to legal, per `policies.yaml` `a2a_policies`).
   Per MCP server,
   with a **tool spec** (auto-generated from the live server by
   `deploy/make_toolspec.py` → `deploy/toolspecs/*.json`) and the run.app `/mcp`
   URL as the JSONRPC interface.
2. **Gateway** — `gcloud alpha network-services agent-gateways import` from the
   generated `deploy/agent-gateway.yaml` (protocols `[MCP]`, governed access
   path `AGENT_TO_ANYWHERE`, bound to the project registry). Note the endpoint
   + service agent SA from the describe output.
3. **Policies** — an IAP authz extension imported (`iapPolicyVersion: "V1"`),
   bound to the gateway via an `AuthzPolicy` (REQUEST_AUTHZ, REST), then ALL
   per-caller tool grants applied from [`deploy/policies.yaml`](policies.yaml)
   in one shot:

   ```bash
   ./deploy/grant_mcp_egress.sh --dry-run   # preview all six grants
   ./deploy/grant_mcp_egress.sh             # roles/iap.egressor + CEL per row
   ```

   Also grant egress permissions for Google APIs (Vertex AI, logging, telemetry) to all agents:

   ```bash
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
   ```

   Members come from `deploy/agent_identities.json` (agents → `principal://…`;
   the console app → its `serviceAccount:`).
4. **Rewire MCP invocation** — the gateway exposes no backend-egress SA; create
   the dedicated `vibeflix-mcp-invoker` SA (passed as the agents' MCP invoker
   when they attach to the gateway) and make it + the console app the invokers:

```bash
terraform -chdir=deploy/terraform/mcp apply \
  -var project=$PROJECT -var region=$REGION -var deployer=user:$(gcloud config get-value account) \
  -var 'invoker_members=["serviceAccount:vibeflix-mcp-invoker@'$PROJECT'.iam.gserviceaccount.com","serviceAccount:vibeflix-app@'$PROJECT'.iam.gserviceaccount.com"]'
# (create vibeflix-mcp-invoker first: gcloud iam service-accounts create vibeflix-mcp-invoker)
# The app keeps DIRECT access — the gateway is consumed over mTLS/PSC by Agent
# Runtime agents (attached by reference), not by public-HTTPS callers.
```

Then **attach the agents to the gateway by reference** (the gateway has no public URL — it's an mTLS/PSC surface consumed by Agent Runtime):

```bash
GW="projects/$PROJECT/locations/$REGION/agentGateways/vibeflix-gateway"
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' deploy/agent_identities.json)
  curl -s -X PATCH -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d '{"spec":{"deploymentSpec":{"agentGatewayConfig":{"agentToAnywhereConfig":{"agentGateway":"'$GW'"}}}}}' \
    "https://$REGION-aiplatform.googleapis.com/v1beta1/$ENG?updateMask=spec.deploymentSpec.agentGatewayConfig" \
    | jq -r '"'$A': " + (if .error then "⚠️ " + .error.message else "attached" end)'
done
```

Wait 2-4 minutes for the LROs to finish (this is a full engine redeploy under the hood), then verify:

```bash
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' deploy/agent_identities.json)
  GW_BOUND=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://$REGION-aiplatform.googleapis.com/v1beta1/$ENG" \
    | jq -r '.spec.deploymentSpec.agentGatewayConfig.agentToAnywhereConfig.agentGateway // "NOT ATTACHED"')
  echo "vibeflix-$A → $(basename $GW_BOUND)"
done
```

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
MCP_LICENSING_URL=<licensing run.app URL>/mcp,MCP_MARKET_URL=<market run.app URL>/mcp,MCP_BRAND_STYLE_URL=<brand-style run.app URL>/mcp"
# (the app uses the DIRECT service URLs — it cannot ride the gateway's mTLS/PSC surface)
```

(`--allow-unauthenticated` for the demo console; front with IAP for real use.)

**End-to-end verify:** open the app URL, run a standard audit — reports render,
graph LEDs light from the `-app-cloud` subscription, contract lands in history.

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

1. **A2A base URLs must use the PLAIN endpoint, NOT `mtls.googleapis.com`**:
   - Use `https://<region>-aiplatform.googleapis.com/v1beta1/<engine>`.
   - ⚠️ An earlier revision of this runbook told you to use the **mtls** host. That is wrong and it breaks A2A: `vibeflix_common/a2a_engine.py` authenticates with a bearer access token and **no client certificate**, and an mTLS endpoint requires one — so it answers **`401 Unauthorized`**. Symptom: `[vendor_clearance] legal call failed: HTTPError: 401 Client Error: Unauthorized for url: https://…-aiplatform.mtls.googleapis.com/…/a2a/v1/message:send`, and the callee engine shows *zero* activity (it never saw the request).
   - The plain host **and** its in-container private-IP form (`240.0.0.2`) are BOTH registered as interfaces on the `gcp-aiplatform` registry endpoint and granted `iap.egressor` to every agent principal, so gateway egress permits the plain host. (Registering only the mtls variant is what made the plain host look "blocked" in the first place.)
   - Rule of thumb: **mtls endpoints are for the Google client libraries** (which do present a client cert); **our raw `requests`/`httpx` A2A calls use the plain endpoint.**
   
2. **Workload Identity OIDC Limitations** — and how the agent ACTUALLY reaches an MCP:
   - Engines running under `AGENT_IDENTITY` (rather than a Google Service Account) cannot generate/sign OpenID Connect (OIDC) ID tokens via the metadata server for Cloud Run targets. There is no service account behind the metadata server, so `fetch_id_token()` fails.
   - ⚠️ **The Agent Gateway does NOT sign the request to Cloud Run on the agent's behalf.** (An earlier revision of this runbook claimed it did — it does not, and believing that costs days.) There is no invoker-SA field on `agentToAnywhereConfig`, on the Agent Registry service, or in the gcloud surface. The gateway *authorizes* egress (IAP `roles/iap.egressor` + per-tool CEL); it does not *authenticate* you to the backend.
   - An access token is NOT enough. Cloud Run rejects it — measured directly against the MCP:

     | token presented | Cloud Run |
     |---|---|
     | OAuth2 access token | **401** `"the access token could not be verified"` |
     | audience-bound OIDC ID token | **200** |
     | no token | **403** |

   - **The agent must mint its own ID token by impersonating an invoker SA** (`MCP_INVOKER_SA` → `impersonated_credentials.IDTokenCredentials`, audience = `scheme://host` of the MCP). This is the same mechanism as the Agent Gateway codelab's `--mcp-invoker-sa`, which merely injects that env var. See instruction-dev "The MCP auth rule" for the three grants required.

3. **`403 Egress request is not authorized` — the rule, and the trap**:

   **The rule (simple).** *"The destination endpoint must be explicitly registered as a Service in the Agent Registry"*, and the calling agent's principal must hold `roles/iap.egressor` on it. Default-deny; anything else 403s. `deploy/grant_agent_iam.sh` grants **every registered `GCP *` endpoint** to **every** agent — derived from the registry, never hand-maintained. (Ours was hand-maintained and drifted: it omitted `agentregistry` ×4, `pubsub`, and `telemetry-regional`.)

   Know which host you actually egress to: `GOOGLE_CLOUD_LOCATION=global` ⇒ genai + `VertexAiSessionService` use the **global** host `https://aiplatform.googleapis.com` (`gcp-aiplatform-global`); pinned to a region ⇒ `https://REGION-aiplatform.googleapis.com` (`gcp-aiplatform`). Register and grant **both**.

   **⚠️ The trap: two Services claiming the SAME HOST.** The agent registry entries (`vibeflix-<agent>-agent`) must advertise the **mtls URL only**. We added the plain URL (`https://REGION-aiplatform.googleapis.com/v1beta1/<engine>`) as a second interface so a plain bearer-token A2A client would be authorized — but that host is already claimed by the `GCP aiplatform` Service. With two Services claiming one host the gateway denied **ALL aiplatform egress, fleet-wide**: every engine died in `_prepare_session`/`create_session` or on the Gemini call, before any agent code ran. Reverting the agent endpoints to mtls-only restored the fleet. **If a fleet-wide 403 appears right after you touch the registry, look for a host collision first** — it masquerades perfectly as random gateway flakiness.

   ⏱️ **Propagation is 2–5 minutes.** After any registry/egressor change, WAIT before judging. We tested a correct fix 40s after applying it, saw a 403, and wrongly discarded it — twice.

4. **Symptom → cause quick table**:

   | symptom | actual cause |
   |---|---|
   | `403 Egress request is not authorized`, seemingly at random | `GOOGLE_CLOUD_LOCATION=global` → egress to the unregistered GLOBAL aiplatform host (see 3) |
   | MCP `401`, `Failed to get tools from toolset` | agent identity can't mint an ID token — impersonation not wired (see above) |
   | `Failed to create MCP session: unhandled errors in a TaskGroup`, **intermittent**, MCP logs show `200 OK` | NOT auth — a **TimeoutError**. `StreamableHTTPConnectionParams.timeout` defaults to **5s** and ADK applies it to the whole `list_tools()` handshake. A cold agent-identity connection must first mint an impersonated ID token (2 round trips, themselves gateway-governed) and blows the budget. Fix: `timeout=60` + `prewarm_id_token()` at import (both in `mcp_clients.py`). The TaskGroup swallows the cause — always dig out the real sub-exception before assuming auth |
   | MCP `403` | no `Authorization` header at all — token minting threw and the header was dropped |
   | `TASK_STATE_FAILED` before agent code runs | principal missing `roles/aiplatform.agentContextEditor` → `create_session()` fails in `_prepare_session` |
   | 401/403 everywhere, but console policies look right | engines were DELETED and recreated → new engine ids → new principals → every grant orphaned. Re-run `grant_agent_iam.sh` |
   | code fix "deployed" but behaviour unchanged | stale vendored copy. `_vendored_common()` must re-copy every deploy (it now does) |
   | console **playground** returns `400` / code `9` | expected: A2A-only engines expose `on_message_send` (`api_mode=a2a_extension`), not `query`. The playground calls `:query`, the container 404s, the platform wraps it as `FAILED_PRECONDITION`. Drive these engines over `/a2a/v1/message:send` instead |

4. **Verifying a layer actually passes — do NOT trust the agent's own answer.**
   A compliance agent whose toolset failed to load will still emit a confident,
   clean verdict: we observed `status: "success"`, `findings: []` and a plausible
   `checks_run` list while the MCP had **never been called once**. The model was
   inventing the check names (they changed between runs). Always confirm against
   the *backend's* log, not the agent's report:

   ```bash
   # the ONLY trustworthy proof a governed MCP tool call really executed:
   gcloud logging read 'resource.type="cloud_run_revision" AND
     resource.labels.service_name="vibeflix-mcp-brand-style"' \
     --project=$PROJECT --limit=200 --freshness=15m \
     --format='value(textPayload)' | grep -oiE 'CallToolRequest|ListToolsRequest' | sort | uniq -c
   # ListToolsRequest only  → the tool was LISTED, never CALLED → the verdict is fabricated
   # CallToolRequest >= 1   → the tool really ran

   # what the ENGINE got back from the MCP (401 = impersonation not working):
   gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND
     resource.labels.reasoning_engine_id="<ID>"' --project=$PROJECT --limit=300 --freshness=15m \
     --format='value(textPayload)' | grep -oE 'HTTP Request: POST https://vibeflix-mcp[^"]*"HTTP/1.1 [0-9]{3}'
   ```

   The agents now **fail closed** (`vibeflix_common/tool_guard.py`): if a required
   tool is absent from the LlmRequest, the model is never called and the agent
   returns `status: "error"` instead of a fake pass.

---

## Teardown (reverse order)

> ⚠️ Teardown is for tearing the demo DOWN — never as a step in "redeploying".
> Deleting an engine mints a new id on recreate, hence a new `principal://`, which
> orphans every IAM grant and registry endpoint. To ship new code, just re-run
> `deploy_agents_a2a.py <name>`: it UPDATES in place and keeps the engine id.

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

#!/usr/bin/env bash
# deploy_app.sh — build + deploy the console app (frontend + shared A2A task store) to Cloud Run.
#
# Resolves the engine A2A URLs and MCP URLs automatically from agent_identities.json / Cloud Run,
# so you don't hand-fill them. The app uses the PLAIN aiplatform host for A2A (it cannot ride the
# gateway's mTLS/PSC surface — GOTCHAS.md G11).
#
# ORDER: deploy the app AFTER the agents (it needs their engine ids) and BEFORE
# grant_agent_iam.sh + engine pass-2 (they read the app's URL as TASK_STORE_URL).
#
# ⚠️ --timeout 1800 is also LOAD-BEARING. Cloud Run's DEFAULT is 300s, and /api/audit/stream is
# an SSE stream held open for the whole audit. A run longer than five minutes gets its stream
# severed mid-flight: the console stops updating and shows no error, while the agents carry on
# working for a browser that is no longer listening. Measured on vibeflix-demo: ordinary audits
# finish in 80-165s and pass, while VENDOR ONBOARDING — which adds the legal handoff, RAG
# retrieval and a human-in-the-loop question — reliably crossed 300s and was cut every time,
# looking exactly like a hung mesh. The engines logged 300+ more lines after each cut.
# ⚠️ --min/--max-instances=1 is LOAD-BEARING: the app hosts the shared task store and the single
#    Pub/Sub consumer; a 2nd instance split-brains both. Config from deploy/.env.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"; REGION="${REGION:-us-central1}"
IDS="$HERE/agent_identities.json"
[ -f "$IDS" ] || { echo "ERROR: $IDS missing — deploy the agents first (Steps 2-5)." >&2; exit 1; }

A2A="https://$REGION-aiplatform.googleapis.com/v1beta1"          # PLAIN host (G11: app ≠ mtls)
eng() { jq -r --arg k "$1" '.[$k].engine // empty' "$IDS"; }
run() { gcloud run services describe "$1" --region "$REGION" --project "$PROJECT" --format 'value(status.url)'; }

IMG="$REGION-docker.pkg.dev/$PROJECT/vibeflix/app"
DEF="gs://${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image}/vendor_request_refine.png"

# A build submitted from INSIDE a build has no default service account to fall back on. Projects
# created after Google's 2024 change get no <number>@cloudbuild.gserviceaccount.com, and the
# Compute Engine default SA only exists once compute.googleapis.com is enabled — so on a fresh
# project a nested `gcloud builds submit` with no --service-account is rejected outright.
# cloudbuild-mesh.yaml exports the account the outer build runs as; pass it down when present.
# Empty (a normal laptop/Cloud Shell run) → the flag is omitted and gcloud picks the default.
# A plain string, not an array: `"${arr[@]}"` on an EMPTY array is an "unbound variable" error
# under `set -u` on bash 3.2, which is still what macOS ships — and these scripts are run by
# hand there. The value never contains spaces, so unquoted expansion is safe and portable.
BUILD_SA_FLAG=""
[ -n "${CLOUDBUILD_SA:-}" ] && BUILD_SA_FLAG="--service-account=projects/$PROJECT/serviceAccounts/$CLOUDBUILD_SA"

echo "[deploy_app] building image…"
gcloud builds submit "$ROOT" --config "$HERE/cloudbuild-app.yaml" --project "$PROJECT" \
  $BUILD_SA_FLAG \
  --substitutions "_IMAGE=$IMG,_DEFAULT_IMAGE=$DEF"

echo "[deploy_app] resolving engine + MCP URLs…"
BRAND=$(eng vibeflix-brand-style); VC=$(eng vibeflix-vendor-clearance); DP=$(eng vibeflix-deal-pricing)
UIR=$(eng vibeflix-ui-renderer);   ORCH=$(eng vibeflix-orchestrator)
MLIC="$(run vibeflix-mcp-licensing)/mcp"; MMKT="$(run vibeflix-mcp-market)/mcp"; MBS="$(run vibeflix-mcp-brand-style)/mcp"

# The console's "Refresh Backend" button rolls every engine's replicas, which clears the credential
# fault the mesh develops as it runs (eng-report/UPSTREAM-BUG-mtls-handshake-agent-identity.md).
#
#   MESH_ROLLOUT=off (or unset)  button hidden — the default for a hand-rolled install
#   MESH_ROLLOUT=open            button shown, no key. deploy/.env.example ships this, so
#                                workshop and one-click installs get it; those projects are
#                                short-lived and single-owner.
#   + MESH_ADMIN_KEY set         button shown, key required. For a long-lived shared project
#                                whose console is on the internet.
#
# This app is deployed --allow-unauthenticated because the browser has to load the console,
# so the rollout endpoints refuse every call unless one of the enabling modes is in force.
MESH_ADMIN_ENV=",MESH_ROLLOUT=${MESH_ROLLOUT:-off}"
# How old the replicas may get before the console forces a refresh. Optional; default 45 min.
[ -n "${MESH_ROLLOUT_MAX_AGE_MIN:-}" ] && \
  MESH_ADMIN_ENV="$MESH_ADMIN_ENV,MESH_ROLLOUT_MAX_AGE_MIN=${MESH_ROLLOUT_MAX_AGE_MIN}"
# A refresh finishes when the engines ANSWER again, not on a clock — these tune that check.
for V in MESH_ROLLOUT_SETTLE_SEC MESH_ROLLOUT_READY_STREAK MESH_ROLLOUT_READY_TIMEOUT_SEC; do
  eval "VAL=\${$V:-}"
  [ -n "$VAL" ] && MESH_ADMIN_ENV="$MESH_ADMIN_ENV,$V=$VAL"
done
if [ -n "${MESH_ADMIN_KEY:-}" ]; then
  MESH_ADMIN_ENV="$MESH_ADMIN_ENV,MESH_ADMIN_KEY=${MESH_ADMIN_KEY}"
fi
case "${MESH_ROLLOUT:-off}:${MESH_ADMIN_KEY:+key}" in
  off:*)    echo "[deploy_app] Refresh Backend button: HIDDEN (set MESH_ROLLOUT=open in deploy/.env)" ;;
  *:key)    echo "[deploy_app] Refresh Backend button: SHOWN, key required (MESH_ADMIN_KEY is set)" ;;
  *)        echo "[deploy_app] Refresh Backend button: SHOWN, no key (short-lived project)" ;;
esac

echo "[deploy_app] deploying vibeflix-app (pinned 1/1 — load-bearing)…"
gcloud run deploy vibeflix-app --image "$IMG" \
  --region "$REGION" --project "$PROJECT" \
  --service-account "vibeflix-app@$PROJECT.iam.gserviceaccount.com" \
  --memory 1Gi --min-instances 1 --max-instances 1 --allow-unauthenticated \
  --timeout 1800 \
  --set-env-vars "RUN_LOCAL=false,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=global,FIRESTORE_DATABASE=${FIRESTORE_DATABASE:-vibeflix-registry},PUBSUB_TOPIC=${PUBSUB_TOPIC:-vibeflix-mesh-events},PUBSUB_SUBSCRIPTION=${PUBSUB_SUBSCRIPTION:-vibeflix-mesh-events-app-cloud},REQUEST_IMAGE_BUCKET=${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image},TASK_STORE_KEY=${TASK_STORE_KEY:?set TASK_STORE_KEY in deploy/.env},BRAND_STYLE_A2A_URL=$A2A/$BRAND,VENDOR_CLEARANCE_A2A_URL=$A2A/$VC,DEAL_PRICING_A2A_URL=$A2A/$DP,UI_RENDERER_A2A_URL=$A2A/$UIR,ORCHESTRATOR_A2A_URL=$A2A/$ORCH,MCP_LICENSING_URL=$MLIC,MCP_MARKET_URL=$MMKT,MCP_BRAND_STYLE_URL=$MBS$MESH_ADMIN_ENV"

echo "[deploy_app] done → $(run vibeflix-app)"
echo "[deploy_app] NEXT: ./deploy/setup_gateway.sh (Step 7) registers this URL, then redeploy the"
echo "             engines (pass 2) so they pick up TASK_STORE_URL: deploy/deploy_agents_a2a.py"

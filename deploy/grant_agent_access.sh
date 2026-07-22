#!/usr/bin/env bash
# grant_agent_access.sh <agent> — the INTERIM (pre-gateway) IAM one agent needs to run and be
# tested, granted to its OWN principal. Run it right AFTER deploying an agent (workshop Steps
# 2-5), once its principal exists in agent_identities.json.
#
# It grants exactly the pre-gateway subset of grant_agent_iam.sh, for ONE agent:
#   • project roles on the agent's principal (incl. agentContextEditor — the agent writes its
#     own sessions; without it every task poll 401s and the agent hangs forever);
#   • the MCP-invoker SA + run.invoker on the MCP services, and this agent's right to impersonate
#     it (an agent identity has no SA of its own, so it mints an MCP OIDC token by impersonation).
#
# Step 7 (setup_gateway.sh → grant_agent_iam.sh) then layers the GATEWAY egress governance on
# top. Idempotent — safe to re-run.
#
#   ./deploy/grant_agent_access.sh brand-style
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"; REGION="${REGION:-us-central1}"
A="${1:?usage: grant_agent_access.sh <agent>  (brand-style|deal-pricing|legal|vendor-clearance|ui-renderer|orchestrator)}"
IDENT="$HERE/agent_identities.json"
INVOKER_SA="${MCP_INVOKER_SA:-vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com}"

PRINCIPAL="$(jq -r --arg k "vibeflix-$A" '.[$k].principal // empty' "$IDENT" 2>/dev/null || true)"
[ -n "$PRINCIPAL" ] || { echo "ERROR: no principal for vibeflix-$A in $IDENT — deploy the agent first." >&2; exit 1; }
echo "[grant] vibeflix-$A → …${PRINCIPAL##*/}"

# 1) The MCP-invoker SA (shared; created once).
gcloud iam service-accounts describe "$INVOKER_SA" --project="$PROJECT" >/dev/null 2>&1 \
  || gcloud iam service-accounts create vibeflix-mcp-invoker --project="$PROJECT" \
       --display-name "Vibeflix MCP invoker (agent-identity ID-token source)"

# 2) The invoker SA may call the IAM-gated MCP Cloud Run services.
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  gcloud run services add-iam-policy-binding "$S" --region="$REGION" --project="$PROJECT" \
    --member="serviceAccount:$INVOKER_SA" --role=roles/run.invoker -q >/dev/null
done

# 3) This agent's principal gets the project roles it needs to run — the same set your live
#    deployment grants (grant_agent_iam.sh + terraform/agents), minus the gateway egress (Step 7).
#    logging/monitoring writers + pubsub.publisher are what emit the telemetry Step 8 shows.
for R in roles/aiplatform.user roles/aiplatform.agentDefaultAccess roles/aiplatform.agentContextEditor \
         roles/logging.logWriter roles/monitoring.metricWriter \
         roles/browser roles/agentregistry.viewer roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="$PRINCIPAL" --role="$R" --condition=None -q >/dev/null
done

# …and publish rights on the mesh-telemetry topic (the live-graph events in Step 8).
gcloud pubsub topics add-iam-policy-binding "${PUBSUB_TOPIC:-vibeflix-mesh-events}" --project="$PROJECT" \
  --member="$PRINCIPAL" --role=roles/pubsub.publisher >/dev/null

# 4) …and it may impersonate the invoker SA to mint the MCP OIDC token.
gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" --project="$PROJECT" \
  --member="$PRINCIPAL" --role=roles/iam.serviceAccountTokenCreator -q >/dev/null

echo "[grant] done — vibeflix-$A can reach Gemini + the MCP servers (pre-gateway)."

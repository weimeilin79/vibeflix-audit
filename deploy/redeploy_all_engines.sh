#!/usr/bin/env bash
#
# redeploy_all_engines.sh — Redeploy all 6 reasoning engines with updated cloud_auth.py
# and then re-attach them to the Agent Gateway.
#
set -euo pipefail

export PROJECT=pokedemo-test
export REGION=us-central1
export BUCKET=vibeflix-artifacts
export RAG_CORPUS=projects/pokedemo-test/locations/us-central1/ragCorpora/893665458870288384
export RAG_LOCATION=us-central1

echo "[redeploy] Fetching MCP server URLs..."
export MCP_LICENSING_URL=$(gcloud run services describe vibeflix-mcp-licensing --region $REGION --project $PROJECT --format 'value(status.url)')/mcp
export MCP_MARKET_URL=$(gcloud run services describe vibeflix-mcp-market --region $REGION --project $PROJECT --format 'value(status.url)')/mcp
export MCP_BRAND_STYLE_URL=$(gcloud run services describe vibeflix-mcp-brand-style --region $REGION --project $PROJECT --format 'value(status.url)')/mcp

echo "[redeploy] Resolving Agent A2A URLs..."
export LEGAL_A2A_URL="https://${REGION}-aiplatform.googleapis.com/v1beta1/$(jq -r '."vibeflix-legal".engine' deploy/agent_identities.json)"
export BRAND_STYLE_A2A_URL="https://${REGION}-aiplatform.googleapis.com/v1beta1/$(jq -r '."vibeflix-brand-style".engine' deploy/agent_identities.json)"
export VENDOR_CLEARANCE_A2A_URL="https://${REGION}-aiplatform.googleapis.com/v1beta1/$(jq -r '."vibeflix-vendor-clearance".engine' deploy/agent_identities.json)"
export DEAL_PRICING_A2A_URL="https://${REGION}-aiplatform.googleapis.com/v1beta1/$(jq -r '."vibeflix-deal-pricing".engine' deploy/agent_identities.json)"

echo "[redeploy] Redeploying all 6 reasoning engines..."
.venv/bin/python -u deploy/deploy_agents_a2a.py

echo "[redeploy] Re-attaching all 6 engines to the Agent Gateway..."
GW="projects/$PROJECT/locations/$REGION/agentGateways/vibeflix-gateway"
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' deploy/agent_identities.json)
  curl -s -X PATCH -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d '{"spec":{"deploymentSpec":{"agentGatewayConfig":{"agentToAnywhereConfig":{"agentGateway":"'$GW'"}}}}}' \
    "https://$REGION-aiplatform.googleapis.com/v1beta1/$ENG?updateMask=spec.deploymentSpec.agentGatewayConfig" \
    | jq -r '"'$A': " + (if .error then "⚠️ " + .error.message else "attached (op " + (.name|split("/")|last) + ")" end)'
done

echo "[redeploy] Redeployment initiated. Please allow a few minutes for LRO operations to complete."

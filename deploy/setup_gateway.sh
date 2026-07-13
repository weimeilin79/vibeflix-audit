#!/usr/bin/env bash
#
# setup_gateway.sh — Agent Registry + Agent Gateway + access policies (phase 2C/2D).
#
# Surfaces per the Agent Gateway codelab
# (https://codelabs.developers.google.com/cloudnet-agent-gateway):
#   registry:  gcloud alpha agent-registry services create … (tool-spec + interface URL)
#   gateway:   gcloud alpha network-services agent-gateways import … (YAML)
#   policies:  IAP authz extension + per-agent egress grants (roles/iap.egressor,
#              CEL conditions on tool attributes) — mapping in deploy/policies.yaml
#
# ⚠️ PREVIEW surfaces — spellings can drift between gcloud releases; each step is
# a thin block so fixes are one-line. Config from deploy/.env.
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"
REGION="${REGION:-us-central1}"
STEP="${1:-all}"

echo "[gateway] project=$PROJECT region=$REGION step=$STEP"

# ── 1/4 REGISTRY: register the 3 MCP servers (tool spec + interface URL) ──────
if [ "$STEP" = all ] || [ "$STEP" = registry ]; then
  mkdir -p "$HERE/toolspecs"
  for S in licensing market brand-style; do
    URL=$(gcloud run services describe "vibeflix-mcp-$S" --region "$REGION" --format 'value(status.url)')/mcp
    SPEC="$HERE/toolspecs/$S.json"
    [ -s "$SPEC" ] || { echo "  generating tool spec $SPEC…";
      "$HERE/../.venv/bin/python" "$HERE/make_toolspec.py" "$URL" > "$SPEC"; }
    gcloud alpha agent-registry services create "vibeflix-mcp-$S" \
      --project "$PROJECT" --location "$REGION" \
      --display-name "Vibeflix MCP $S" \
      --mcp-server-spec-type=tool-spec \
      --mcp-server-spec-content="$(cat "$SPEC")" \
      --interfaces="url=$URL,protocolBinding=JSONRPC" \
      || echo "  (vibeflix-mcp-$S may already be registered — continuing)"
  done
  # The 5 AGENTS are registry entries too (A2A policies + console list + gateway
  # destinations all key off these; unregistered destinations are blocked).
  # Interface URLs must be UNIQUE — each agent registers with its own engine path
  # (from agent_identities.json, produced by step 3 / enable_agent_identity.py).
  if [ ! -s "$HERE/agent_identities.json" ]; then
    echo "  ⚠️ skipping AGENT registration: deploy/agent_identities.json missing —"
    echo "     deploy the agents (step 3) first, then re-run: ./deploy/setup_gateway.sh registry"
  else
  for A in brand-style vendor-clearance deal-pricing legal ui-renderer; do
    ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' "$HERE/agent_identities.json")
    gcloud alpha agent-registry services create "vibeflix-$A-agent" \
      --project "$PROJECT" --location "$REGION" \
      --display-name "Vibeflix $A agent" \
      --endpoint-spec-type=no-spec \
      --interfaces='[{url="https://'"$REGION"'-aiplatform.mtls.googleapis.com/v1beta1/'"$ENG"'",protocolBinding="jsonrpc"}]' \
      || echo "  (vibeflix-$A-agent may already be registered — continuing)"
  done
  fi
  gcloud alpha agent-registry services list --project "$PROJECT" --location "$REGION" \
    --format "value(displayName,name)"
fi

# ── 2/4 GATEWAY: one governed MCP front door over the registry ────────────────
if [ "$STEP" = all ] || [ "$STEP" = gateway ]; then
  cat > "$HERE/agent-gateway.yaml" <<EOF
name: vibeflix-gateway
protocols: [MCP]
googleManaged:
  governedAccessPath: AGENT_TO_ANYWHERE
registries:
  - "//agentregistry.googleapis.com/projects/$PROJECT/locations/$REGION"
EOF
  # (Backends are public run.app URLs — the codelab's networkConfig/dnsPeering
  #  block is only needed for private-VPC MCP backends.)
  gcloud alpha network-services agent-gateways import vibeflix-gateway \
    --source="$HERE/agent-gateway.yaml" --location="$REGION" --project="$PROJECT"
  gcloud alpha network-services agent-gateways describe vibeflix-gateway \
    --location="$REGION" --project="$PROJECT"
  echo "  → note the gateway ENDPOINT + service agent SA from the describe output."
fi

# ── 3/4 POLICIES: IAP authz extension + per-agent egress grants ───────────────
if [ "$STEP" = all ] || [ "$STEP" = policies ]; then
  cat > "$HERE/iap-authz-extension.yaml" <<EOF
name: vibeflix-gateway-iap-authz
service: iap.googleapis.com
failOpen: true
timeout: 5s
metadata:
  iapPolicyVersion: "V1"
EOF
  gcloud beta service-extensions authz-extensions import vibeflix-gateway-iap-authz \
    --source="$HERE/iap-authz-extension.yaml" --location="$REGION" --project="$PROJECT" \
    || echo "  (authz extension may already exist — continuing)"
  # Bind the extension to the gateway (AuthzPolicy, REQUEST_AUTHZ profile).
  curl -fsS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -X POST "https://networksecurity.googleapis.com/v1alpha1/projects/$PROJECT/locations/$REGION/authzPolicies?authz_policy_id=vibeflix-gateway-iap-policy" \
    -d '{
      "name": "vibeflix-gateway-iap-policy",
      "policyProfile": "REQUEST_AUTHZ",
      "action": "CUSTOM",
      "target": {"resources": ["projects/'"$PROJECT"'/locations/'"$REGION"'/agentGateways/vibeflix-gateway"]},
      "customProvider": {"authzExtension": {"resources": ["projects/'"$PROJECT"'/locations/'"$REGION"'/authzExtensions/vibeflix-gateway-iap-authz"]}}
    }' || echo "  (authz policy may already exist — continuing)"
  echo
  # Per-caller tool grants: ALL rows of deploy/policies.yaml as roles/iap.egressor
  # bindings with CEL server+tool conditions (members from agent_identities.json).
  if [ -f "$HERE/agent_identities.json" ]; then
    "$HERE/grant_mcp_egress.sh"
  else
    echo "  ⚠️ deploy/agent_identities.json missing — deploy the agents (step 3)"
    echo "     first, then run: ./deploy/grant_mcp_egress.sh"
  fi
fi

# ── 4/4 REWIRE: the gateway SA becomes the ONLY direct invoker on the MCPs ────
if [ "$STEP" = all ] || [ "$STEP" = rewire ]; then
  gcloud iam service-accounts describe "vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1 \
    || gcloud iam service-accounts create vibeflix-mcp-invoker --display-name "Vibeflix MCP invoker (gateway egress)"
  echo "  then: terraform -chdir=$HERE/terraform/mcp apply \\"
  echo "    -var project=$PROJECT -var region=$REGION -var deployer=user:\$(gcloud config get-value account) \\"
  echo "    -var 'invoker_members=[\"serviceAccount:vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com\",\"serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com\"]'"
  echo "  (pass vibeflix-mcp-invoker as --mcp-invoker-sa when attaching agents to the gateway;"
  echo "   the app keeps DIRECT access — the mTLS/PSC surface is agents-only)"
  echo "  then redeploy the agents with MCP_*_URL = the gateway endpoint."
fi

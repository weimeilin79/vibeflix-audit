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
failOpen: false
timeout: 1s
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
  echo "  Per-agent tool access = IAP egress grants (roles/iap.egressor) with CEL"
  echo "  conditions. Apply ONE grant per row of deploy/policies.yaml, e.g.:"
  echo
  echo "    # brand_style may reach ONLY the brand-style MCP server:"
  echo "    gcloud iap … add-iam-policy-binding (roles/iap.egressor) \\"
  echo "      --member 'principal://…vibeflix-brand-style…'  # deploy/agent_identities.json"
  echo "      --condition-expression \"api.getAttribute('iap.googleapis.com/mcp.server', '') == 'vibeflix-mcp-brand-style'\""
  echo
  echo "    # tool-level (e.g. app read-only) via tool attributes:"
  echo "    --condition-expression \"api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true\""
  echo
  echo "  (the codelab wraps these in scripts/grant_agent_mcp_egress.sh — same idea)"
fi

# ── 4/4 REWIRE: the gateway SA becomes the ONLY direct invoker on the MCPs ────
if [ "$STEP" = all ] || [ "$STEP" = rewire ]; then
  echo "  terraform -chdir=$HERE/terraform/mcp apply \\"
  echo "    -var project=$PROJECT -var region=$REGION -var deployer=user:\$(gcloud config get-value account) \\"
  echo "    -var 'invoker_members=[\"serviceAccount:<GATEWAY_SA>\",\"serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com\"]'"
  echo "  (the app keeps DIRECT access — the gateway's mTLS/PSC surface is for agents)"
  echo "  then redeploy the agents with MCP_*_URL = the gateway endpoint."
fi

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
. "$HERE/lib_setup.sh"
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
    ensure_created "registry entry vibeflix-mcp-$S" \
      gcloud alpha agent-registry services create "vibeflix-mcp-$S" \
      --project "$PROJECT" --location "$REGION" \
      --display-name "Vibeflix MCP $S" \
      --mcp-server-spec-type=tool-spec \
      --mcp-server-spec-content="$(cat "$SPEC")" \
      --interfaces="url=$URL,protocolBinding=JSONRPC"
  done
  # ALL 6 AGENTS are registry entries too (A2A policies + console list + gateway
  # destinations all key off these; unregistered destinations are blocked). The
  # ORCHESTRATOR must be here as well — the app calls it over A2A, and grant_agent_iam.sh
  # binds egress on EVERY agent endpoint (all-to-all); omit it and its endpoint never
  # exists, so those grants are silently skipped and the mesh 403s. (Fresh-project trap:
  # this loop used to list only the 5 domain agents.)
  # Interface URLs must be UNIQUE — each agent registers with its own engine path
  # (from agent_identities.json, produced by step 3 / enable_agent_identity.py).
  if [ ! -s "$HERE/agent_identities.json" ]; then
    echo "  ⚠️ skipping AGENT registration: deploy/agent_identities.json missing —"
    echo "     deploy the agents (step 3) first, then re-run: ./deploy/setup_gateway.sh registry"
  else
  for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
    ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine' "$HERE/agent_identities.json")
    ensure_created "registry entry vibeflix-$A-agent" \
      gcloud alpha agent-registry services create "vibeflix-$A-agent" \
      --project "$PROJECT" --location "$REGION" \
      --display-name "Vibeflix $A agent" \
      --endpoint-spec-type=no-spec \
      --interfaces='[{url="https://'"$REGION"'-aiplatform.mtls.googleapis.com/v1beta1/'"$ENG"'",protocolBinding="jsonrpc"}]' 
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
  ensure_created "the IAP authz extension" \
    gcloud beta service-extensions authz-extensions import vibeflix-gateway-iap-authz \
    --source="$HERE/iap-authz-extension.yaml" --location="$REGION" --project="$PROJECT"
  # Bind the extension to the gateway (AuthzPolicy, REQUEST_AUTHZ profile).
  ensure_created "the gateway authz policy" \
    curl -fsS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -X POST "https://networksecurity.googleapis.com/v1alpha1/projects/$PROJECT/locations/$REGION/authzPolicies?authz_policy_id=vibeflix-gateway-iap-policy" \
    -d '{
      "name": "vibeflix-gateway-iap-policy",
      "policyProfile": "REQUEST_AUTHZ",
      "action": "CUSTOM",
      "target": {"resources": ["projects/'"$PROJECT"'/locations/'"$REGION"'/agentGateways/vibeflix-gateway"]},
      "customProvider": {"authzExtension": {"resources": ["projects/'"$PROJECT"'/locations/'"$REGION"'/authzExtensions/vibeflix-gateway-iap-authz"]}}
    }' 
  echo
  # EVERYTHING the agents need, in one idempotent pass — grant_agent_iam.sh registers the
  # endpoints nothing else creates (gcp-iamcredentials, global aiplatform), grants the
  # project roles, the Google-API egress, the ALL-TO-ALL A2A egress, the MCP invoker SA
  # (impersonation — how an agent identity authenticates to Cloud Run at all), and then
  # calls grant_mcp_egress.sh for the per-tool CEL allowlist.
  #
  # Do NOT go back to calling grant_mcp_egress.sh alone: it covers only the MCP tool
  # policies. Every other grant was applied by hand during bring-up, which meant a fresh
  # project rebuilt from this repo failed exactly the way ours did.
  if [ -f "$HERE/agent_identities.json" ]; then
    PROJECT="$PROJECT" REGION="$REGION" "$HERE/grant_agent_iam.sh"
  else
    echo "  ⚠️ deploy/agent_identities.json missing — deploy the agents (step 3)"
    echo "     first, then run: ./deploy/grant_agent_iam.sh"
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

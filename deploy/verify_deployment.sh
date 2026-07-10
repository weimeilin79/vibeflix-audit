#!/usr/bin/env bash
#
# verify_deployment.sh — READ-ONLY audit of the cloud deployment, step by step.
# Prints ✅/❌ per check so you always know exactly where the deployment stands.
# Safe to run anytime; changes nothing.
#
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"; REGION="${REGION:-us-central1}"
TOK=$(gcloud auth print-access-token)
PASS=0; FAIL=0
ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
have() { [ -n "$1" ] && [ "$1" != "null" ]; }

echo "═══ Step 1 — foundations"
have "$(gcloud firestore databases describe --database=vibeflix-registry --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "Firestore db vibeflix-registry" || bad "Firestore db vibeflix-registry"
have "$(gcloud pubsub topics describe vibeflix-mesh-events --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "Pub/Sub topic" || bad "Pub/Sub topic vibeflix-mesh-events"
have "$(gcloud pubsub subscriptions describe vibeflix-mesh-events-app-cloud --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "cloud app subscription" || bad "subscription vibeflix-mesh-events-app-cloud (created in step 3a terraform or 1c)"
N=$(curl -s -H "Authorization: Bearer $TOK" "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/$REGION/ragCorpora" | jq '.ragCorpora | length' 2>/dev/null)
[ "${N:-0}" -ge 1 ] && ok "RAG corpus ($N)" || bad "RAG corpus"

echo "═══ Step 2 — MCP servers on Cloud Run"
for S in licensing market brand-style; do
  URL=$(gcloud run services describe "vibeflix-mcp-$S" --region "$REGION" --project "$PROJECT" --format 'value(status.url)' 2>/dev/null)
  if have "$URL"; then
    CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/mcp")
    [ "$CODE" = "403" ] && ok "vibeflix-mcp-$S up, anonymous blocked (403)" || bad "vibeflix-mcp-$S anonymous returned $CODE (want 403)"
    ACODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/mcp" -H "Authorization: Bearer $(gcloud auth print-identity-token)")
    [ "$ACODE" != "403" ] && ok "vibeflix-mcp-$S authed reachable ($ACODE)" || bad "vibeflix-mcp-$S authed still 403 — you lack run.invoker"
  else bad "vibeflix-mcp-$S not deployed"; fi
done

echo "═══ Step 3 — engines + identity"
ENG=$(curl -s -H "Authorization: Bearer $TOK" "https://$REGION-aiplatform.googleapis.com/v1beta1/projects/$PROJECT/locations/$REGION/reasoningEngines")
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  ROWS=$(echo "$ENG" | jq --arg n "vibeflix-$A" '[.reasoningEngines[] | select(.displayName==$n)]')
  CNT=$(echo "$ROWS" | jq 'length')
  IDY=$(echo "$ROWS" | jq -r '.[0].spec.effectiveIdentity // empty')
  if [ "$CNT" = "1" ] && have "$IDY"; then ok "vibeflix-$A: 1 engine, identity on"
  elif [ "$CNT" = "0" ]; then bad "vibeflix-$A: not deployed"
  elif [ "$CNT" != "1" ]; then bad "vibeflix-$A: $CNT engines (duplicates — delete extras)"
  else bad "vibeflix-$A: deployed but NO agent identity"; fi
done
[ -s "$HERE/agent_identities.json" ] && ok "agent_identities.json present" || bad "agent_identities.json missing (run enable_agent_identity.py)"

echo "═══ Step 4 — registry, gateway, policies"
REG=$(gcloud alpha agent-registry services list --project "$PROJECT" --location "$REGION" --format 'value(name)' 2>/dev/null)
M=$(echo "$REG" | grep -c "vibeflix-mcp-" || true); AG=$(echo "$REG" | grep -c -- "-agent" || true)
[ "$M" = "3" ] && ok "registry: 3 MCP servers" || bad "registry: $M/3 MCP servers"
[ "$AG" = "6" ] && ok "registry: 6 agents" || bad "registry: $AG/6 agents (step 4a-ii — orchestrator too)"
have "$(gcloud alpha network-services agent-gateways describe vibeflix-gateway --location "$REGION" --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "gateway vibeflix-gateway" || bad "gateway vibeflix-gateway"
have "$(gcloud beta service-extensions authz-extensions describe vibeflix-gateway-iap-authz --location "$REGION" --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "IAP authz extension" || bad "IAP authz extension (4c-i)"
AP=$(curl -s -H "Authorization: Bearer $TOK" "https://networksecurity.googleapis.com/v1alpha1/projects/$PROJECT/locations/$REGION/authzPolicies" | jq -r '.authzPolicies[]?.name' | grep -c vibeflix-gateway-iap-policy || true)
[ "${AP:-0}" -ge 1 ] && ok "authz policy bound to gateway" || bad "authz policy binding (4c-ii)"
G=$(gcloud iap web get-iam-policy --project "$PROJECT" --format json 2>/dev/null | jq '[.bindings[]? | select(.role=="roles/iap.egressor") | select((.condition.expression // "") | contains("mcp.toolName"))] | length')
[ "${G:-0}" -ge 5 ] && ok "IAP egress grants ($G with corrected conditions)" || bad "IAP egress grants: ${G:-0}/5+ (run grant_mcp_egress.sh)"
for S in licensing market brand-style; do
  INV=$(gcloud run services get-iam-policy "vibeflix-mcp-$S" --region "$REGION" --project "$PROJECT" --format json 2>/dev/null | jq -r '.bindings[]? | select(.role=="roles/run.invoker") | .members[]' | grep -c "vibeflix-mcp-invoker" || true)
  [ "${INV:-0}" = "1" ] && ok "invoker SA on vibeflix-mcp-$S" || bad "invoker SA missing on vibeflix-mcp-$S (4d)"
done

echo "═══ Step 4e — gateway attachment"
ATT=$(echo "$ENG" | jq '[.reasoningEngines[] | select(.displayName // "" | startswith("vibeflix")) | select(.spec.deploymentSpec.agentGatewayConfig != null)] | length')
[ "${ATT:-0}" -ge 1 ] && ok "$ATT engine(s) attached to the gateway" || bad "no engines attached to the gateway yet (4e)"

echo "═══ Step 5 — console app"
APPURL=$(gcloud run services describe vibeflix-app --region "$REGION" --project "$PROJECT" --format 'value(status.url)' 2>/dev/null)
if have "$APPURL"; then
  R=$(curl -s "$APPURL/api/ready" | jq -r '.ready' 2>/dev/null)
  [ "$R" = "true" ] && ok "app deployed and READY" || bad "app deployed but not ready ($APPURL/api/ready)"
else bad "vibeflix-app not deployed (step 5)"; fi

echo
echo "════ RESULT: $PASS passed · $FAIL failed"

#!/usr/bin/env bash
#
# verify_deployment.sh — READ-ONLY audit of the cloud deployment, step by step.
# Prints ✅/❌ per check so you always know exactly where the deployment stands.
# Safe to run anytime; changes nothing. Exits non-zero if anything failed, so it can
# gate a deploy script.
#
#   ./deploy/verify_deployment.sh          # everything
#   ./deploy/verify_deployment.sh 3        # ONLY step 3 (engines + identity)
#   ./deploy/verify_deployment.sh 3b       # ONLY the engine FLAGS (telemetry/task store/trace)
#
# RUN IT AFTER EVERY STEP. A deploy can exit 0 and still be broken: that is exactly how
# the whole fleet ended up untraced (TELEMETRY silently defaulted off) and how the engines
# silently fell back to a per-replica task store (TASK_STORE_URL empty). The exit code of
# a deploy tells you the API accepted your request — not that the thing is there.
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
ONLY="${1:-}"                       # optional: 1 | 2 | 3 | 3b | 4 | 4e | 5
step() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

if step 1; then
echo "═══ Step 1 — foundations"
have "$(gcloud firestore databases describe --database=vibeflix-registry --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "Firestore db vibeflix-registry" || bad "Firestore db vibeflix-registry"
have "$(gcloud pubsub topics describe vibeflix-mesh-events --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "Pub/Sub topic" || bad "Pub/Sub topic vibeflix-mesh-events"
have "$(gcloud pubsub subscriptions describe vibeflix-mesh-events-app-cloud --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "cloud app subscription" || bad "subscription vibeflix-mesh-events-app-cloud (created in step 3a terraform or 1c)"
N=$(curl -s -H "Authorization: Bearer $TOK" "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/$REGION/ragCorpora" | jq '.ragCorpora | length' 2>/dev/null)
[ "${N:-0}" -ge 1 ] && ok "RAG corpus ($N)" || bad "RAG corpus"

fi

if step 2; then
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

fi

# ENG is needed by steps 3, 3b and 4e — always fetch it.
ENG=$(curl -s -H "Authorization: Bearer $TOK" "https://$REGION-aiplatform.googleapis.com/v1beta1/projects/$PROJECT/locations/$REGION/reasoningEngines")

if step 3; then
echo "═══ Step 3 — engines + identity"
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

# agent_identities.json is COMMITTED, so a fresh clone starts with the ORIGINAL project's
# ids. deploy_agents_a2a.py refuses foreign identities, but the file itself must be
# regenerated or every A2A url points at another project's engines.
PNUM=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)' 2>/dev/null)
if [ -s "$HERE/agent_identities.json" ] && have "$PNUM"; then
  FOREIGN=$(jq -r --arg n "$PNUM" '[to_entries[] | select((.value.engine // "") | contains("projects/"+$n+"/") | not) | .key] | length' "$HERE/agent_identities.json" 2>/dev/null || echo 0)
  [ "${FOREIGN:-0}" = "0" ] \
    && ok "agent_identities.json belongs to THIS project ($PNUM)" \
    || bad "agent_identities.json has $FOREIGN entries from ANOTHER project — run collect_agent_identities.py"
fi

fi

if step 3b; then
echo "═══ Step 3b — engine config (the flags a deploy can silently drop)"
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  EID=$(echo "$ENG" | jq -r --arg n "vibeflix-$A" '.reasoningEngines[] | select(.displayName==$n) | .name' | head -1)
  [ -z "$EID" ] && continue
  EV=$(curl -s -H "Authorization: Bearer $TOK" "https://$REGION-aiplatform.googleapis.com/v1beta1/$EID" \
       | jq -r '[.spec.deploymentSpec.env[]? | "\(.name)=\(.value)"] | join(" ")')
  # TELEMETRY: the traces ARE the demo. It used to default OFF, so a deploy that merely
  # FORGOT the flag untraced the whole fleet, reported success and exited 0.
  echo "$EV" | grep -q "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true" \
    && ok "vibeflix-$A: traced" || bad "vibeflix-$A: NOT TRACED (GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY≠true)"
  # TASK_STORE_URL: empty ⇒ the engine falls back to a PER-REPLICA task store and ~87% of
  # task polls 404. That is the #1 symptom of skipping the SECOND engine deploy pass.
  echo "$EV" | grep -q "TASK_STORE_URL=https://" \
    && ok "vibeflix-$A: shared task store wired" \
    || bad "vibeflix-$A: TASK_STORE_URL EMPTY → per-replica store (deploy the APP, then re-run deploy_agents_a2a.py — pass 2)"
  echo "$EV" | grep -q "A2A_TRACE_PROPAGATION=on" \
    && ok "vibeflix-$A: trace propagation on" || bad "vibeflix-$A: A2A_TRACE_PROPAGATION not on (topology page will be empty)"
done

fi

if step 4; then
echo "═══ Step 4 — registry, gateway, policies"
REG=$(gcloud alpha agent-registry services list --project "$PROJECT" --location "$REGION" --format 'value(name)' 2>/dev/null)
M=$(echo "$REG" | grep -c "vibeflix-mcp-" || true)
# NB: match vibeflix-*-agent EXACTLY — a bare `-agent` also matches the four
# gcp-agentregistry* endpoints and reports a phantom "10/6 agents".
AG=$(echo "$REG" | grep -cE "/vibeflix-[a-z-]+-agent$" || true)
[ "$M" = "3" ] && ok "registry: 3 MCP servers" || bad "registry: $M/3 MCP servers"
[ "$AG" = "6" ] && ok "registry: 6 agents" || bad "registry: $AG/6 agents (step 4a-ii — orchestrator too)"
have "$(gcloud alpha network-services agent-gateways describe vibeflix-gateway --location "$REGION" --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "gateway vibeflix-gateway" || bad "gateway vibeflix-gateway"
have "$(gcloud beta service-extensions authz-extensions describe vibeflix-gateway-iap-authz --location "$REGION" --project "$PROJECT" --format 'value(name)' 2>/dev/null)" \
  && ok "IAP authz extension" || bad "IAP authz extension (4c-i)"
AP=$(curl -s -H "Authorization: Bearer $TOK" "https://networksecurity.googleapis.com/v1alpha1/projects/$PROJECT/locations/$REGION/authzPolicies" | jq -r '.authzPolicies[]?.name' | grep -c vibeflix-gateway-iap-policy || true)
[ "${AP:-0}" -ge 1 ] && ok "authz policy bound to gateway" || bad "authz policy binding (4c-ii)"
# Egress grants are RESOURCE-scoped (--mcp-server) → check each MCP server's
# registry-resource IAM, not the project iap_web root.
G=0
for SRV in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  RR=$(gcloud alpha agent-registry services describe "$SRV" --project "$PROJECT" --location "$REGION" --format='value(registryResource)' 2>/dev/null | xargs -r basename)
  [ -n "$RR" ] || continue
  N=$(gcloud alpha iap web get-iam-policy --resource-type=agent-registry --mcp-server="$RR" --region "$REGION" --project "$PROJECT" --format json 2>/dev/null \
      | jq '[.bindings[]? | select(.role=="roles/iap.egressor")] | length' 2>/dev/null)
  G=$((G + ${N:-0}))
done
# also count project-scoped grants (--project-scope fallback mode)
PG=$(gcloud iap web get-iam-policy --project "$PROJECT" --format json 2>/dev/null | jq '[.bindings[]? | select(.role=="roles/iap.egressor") | select((.condition.expression // "") | contains("mcp.toolName"))] | length' 2>/dev/null)
G=$((G + ${PG:-0}))
[ "${G:-0}" -ge 6 ] && ok "IAP egress grants ($G on registry resources)" || bad "IAP egress grants: ${G:-0}/6+ (run grant_mcp_egress.sh)"
for S in licensing market brand-style; do
  INV=$(gcloud run services get-iam-policy "vibeflix-mcp-$S" --region "$REGION" --project "$PROJECT" --format json 2>/dev/null | jq -r '.bindings[]? | select(.role=="roles/run.invoker") | .members[]' | grep -c "vibeflix-mcp-invoker" || true)
  [ "${INV:-0}" = "1" ] && ok "invoker SA on vibeflix-mcp-$S" || bad "invoker SA missing on vibeflix-mcp-$S (4d)"
done

fi

if step 4e; then
echo "═══ Step 4e — gateway attachment (per-engine GET; list omits deploymentSpec)"
ATT=0
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  EID=$(echo "$ENG" | jq -r --arg n "vibeflix-$A" '[.reasoningEngines[]|select(.displayName==$n)][0].name')
  [ -n "$EID" ] && [ "$EID" != "null" ] || continue
  GW=$(curl -s -H "Authorization: Bearer $TOK" "https://$REGION-aiplatform.googleapis.com/v1beta1/$EID" \
    | jq -r '.spec.deploymentSpec.agentGatewayConfig.agentToAnywhereConfig.agentGateway // ""')
  [ -n "$GW" ] && ATT=$((ATT+1))
done
[ "$ATT" = "6" ] && ok "all 6 engines attached to the gateway" || bad "$ATT/6 engines attached (4e)"

fi

if step 4s; then
echo "═══ Step 4s — identities, service accounts & grants"
# WHY THIS EXISTS: every one of these has silently broken the mesh before, and each failure
# looked like something else entirely. The engine's exit code tells you nothing about them.
POL=$(gcloud projects get-iam-policy "$PROJECT" --format=json 2>/dev/null)
has_role() {  # has_role <member> <role>
  echo "$POL" | jq -e --arg m "$1" --arg r "$2" \
    '[.bindings[] | select(.role==$r) | .members[]] | index($m)' >/dev/null 2>&1
}

# ── the 6 AGENT PRINCIPALS (principal://…, NOT service accounts) ──────────────
# ⚠️ principalSet:// grants DO NOT match agent identities — they bind without error and
#    match nothing. Must be the specific principal://.
AGENT_ROLES="roles/aiplatform.user roles/aiplatform.agentDefaultAccess roles/aiplatform.agentContextEditor roles/agentregistry.viewer"
if [ -s "$HERE/agent_identities.json" ]; then
  for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
    PR=$(jq -r --arg k "vibeflix-$A" '.[$k].principal // empty' "$HERE/agent_identities.json")
    if ! have "$PR"; then bad "vibeflix-$A: no principal in agent_identities.json"; continue; fi
    MISS=""
    for R in $AGENT_ROLES; do has_role "$PR" "$R" || MISS="$MISS ${R#roles/}"; done
    # agentContextEditor is the one people forget: the agent WRITES ITS OWN SESSIONS.
    # Without it create_session() fails in _prepare_session → an opaque TASK_STATE_FAILED
    # *before any of your code runs*.
    [ -z "$MISS" ] && ok "vibeflix-$A principal: all project roles" \
                   || bad "vibeflix-$A principal MISSING:$MISS"
    # topic-scoped publish — without it the mesh telemetry never leaves the engine and the
    # console's workflow graph simply never draws (the publish error lands on an unread
    # future, so it fails SILENTLY).
    gcloud pubsub topics get-iam-policy vibeflix-mesh-events --project "$PROJECT" --format=json 2>/dev/null \
      | jq -e --arg m "$PR" '[.bindings[]? | select(.role=="roles/pubsub.publisher") | .members[]] | index($m)' >/dev/null 2>&1 \
      && ok "vibeflix-$A: pubsub.publisher on the mesh topic" \
      || bad "vibeflix-$A: NO pubsub.publisher on vibeflix-mesh-events (the graph will stay dark)"
  done
fi

# ── the APP's service account ────────────────────────────────────────────────
APP_SA="serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com"
for R in roles/aiplatform.user roles/aiplatform.agentContextEditor roles/aiplatform.agentDefaultAccess; do
  has_role "$APP_SA" "$R" && ok "app SA: ${R#roles/}" \
    || bad "app SA MISSING ${R#roles/} — without agentContextEditor every GET /a2a/v1/tasks/{id} 401s and the slow agents HANG FOREVER"
done

# ── the MCP INVOKER SA — how an AGENT_IDENTITY engine authenticates to Cloud Run ──
# An agent identity has NO service account behind the metadata server, so fetch_id_token()
# cannot work and the gateway does NOT inject a credential. The engine mints an
# audience-bound OIDC token by IMPERSONATING this SA. Needs: the env var + tokenCreator
# for each agent principal + run.invoker on each target.
INV="vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com"
if gcloud iam service-accounts describe "$INV" --project "$PROJECT" >/dev/null 2>&1; then
  ok "MCP invoker SA exists"
  IPOL=$(gcloud iam service-accounts get-iam-policy "$INV" --project "$PROJECT" --format=json 2>/dev/null)
  NTC=$(echo "$IPOL" | jq '[.bindings[]? | select(.role=="roles/iam.serviceAccountTokenCreator") | .members[]] | length' 2>/dev/null)
  [ "${NTC:-0}" -ge 6 ] && ok "agent principals can impersonate the invoker SA ($NTC tokenCreator)" \
    || bad "only ${NTC:-0}/6 principals have tokenCreator on $INV — MCP calls will 401"
  for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style vibeflix-app; do
    gcloud run services get-iam-policy "$S" --region "$REGION" --project "$PROJECT" --format=json 2>/dev/null \
      | jq -e '[.bindings[]? | select(.role=="roles/run.invoker") | .members[]] | map(select(test("vibeflix-mcp-invoker"))) | length > 0' >/dev/null 2>&1 \
      && ok "invoker SA may call $S" || bad "invoker SA CANNOT call $S (run.invoker)"
  done
else bad "MCP invoker SA $INV does not exist — every MCP call will 401 (agent identities cannot mint OIDC)"; fi

# ── MCP runtime SAs (least privilege: licensing WRITES, the other two READ) ───
gcloud iam service-accounts describe "vibeflix-mcp-licensing@$PROJECT.iam.gserviceaccount.com" --project "$PROJECT" >/dev/null 2>&1 \
  && { has_role "serviceAccount:vibeflix-mcp-licensing@$PROJECT.iam.gserviceaccount.com" roles/datastore.user \
       && ok "mcp-licensing SA: datastore.user (RW)" || bad "mcp-licensing SA missing datastore.user"; } \
  || bad "SA vibeflix-mcp-licensing missing"
gcloud iam service-accounts describe "vibeflix-mcp-readonly@$PROJECT.iam.gserviceaccount.com" --project "$PROJECT" >/dev/null 2>&1 \
  && { has_role "serviceAccount:vibeflix-mcp-readonly@$PROJECT.iam.gserviceaccount.com" roles/datastore.viewer \
       && ok "mcp-readonly SA: datastore.viewer (RO, least privilege)" || bad "mcp-readonly SA missing datastore.viewer"; } \
  || bad "SA vibeflix-mcp-readonly missing"

# ── engines must run as AGENT IDENTITY, never a service account ───────────────
for A in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  SA=$(echo "$ENG" | jq -r --arg n "vibeflix-$A" '[.reasoningEngines[]|select(.displayName==$n)][0].spec.serviceAccount // ""')
  [ -z "$SA" ] || [ "$SA" = "null" ] \
    && ok "vibeflix-$A: agent identity (no SA)" \
    || bad "vibeflix-$A runs as SERVICE ACCOUNT $SA — the Agent Identity demo is not actually being demonstrated"
done
fi

if step 5; then
echo "═══ Step 5 — console app + the SHARED A2A TASK STORE"
APPURL=$(gcloud run services describe vibeflix-app --region "$REGION" --project "$PROJECT" --format 'value(status.url)' 2>/dev/null)

# ⚠️ EXACTLY ONE INSTANCE — correctness, not cost control. The task store is a dict in the
# app process: a 2nd instance splits it and every task poll that lands on the wrong one
# 404s (the very bug the store exists to kill). It also keeps the Pub/Sub mesh subscription
# on ONE consumer — a subscription is a COMPETING-CONSUMER queue, so 2+ instances split the
# telemetry and the console's workflow graph renders only a fraction of its nodes.
if have "$APPURL"; then
  SCALE=$(gcloud run services describe vibeflix-app --region "$REGION" --project "$PROJECT" --format=json 2>/dev/null \
          | jq -r '.spec.template.metadata.annotations|"\(."autoscaling.knative.dev/minScale" // "unset")/\(."autoscaling.knative.dev/maxScale" // "unset")"')
  [ "$SCALE" = "1/1" ] \
    && ok "app pinned to exactly 1 instance (min/max=1)" \
    || bad "app scaling is $SCALE — MUST be 1/1, else the task store split-brains and the mesh graph half-draws"

  # The app is --allow-unauthenticated (the browser must load the console), so the task-store
  # endpoints carry their own shared secret. No key ⇒ the agents' task state is world-writable.
  KEY=$(grep -s '^TASK_STORE_KEY=' "$HERE/.env" | cut -d= -f2)
  NOKEY=$(curl -s -o /dev/null -w '%{http_code}' -X PUT "$APPURL/api/taskstore/_probe" \
          -H 'Content-Type: application/json' -d '{"json":"{}"}' 2>/dev/null)
  [ "$NOKEY" = "403" ] \
    && ok "task store REJECTS an unkeyed write (403)" \
    || bad "task store answered $NOKEY without a key — it is UNGATED (set TASK_STORE_KEY and redeploy the app)"
  if have "$KEY"; then
    WITHKEY=$(curl -s -o /dev/null -w '%{http_code}' -X PUT "$APPURL/api/taskstore/_probe" \
              -H "X-Task-Store-Key: $KEY" -H 'Content-Type: application/json' -d '{"json":"{}"}' 2>/dev/null)
    [ "$WITHKEY" = "200" ] && ok "task store ACCEPTS a keyed write (200)" \
                           || bad "task store answered $WITHKEY WITH the key — app and engines disagree on TASK_STORE_KEY"
    curl -s -o /dev/null -X DELETE "$APPURL/api/taskstore/_probe" -H "X-Task-Store-Key: $KEY" 2>/dev/null
  fi

  R=$(curl -s "$APPURL/api/ready" | jq -r '.ready' 2>/dev/null)
  [ "$R" = "true" ] && ok "app deployed and READY" || bad "app deployed but not ready ($APPURL/api/ready)"
else bad "vibeflix-app not deployed (step 5)"; fi
fi

echo
echo "════ RESULT: $PASS passed · $FAIL failed"
# Non-zero on failure so this can GATE a deploy:  ./deploy/verify_deployment.sh 3b || exit 1
[ "$FAIL" -eq 0 ] || exit 1

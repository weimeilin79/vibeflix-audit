#!/usr/bin/env bash
#
# grant_agent_iam.sh — ALL IAM an AGENT_IDENTITY engine needs, in one idempotent pass.
#
# ⚠️ WHY THIS SCRIPT EXISTS / WHEN TO RE-RUN
# An AGENT_IDENTITY engine runs AS `principal://…/reasoningEngines/<ENGINE_ID>` —
# NOT as any service account. The engine id is baked into the principal, so:
#
#   • REDEPLOY (update in place) → same engine id → same principal → grants SURVIVE.
#   • DELETE + recreate          → NEW engine id → NEW principal → EVERY grant below
#                                  is orphaned onto a dead principal and the mesh
#                                  breaks in confusing ways (401/403 with a policy
#                                  that "looks correct" in the console).
#
# So: never delete the engines. If you ever do, re-run collect_agent_identities.py
# and then THIS script. Safe to re-run any time — all bindings are idempotent.
#
#   ./deploy/grant_agent_iam.sh            # apply
#   ./deploy/grant_agent_iam.sh --dry-run  # print, don't apply
#
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"; REGION="${REGION:-us-central1}"
IDENT="$HERE/agent_identities.json"
[ -s "$IDENT" ] || { echo "missing $IDENT — run deploy/collect_agent_identities.py first"; exit 1; }
DRY=""; [ "${1:-}" = "--dry-run" ] && DRY=1

AGENTS="brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator"
run() { [ -n "$DRY" ] && { echo "    + $*"; return 0; }; "$@" >/dev/null 2>&1 \
        && echo "    ✓ ${*: -1}" || echo "    ⚠️ FAILED: $*"; }
M() { jq -r --arg k "vibeflix-$1" '.[$k].principal' "$IDENT"; }

echo "[grant_agent_iam] project=$PROJECT region=$REGION dry=${DRY:-0}"
echo "  principals under management:"
for A in $AGENTS; do echo "    vibeflix-$A → …$(M "$A" | tail -c 25)"; done
echo

# ── 1. PROJECT roles ──────────────────────────────────────────────────────────
# agentDefaultAccess = basic project-wide logging + model-calling perms.
# agentContextEditor = lets the agent read/write ITS OWN sessions/memories/sandboxes.
#   Without it, ADK's VertexAiSessionService create_session() fails and the A2A
#   executor dies in _prepare_session before the agent ever runs.
PROJECT_ROLES="roles/aiplatform.user
roles/aiplatform.agentDefaultAccess
roles/aiplatform.agentContextEditor
roles/logging.logWriter
roles/monitoring.metricWriter
roles/browser
roles/agentregistry.viewer"

echo "── 1/4 project roles"
for A in $AGENTS; do
  P="$(M "$A")"; echo "  vibeflix-$A"
  for R in $PROJECT_ROLES; do
    run gcloud projects add-iam-policy-binding "$PROJECT" --member="$P" --role="$R" --condition=None
  done
done

# ── 2. GOOGLE-API egress (gateway is default-deny on EVERYTHING outbound) ─────
# AGENT_TO_ANYWHERE governs the engine's OWN calls too: the Gemini model call and
# the VertexAiSessionService session/event writes both leave over
# us-central1-aiplatform.mtls.googleapis.com. Un-granted → the agent cannot run.
echo "── 2/4 Google-API egress endpoints"
epid_at() { gcloud alpha agent-registry services describe "$1" --project="$PROJECT" \
  --location="$2" --format='value(registryResource)' 2>/dev/null | xargs -r basename; }

# Do NOT hand-maintain this list. Every `gcp-*` endpoint that is REGISTERED gets granted
# to every agent. A hardcoded list drifts: ours silently omitted agentregistry(+variants),
# pubsub and telemetry-regional, and the engines 403'd on destinations nobody had granted.
# The rule from the docs is simply: "The destination endpoint must be explicitly registered
# as a Service in the Agent Registry" — and then the caller needs iap.egressor on it.
#
# ⚠️ Includes BOTH regional and GLOBAL aiplatform hosts. With GOOGLE_CLOUD_LOCATION=global
# the genai client egresses to https://aiplatform.googleapis.com (global); pinned to a
# region it uses https://REGION-aiplatform.googleapis.com. Grant both so either works.
GCP_ENDPOINTS="$(gcloud alpha agent-registry services list --project="$PROJECT" \
  --location="$REGION" --format='value(displayName,name)' 2>/dev/null \
  | awk -F'\t' '$1 ~ /^GCP /{n=$2; sub(/.*\//,"",n); print n}')"

echo "  registered GCP endpoints to grant: $(echo "$GCP_ENDPOINTS" | wc -l | tr -d ' ')"
for A in $AGENTS; do
  P="$(M "$A")"; echo "  vibeflix-$A"
  for N in $GCP_ENDPOINTS; do
    EP="$(epid_at "$N" "$REGION")"
    [ -z "$EP" ] && continue
    run gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry \
      --endpoint="$EP" --region="$REGION" --project="$PROJECT" \
      --member="$P" --role=roles/iap.egressor
  done
done

# ── 3. A2A egress (agent → agent), scoped to the TARGET's registry ENDPOINT ───
# Agents are registered --endpoint-spec-type=no-spec → ENDPOINT entries, so bind
# with --endpoint (--mcp-server / --agent both 404 here).
echo "── 3/4 A2A egress (caller → target)"
grantA2A() {
  local EP; EP="$(epid_at "vibeflix-$2-agent" "$REGION")"
  [ -z "$EP" ] && { echo "    ⚠️ vibeflix-$2-agent not registered — skipping"; return; }
  run gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry \
    --endpoint="$EP" --region="$REGION" --project="$PROJECT" \
    --member="$(M "$1")" --role=roles/iap.egressor
}
echo "  vendor-clearance → legal (private hand-off)"
grantA2A vendor-clearance legal
echo "  orchestrator → brand-style / vendor-clearance / deal-pricing (fan-out)"
for T in brand-style vendor-clearance deal-pricing; do grantA2A orchestrator "$T"; done

# ── 4. MCP tool egress (per-tool CEL allowlist from deploy/policies.yaml) ─────
echo "── 4/4 MCP per-tool egress → deploy/grant_mcp_egress.sh"
if [ -n "$DRY" ]; then
  PROJECT="$PROJECT" REGION="$REGION" bash "$HERE/grant_mcp_egress.sh" --dry-run
else
  PROJECT="$PROJECT" REGION="$REGION" bash "$HERE/grant_mcp_egress.sh"
fi

echo
echo "[grant_agent_iam] done. IAM can take 1-2 min to propagate; if a call 403s"
echo "  immediately after, wait and retry ONCE before assuming it's misconfigured."

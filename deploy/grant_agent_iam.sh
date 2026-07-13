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
INVOKER_SA="${MCP_INVOKER_SA:-vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com}"
run() { [ -n "$DRY" ] && { echo "    + $*"; return 0; }; "$@" >/dev/null 2>&1 \
        && echo "    ✓ ${*: -1}" || echo "    ⚠️ FAILED: $*"; }
M() { jq -r --arg k "vibeflix-$1" '.[$k].principal' "$IDENT"; }

# ── 0. Endpoints this demo needs that nothing else creates ────────────────────
# The gateway is DEFAULT-DENY on every outbound call — including the call an engine makes
# to MINT its own MCP token. Without gcp-iamcredentials registered + granted,
# IDTokenCredentials.refresh() is itself blocked and every MCP call 401s with no obvious
# cause. Registered here so a fresh project works from the scripts alone.
ensure_endpoint() {  # ensure_endpoint <name> <url>
  gcloud alpha agent-registry services describe "$1" --project="$PROJECT" \
    --location="$REGION" >/dev/null 2>&1 && return 0
  [ -n "$DRY" ] && { echo "    + register $1 → $2"; return 0; }
  gcloud alpha agent-registry services create "$1" \
    --project="$PROJECT" --location="$REGION" --display-name="GCP ${1#gcp-}" \
    --endpoint-spec-type=no-spec \
    --interfaces="[{url=\"$2\",protocolBinding=\"jsonrpc\"}]" >/dev/null 2>&1 \
    && echo "    ✓ registered $1" || echo "    ⚠️ could not register $1"
}
echo "── 0/4 required GCP endpoints"
ensure_endpoint gcp-iamcredentials      https://iamcredentials.googleapis.com
ensure_endpoint gcp-iamcredentials-mtls https://iamcredentials.mtls.googleapis.com
# GOOGLE_CLOUD_LOCATION=global ⇒ genai/session egress to the GLOBAL aiplatform host.
ensure_endpoint gcp-aiplatform-global   https://aiplatform.googleapis.com
ensure_endpoint gcp-aiplatform-mtls-glb https://aiplatform.mtls.googleapis.com
echo

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

# ── 3. A2A egress — EVERY principal on EVERY agent endpoint (all-to-all) ──────
# Agents are registered --endpoint-spec-type=no-spec → ENDPOINT entries, so bind with
# --endpoint (--mcp-server / --agent both 404 here).
#
# ⚠️ ALL-TO-ALL, not just the caller→target pairs you expect (orchestrator→domain,
# vendor→legal). An *agent* endpoint advertising the aiplatform host SHADOWS the
# `GCP aiplatform` Service for every engine's OWN model call — so an engine holding no
# grant on the agent endpoints gets `403 Egress request is not authorized` on its own
# Gemini call and dies in _prepare_session before running a line of agent code. Granting
# only the "real" A2A pairs took the whole fleet down and looked like gateway flakiness.
echo "── 3/4 A2A egress (all principals × all agent endpoints)"
for T in $AGENTS; do
  EP="$(epid_at "vibeflix-$T-agent" "$REGION")"
  [ -z "$EP" ] && { echo "    ⚠️ vibeflix-$T-agent not registered — skipping"; continue; }
  for C in $AGENTS; do
    run gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry \
      --endpoint="$EP" --region="$REGION" --project="$PROJECT" \
      --member="$(M "$C")" --role=roles/iap.egressor
  done
  echo "  ✓ endpoint $T ← all agents"
done

# ── 3b. MCP INVOKER SA — how an agent-identity engine authenticates to Cloud Run ──
# An AGENT_IDENTITY engine has NO service account behind the metadata server, so
# fetch_id_token() cannot work — and the Agent Gateway does NOT inject a credential for
# you (there is no invoker-SA field on agentToAnywhereConfig, on the registry Service, or
# in gcloud). Cloud Run accepts ONLY an audience-bound OIDC ID token (measured: access
# token → 401 "could not be verified"; ID token → 200; none → 403).
# So the engine mints its own by IMPERSONATING this SA (cloud_auth._id_token_via_impersonation),
# which is exactly what the Agent Gateway codelab's --mcp-invoker-sa does: it only injects
# MCP_INVOKER_SA as an env var. deploy_agents_a2a.py sets that env var; these are the grants.
echo "── 3b/4 MCP invoker SA ($INVOKER_SA)"
if ! gcloud iam service-accounts describe "$INVOKER_SA" --project="$PROJECT" >/dev/null 2>&1; then
  run gcloud iam service-accounts create vibeflix-mcp-invoker --project="$PROJECT" \
    --display-name "Vibeflix MCP invoker (agent-identity ID-token source)"
  sleep 10
fi
# the SA must be able to invoke the MCP services …
for S in vibeflix-mcp-licensing vibeflix-mcp-market vibeflix-mcp-brand-style; do
  run gcloud run services add-iam-policy-binding "$S" --region="$REGION" --project="$PROJECT" \
    --member="serviceAccount:$INVOKER_SA" --role=roles/run.invoker
done
# … and each agent principal must be able to impersonate it.
for A in $AGENTS; do
  run gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" --project="$PROJECT" \
    --member="$(M "$A")" --role=roles/iam.serviceAccountTokenCreator --condition=None
done

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

#!/usr/bin/env bash
#
# deploy_agents.sh — push the 5 agents to Vertex AI Agent Runtime (cloud phase 2).
#
# Built for the ADK 2.3 `adk deploy agent_engine` CLI, which:
#   • packages the agent FOLDER + a generated Dockerfile (image-based; the
#     engine serves A2A automatically — no flag)
#   • installs agents/<name>/requirements.txt from INSIDE the folder — each
#     agent has one (incl. vibeflix-common via the repo git URL)
#   • takes env via --env_file and extra engine config (service_account) via
#     --agent_engine_config_file
#   • CREATES a new engine unless --agent_engine_id is passed → we look up the
#     existing engine by display name so re-runs UPDATE instead of duplicating
#
# After the deploys it enables AGENT IDENTITY on every engine
# (deploy/enable_agent_identity.py — v1beta1 `identity_type` config update) and
# writes the principals to deploy/agent_identities.json.
#
# Prereqs: terraform -chdir=deploy/terraform/agents apply (SAs + IAM);
#          MCP endpoints exported (terraform -chdir=deploy/terraform/mcp output mcp_urls).
# Config from deploy/.env; usage:
#   ./deploy/deploy_agents.sh [agent_name]
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }

PROJECT="${PROJECT:?set PROJECT in deploy/.env}"
REGION="${REGION:-us-central1}"
AGENTS_SA="vibeflix-agents@$PROJECT.iam.gserviceaccount.com"
ADK="$ROOT/.venv/bin/adk"; PY="$ROOT/.venv/bin/python"
ONLY="${1:-}"
export PROJECT REGION

MCP_LICENSING_URL="${MCP_LICENSING_URL:?export the MCP endpoints (terraform -chdir=deploy/terraform/mcp output mcp_urls)}"
MCP_MARKET_URL="${MCP_MARKET_URL:?}"
MCP_BRAND_STYLE_URL="${MCP_BRAND_STYLE_URL:?}"

# Engine config (beyond env): the runtime service account. (Agent identity is
# applied post-deploy — it's a v1beta1 update, see enable_agent_identity.py.)
CFG="$(mktemp -d)/engine_config.json"
printf '{"service_account": "%s"}\n' "$AGENTS_SA" > "$CFG"

# Env shipped to every engine. GOOGLE_CLOUD_PROJECT/LOCATION are deliberately
# NOT here (the CLI intercepts them; Gemini's `global` location comes from the
# agent folder's own .env, which ships with the source).
COMMON_ENV="RUN_LOCAL=false
GOOGLE_GENAI_USE_VERTEXAI=true
PUBSUB_TOPIC=${PUBSUB_TOPIC:-vibeflix-mesh-events}"

# Each agent folder needs a .env — it SHIPS with the engine source and is what
# the agent reads for Gemini config (GOOGLE_CLOUD_LOCATION=global) at import.
# The files are GITIGNORED, so a fresh clone won't have them: create if missing.
ensure_agent_env() {
  local F="$ROOT/agents/$1/.env"
  [ -f "$F" ] && return 0
  echo "   creating $F (gitignored — absent on fresh clones)"
  cat > "$F" <<ENVEOF
GOOGLE_CLOUD_PROJECT=$PROJECT
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=true
ENVEOF
}

engine_id_for() {  # display name → existing engine resource ID ('' if none)
  "$PY" - "$1" <<'PYEOF'
import os, sys, vertexai
c = vertexai.Client(project=os.environ["PROJECT"], location=os.environ["REGION"])
for e in c.agent_engines.list():
    if e.api_resource.display_name == sys.argv[1]:
        print(e.api_resource.name.rsplit("/", 1)[-1]); break
PYEOF
}

deploy_one() {  # $1 agent dir name, $2 extra env (newline-separated KEY=VALUE)
  local NAME="$1" EXTRA="${2:-}" DISPLAY ENVF EID
  DISPLAY="vibeflix-${NAME//_/-}"
  ensure_agent_env "$NAME"
  ENVF="$(mktemp)"
  printf '%s\n%s\n' "$COMMON_ENV" "$EXTRA" > "$ENVF"
  EID="$(engine_id_for "$DISPLAY")"
  echo "── $NAME → $DISPLAY $([ -n "$EID" ] && echo "(update $EID)" || echo "(create)")"
  "$ADK" deploy agent_engine "$ROOT/agents/$NAME" \
    --project "$PROJECT" --region "$REGION" \
    --display_name "$DISPLAY" \
    --env_file "$ENVF" \
    --agent_engine_config_file "$CFG" \
    ${EID:+--agent_engine_id "$EID"} \
    | tee "$HERE/.deploy_$NAME.log"
}

run_for() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

run_for brand_style  && deploy_one brand_style  "MCP_BRAND_STYLE_URL=$MCP_BRAND_STYLE_URL"
run_for deal_pricing && deploy_one deal_pricing "MCP_LICENSING_URL=$MCP_LICENSING_URL"
run_for ui_renderer  && deploy_one ui_renderer  ""
run_for legal        && deploy_one legal "MCP_LICENSING_URL=$MCP_LICENSING_URL
RAG_CORPUS=${RAG_CORPUS:?legal needs RAG_CORPUS (deploy/setup_legal_rag.py) — no doc volumes on Agent Runtime}
RAG_LOCATION=${RAG_LOCATION:-us-central1}"
if run_for vendor_clearance; then
  if [ -n "${LEGAL_A2A_URL:-}" ]; then
    deploy_one vendor_clearance "MCP_LICENSING_URL=$MCP_LICENSING_URL
MCP_MARKET_URL=$MCP_MARKET_URL
LEGAL_A2A_URL=$LEGAL_A2A_URL"
  else
    echo "── skipping vendor_clearance: export LEGAL_A2A_URL=<legal engine's A2A URL> and re-run"
    echo "   ./deploy/deploy_agents.sh vendor_clearance"
  fi
fi

echo
echo "[deploy_agents] enabling AGENT IDENTITY (v1beta1 identity_type update)…"
"$PY" "$HERE/enable_agent_identity.py" \
  || echo "  ⚠️ identity update failed — re-run deploy/enable_agent_identity.py (preview surface)"

echo
echo "[deploy_agents] engines:"
"$PY" - <<'PYEOF'
import os, vertexai
c = vertexai.Client(project=os.environ["PROJECT"], location=os.environ["REGION"])
for e in c.agent_engines.list():
    r = e.api_resource
    if r.display_name.startswith("vibeflix-"):
        print(f"  {r.display_name:28s} {r.name}")
PYEOF
echo "A2A base per engine: https://$REGION-aiplatform.googleapis.com/v1/<resource name>"
echo "If vendor_clearance was skipped: export LEGAL_A2A_URL from legal's entry above, re-run for it."

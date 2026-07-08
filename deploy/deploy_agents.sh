#!/usr/bin/env bash
#
# deploy_agents.sh — push the 5 agents to Vertex AI Agent Runtime (cloud phase 2).
#
# Agent Runtime is SOURCE-based (no images): each agents/<name>/ package is
# deployed as its own reasoning engine, exposed over A2A so the orchestrator
# keeps speaking the same protocol it does locally. IAM lives in
# deploy/terraform/agents (apply that first); this script only pushes code + env.
#
# Prereqs:
#   terraform -chdir=deploy/terraform/agents apply       # SAs + IAM
#   deploy/terraform/mcp applied (MCP endpoints exist)   # or gateway URLs ready
#   .venv with google-adk[a2a] (repo dev venv works)
#
# Config from deploy/.env (PROJECT, REGION, STAGING_BUCKET); per-run override:
#   PROJECT=… REGION=us-central1 ./deploy/deploy_agents.sh [agent_name]
#
# ⚠️ Agent Runtime location is REGIONAL (us-central1) — Gemini keeps
#    GOOGLE_CLOUD_LOCATION=global INSIDE the agents; the two coexist.
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }

PROJECT="${PROJECT:?set PROJECT in deploy/.env}"
REGION="${REGION:-us-central1}"
STAGING_BUCKET="${STAGING_BUCKET:-gs://$PROJECT-vibeflix-agent-staging}"
AGENTS_SA="vibeflix-agents@$PROJECT.iam.gserviceaccount.com"
ADK="$ROOT/.venv/bin/adk"
ONLY="${1:-}"

# The MCP env contract — from the gateway once phase 2D is live, else the
# terraform/mcp outputs. Export MCP_*_URL before running to override.
MCP_LICENSING_URL="${MCP_LICENSING_URL:?export the MCP endpoints (terraform -chdir=deploy/terraform/mcp output mcp_urls)}"
MCP_MARKET_URL="${MCP_MARKET_URL:?}"
MCP_BRAND_STYLE_URL="${MCP_BRAND_STYLE_URL:?}"

gsutil ls -b "$STAGING_BUCKET" >/dev/null 2>&1 || gsutil mb -p "$PROJECT" -l "$REGION" "$STAGING_BUCKET"

# agent dir | extra env (comma-sep KEY=VALUE)
COMMON="RUN_LOCAL=false,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,PUBSUB_TOPIC=${PUBSUB_TOPIC:-vibeflix-mesh-events}"
SPECS=(
  "brand_style|MCP_BRAND_STYLE_URL=$MCP_BRAND_STYLE_URL"
  "deal_pricing|MCP_LICENSING_URL=$MCP_LICENSING_URL"
  "ui_renderer|"
  "legal|MCP_LICENSING_URL=$MCP_LICENSING_URL,RAG_CORPUS=${RAG_CORPUS:?legal needs RAG_CORPUS (deploy/setup_legal_rag.py) — no doc volumes on Agent Runtime},RAG_LOCATION=${RAG_LOCATION:-us-central1}"
  # vendor_clearance LAST: needs legal's A2A URL. Deploy legal first, then set
  # LEGAL_A2A_URL from deploy/agents_metadata.json and re-run for vendor_clearance.
  "vendor_clearance|MCP_LICENSING_URL=$MCP_LICENSING_URL,MCP_MARKET_URL=$MCP_MARKET_URL,LEGAL_A2A_URL=${LEGAL_A2A_URL:-}"
)

for SPEC in "${SPECS[@]}"; do
  IFS='|' read -r NAME EXTRA <<<"$SPEC"
  [ -n "$ONLY" ] && [ "$NAME" != "$ONLY" ] && continue
  if [ "$NAME" = "vendor_clearance" ] && [ -z "${LEGAL_A2A_URL:-}" ]; then
    echo "── skipping vendor_clearance (set LEGAL_A2A_URL to legal's runtime A2A URL first)"; continue
  fi
  ENVS="$COMMON"; [ -n "$EXTRA" ] && ENVS="$COMMON,$EXTRA"
  echo "── deploying $NAME to Agent Runtime ($REGION)…"
  "$ADK" deploy agent_engine "$ROOT/agents/$NAME" \
    --project "$PROJECT" --region "$REGION" \
    --staging_bucket "$STAGING_BUCKET" \
    --service_account "$AGENTS_SA" \
    --display_name "vibeflix-$NAME" \
    --a2a \
    --env_vars "$ENVS" \
    | tee "$HERE/.deploy_$NAME.log"
done

echo
echo "[deploy_agents] engines:"
gcloud ai reasoning-engines list --project "$PROJECT" --region "$REGION" \
  --format 'table(displayName,name)' 2>/dev/null \
  || echo "  (list via: python -c 'import vertexai; …agent_engines.list()' if gcloud lacks the surface)"
echo "Record each agent's A2A card URL (…/reasoningEngines/<ID>/.well-known/agent-card.json)"
echo "then export LEGAL_A2A_URL and re-run for vendor_clearance if it was skipped."

#!/usr/bin/env bash
#
# setup_gateway.sh — Agent Registry + Agent Gateway + access policies (phase 2C/2D).
#
# ⚠️ PREVIEW SURFACES. Agent Registry / Agent Gateway are Gemini Enterprise
# Agent Platform preview features — command shapes may differ by gcloud release.
# Every step prints the intent first; if a command 404s, check
# `gcloud alpha gemini-enterprise --help` (or the Agent Platform console) for the
# current spelling and re-run. The REGISTRY/GATEWAY sections are intentionally
# thin wrappers so drift is easy to patch.
#
# What it sets up:
#   1. REGISTRY  — register the 3 MCP servers + the 5 agents (A2A cards)
#   2. GATEWAY   — one governed MCP front door proxying the 3 Cloud Run MCPs
#   3. POLICIES  — deny-by-default per-agent tool allowlists (policies.yaml)
#   4. REWIRE    — the gateway SA becomes the ONLY run.invoker on the MCPs
#                  (re-apply terraform/mcp with invoker_members=[gateway SA])
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"
REGION="${REGION:-us-central1}"

echo "[gateway] project=$PROJECT region=$REGION"
echo
echo "── 1/4 Agent Registry: register MCP servers + agents"
echo "   MCP endpoints:   terraform -chdir=$HERE/terraform/mcp output mcp_urls"
echo "   Agent A2A cards: from deploy_agents.sh output"
gcloud alpha gemini-enterprise agent-registry --help >/dev/null 2>&1 || {
  echo "   ⚠️ this gcloud has no agent-registry surface — register via the"
  echo "   Agent Platform console (Gemini Enterprise → Agent Registry) or the"
  echo "   REST API, then re-run this script for the policy step."; }
# Per-asset registration (adjust to the live surface):
#   gcloud alpha gemini-enterprise agent-registry mcp-servers register vibeflix-mcp-licensing \
#     --uri <MCP_LICENSING_URL> --project $PROJECT --location $REGION
#   gcloud alpha gemini-enterprise agent-registry agents register vibeflix-brand-style \
#     --agent-card-url <…/.well-known/agent-card.json> --project $PROJECT --location $REGION

echo
echo "── 2/4 Agent Gateway"
#   gcloud alpha gemini-enterprise gateways create vibeflix-gateway \
#     --project $PROJECT --location $REGION \
#     --mcp-servers vibeflix-mcp-licensing,vibeflix-mcp-market,vibeflix-mcp-brand-style
echo "   create gateway 'vibeflix-gateway' attached to the 3 registered MCP servers,"
echo "   then note its endpoint + service agent/SA."

echo
echo "── 3/4 policies (deny-by-default tool allowlists) — source: deploy/policies.yaml"
cat "$HERE/policies.yaml"
echo "   apply each binding via the gateway policies surface / console."

echo
echo "── 4/4 rewire MCP invokers to the gateway SA ONLY:"
echo "   terraform -chdir=$HERE/terraform/mcp apply \\"
echo "     -var project=$PROJECT -var region=$REGION -var deployer=user:\$(gcloud config get-value account) \\"
echo "     -var 'invoker_members=[\"serviceAccount:<GATEWAY_SA>\"]'"
echo "   (drops the per-user grant; every MCP call now flows through the gateway)"

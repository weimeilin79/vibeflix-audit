#!/usr/bin/env bash
# Verify workshop Step 7 — Agent Gateway + Registry + per-agent identities.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 7: Agent Identity + Gateway + Registry ──"
gcloud alpha network-services agent-gateways describe vibeflix-gateway \
  --location="$REGION" --project="$PROJECT" >/dev/null 2>&1 \
  && ok "Agent Gateway 'vibeflix-gateway' exists" \
  || bad "Agent Gateway 'vibeflix-gateway' not found — run ./deploy/setup_gateway.sh"

N=$(gcloud alpha agent-registry services list --location="$REGION" --project="$PROJECT" \
    --format='value(name)' 2>/dev/null | grep -c . || echo 0)
[ "${N:-0}" -ge 9 ] && ok "$N services in Agent Registry (6 agents + 3 MCP)" \
  || bad "only ${N:-0} registry services (expected ≥ 9) — run ./deploy/setup_gateway.sh registry"

ALL=1
for a in brand-style deal-pricing legal vendor-clearance orchestrator ui-renderer; do
  [ -n "$(jq -r --arg k "vibeflix-$a" '.[$k].principal // empty' "$ROOT/deploy/agent_identities.json" 2>/dev/null)" ] || ALL=0
done
[ "$ALL" = 1 ] && ok "all 6 agents run under their own agent identity (principal://)" \
  || bad "some agents are missing an agent identity"
finish "Step 7"

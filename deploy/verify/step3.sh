#!/usr/bin/env bash
# Verify workshop Step 3 — the deal_pricing agent is deployed with an agent identity.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 3: deal_pricing agent ──"
check_agent vibeflix-deal-pricing "deal_pricing"
finish "Step 3"

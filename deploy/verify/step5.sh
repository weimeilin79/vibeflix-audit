#!/usr/bin/env bash
# Verify workshop Step 5 — the orchestrator deployed with an agent identity.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 5: orchestrator ──"
check_agent vibeflix-orchestrator "orchestrator"
finish "Step 5"

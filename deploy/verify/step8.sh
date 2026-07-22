#!/usr/bin/env bash
# Verify workshop Step 8 — observability: telemetry on, trace propagation, shared task store.
set -uo pipefail
DEPLOY="$(cd "$(dirname "$0")/.." && pwd)"
echo "── Verify Step 8: observability (telemetry + trace propagation + task store) ──"
exec "$DEPLOY/verify_deployment.sh" 3b

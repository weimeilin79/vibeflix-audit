#!/usr/bin/env bash
# Verify workshop Step 4 — vendor_clearance + legal deployed with agent identities.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 4: vendor_clearance + legal ──"
check_agent vibeflix-legal "legal"
check_agent vibeflix-vendor-clearance "vendor_clearance"
finish "Step 4"

#!/usr/bin/env bash
# Verify workshop Step 2 — the brand_style agent is deployed with an agent identity.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 2: brand_style agent ──"
check_agent vibeflix-brand-style "brand_style"
finish "Step 2"

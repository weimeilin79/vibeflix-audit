#!/usr/bin/env bash
# Layer 2: orchestrator engine → brand_style, vendor_clearance, deal_pricing.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; D="$DIR/diag.sh"
export PROJECT="${PROJECT:-pokedemo-test}" REGION="${REGION:-us-central1}"
ORCH=$(jq -r '."vibeflix-orchestrator".principal' "$DIR/../../deploy/agent_identities.json")
echo "═══ 2: grant orchestrator → 3 domain agents ═══"
for T in vibeflix-brand-style vibeflix-vendor-clearance vibeflix-deal-pricing; do "$D" grant_a2a "$ORCH" "$T"; done
echo "═══ 2b: verify each ═══"
for T in vibeflix-brand-style vibeflix-vendor-clearance vibeflix-deal-pricing; do echo "-- $T"; "$D" check_grant "$T"; done
echo "═══ 2c: probe orchestrator ENGINE with a full audit ═══"
"$D" probe vibeflix-orchestrator '{"image_uri":"gs://vibeflix-request-image/0aa7dd74-vendor_request_refine.png","target_market":"Asia-Pacific","volume":1000,"character":"grogu","product_category":"Vinyl Figures","vendor":"VND-1001","medium":"vinyl figures","net_unit_price":15,"agreed_royalty_rate":0.18,"agreed_advance":88000,"agreed_mg":1500000}'
echo "═══ 2d: orchestrator errors ═══"
"$D" errs vibeflix-orchestrator

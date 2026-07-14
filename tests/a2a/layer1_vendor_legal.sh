#!/usr/bin/env bash
# Layer 1: vendor_clearance → legal. Grant (resource-scoped --agent) + verify + probe.
set -uo pipefail
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/diag.sh"
if [ -z "${PROJECT:-}" ]; then
  echo "✗ PROJECT is not set. Refusing to guess." >&2
  echo "  This used to default to a hardcoded project — so forgetting to export PROJECT" >&2
  echo "  silently deployed to (or read from) SOMEONE ELSE'S project." >&2
  echo "  Run:  export PROJECT=<your-project> REGION=<your-region>" >&2
  exit 1
fi
export PROJECT="${PROJECT}" REGION="${REGION:-us-central1}"
VC_PRIN=$(jq -r '."vibeflix-vendor-clearance".principal' "$(dirname "${BASH_SOURCE[0]}")/../../deploy/agent_identities.json")
echo "═══ 1: grant vendor_clearance → legal (--agent) ═══"
"$D" grant_a2a "$VC_PRIN" vibeflix-legal
echo "═══ 1a: verify grant on legal agent resource ═══"
"$D" check_grant vibeflix-legal
echo "═══ 1b: probe vendor_clearance to force the legal hand-off ═══"
"$D" probe vibeflix-vendor-clearance "Onboard vendor VND-1005 for character grogu in North America to a NEW product category 'Vinyl Figures'. add_category_approved: yes. Run legal clearance and execute the contract."
echo "═══ 1c: vendor_clearance recent errors (403/egress?) ═══"
"$D" errs vibeflix-vendor-clearance

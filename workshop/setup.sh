#!/usr/bin/env bash
# workshop/setup.sh — ONE command for the workshop's foundations + all 3 MCP servers.
#
# Runs the same steps as deploy/docs/instruction-sre.md (Step 0-2), in order:
#   preflight → enable APIs → foundations (Artifact Registry + telemetry topic)
#   → buckets → Firestore (+ seed) → Pub/Sub subscription → 3 MCP servers on Cloud Run.
#
# Run ./init.sh FIRST — it owns the venv, the Python dependencies, terraform, and deploy/.env.
# Idempotent — safe to re-run. Reads deploy/.env for PROJECT / REGION.
# On a FRESH workshop project, leave REQUEST_IMAGE_BUCKET / APPROVED_ASSETS_BUCKET UNSET in
# deploy/.env so the project-prefixed defaults are used everywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
[ -f deploy/.env ] && { set -a; . deploy/.env; set +a; }
# init.sh installs terraform to ~/bin (Cloud Shell no longer ships it, and ~/bin survives
# a session restart where `apt install` doesn't). A script can't change its parent's PATH, so
# pick it up here — otherwise the tab you run this in wouldn't see a terraform you just
# installed. Prepended so it beats Cloud Shell's exit-0 placeholder at /usr/bin/terraform.
# Exported, so the preflight + terraform steps below inherit it.
[ -x "$HOME/bin/terraform" ] && export PATH="$HOME/bin:$PATH"
: "${PROJECT:?set PROJECT in deploy/.env (copy deploy/.env.example first)}"
REGION="${REGION:-us-central1}"
echo "▶ Workshop setup — project=$PROJECT region=$REGION"

echo "▶ 1/9 preflight (tools + auth)"
./deploy/preflight.sh || { echo "Fix the ✗ items above, then re-run."; exit 1; }

echo "▶ 2/9 checking the venv from ./init.sh"
# init.sh OWNS the venv, the dependencies, and terraform — this script only asserts they're
# there. Re-installing here would be a second, drifting copy of the install (it used to be one:
# it omitted the --pre that the pre-GA ADK needs). Same rule as the topic at 7/9: one owner.
[ -x .venv/bin/python ] || {
  echo "ERROR: no .venv — run ./init.sh first (it creates the venv and installs everything)." >&2
  exit 1
}
.venv/bin/python -c 'import vibeflix_common' 2>/dev/null || {
  echo "ERROR: .venv exists but is missing dependencies — re-run ./init.sh." >&2
  exit 1
}
# shellcheck disable=SC1091
source .venv/bin/activate
echo "  ✓ .venv ready ($(.venv/bin/python -V 2>&1))"

echo "▶ 3/9 enable APIs"
# A 429 here is a RATE limit, not a failure. serviceusage caps "mutate requests per minute" at
# 120 — and it charges them to your ADC QUOTA project, which is shared by every project you
# drive from this shell, so re-runs, parallel work and this script's own preflight all compete
# for one budget. Waiting is the entire fix. (gcloud appends "may be due to network
# connectivity issues" to this error, which sends you to check DNS for a quota problem.)
enable_apis() {
  local n=1
  until gcloud services enable --project="$PROJECT" "$@"; do
    if [ "$n" -ge 4 ]; then
      echo "  ✗ could not enable APIs after $n attempts. If this is the 429 'Mutate requests"
      echo "    per minute' quota, simply wait 60s and re-run — nothing is broken." >&2
      return 1
    fi
    echo "  ! enable failed (attempt $n/4) — waiting $((n * 30))s before retrying"
    sleep $((n * 30)); n=$((n + 1))
  done
}
enable_apis \
  firestore.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  aiplatform.googleapis.com agentregistry.googleapis.com iamcredentials.googleapis.com \
  vectorsearch.googleapis.com \
  cloudresourcemanager.googleapis.com observability.googleapis.com cloudtrace.googleapis.com \
  telemetry.googleapis.com monitoring.googleapis.com iap.googleapis.com \
  networkservices.googleapis.com networksecurity.googleapis.com \
  apphub.googleapis.com apptopology.googleapis.com

echo "▶ 4/9 foundations: Artifact Registry repo + telemetry topic (Terraform)"
terraform -chdir=deploy/terraform/foundations init -input=false >/dev/null
terraform -chdir=deploy/terraform/foundations apply -auto-approve \
  -var project="$PROJECT" -var region="$REGION" \
  -var pubsub_topic="${PUBSUB_TOPIC:-vibeflix-mesh-events}"

echo "▶ 5/9 GCS buckets (+ default mockup image)"
./deploy/setup_buckets.sh

echo "▶ 6/9 Firestore database + seed the registries"
./deploy/setup_firestore.sh

echo "▶ 7/9 Pub/Sub bridge subscription"
./deploy/setup_pubsub.sh

echo "▶ 8/9 the 3 MCP servers → Cloud Run"
./deploy/deploy_mcp_cloudrun.sh

echo "▶ 9/9 register the 3 MCP servers to the Agent Registry (discoverability + gateway destinations)"
# Registers the MCP servers only; the agents register later (Step 7), so this skips them.
./deploy/setup_gateway.sh registry

echo
echo "✅ Foundations + 3 MCP servers are up, and the MCP servers are in the Agent Registry."

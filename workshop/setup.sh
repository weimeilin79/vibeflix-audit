#!/usr/bin/env bash
# workshop/setup.sh — ONE command for the workshop's foundations + all 3 MCP servers.
#
# Runs the same steps as deploy/docs/instruction-sre.md (Step 0-2), in order:
#   preflight → enable APIs → foundations (Artifact Registry + telemetry topic)
#   → buckets → Firestore (+ seed) → Pub/Sub subscription → 3 MCP servers on Cloud Run.
#
# Idempotent — safe to re-run. Reads deploy/.env for PROJECT / REGION.
# On a FRESH workshop project, leave REQUEST_IMAGE_BUCKET / APPROVED_ASSETS_BUCKET UNSET in
# deploy/.env so the project-prefixed defaults are used everywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
[ -f deploy/.env ] && { set -a; . deploy/.env; set +a; }
: "${PROJECT:?set PROJECT in deploy/.env (copy deploy/.env.example first)}"
REGION="${REGION:-us-central1}"
echo "▶ Workshop setup — project=$PROJECT region=$REGION"

echo "▶ 1/9 preflight (tools + auth)"
./deploy/preflight.sh || { echo "Fix the ✗ items above, then re-run."; exit 1; }

echo "▶ 2/9 Python venv + dependencies (used by the seeding + agent-deploy scripts)"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r agents/requirements.txt -r deploy/requirements-legal-rag.txt
pip install -q -e packages/vibeflix-common

echo "▶ 3/9 enable APIs"
gcloud services enable --project="$PROJECT" \
  firestore.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  aiplatform.googleapis.com agentregistry.googleapis.com iamcredentials.googleapis.com \
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
echo "   Next: workshop/02-brand-style.md — build & deploy your first agent (it grants its own IAM)."

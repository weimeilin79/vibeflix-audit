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
# ensure_apis (deploy/lib_setup.sh) checks what is already on before mutating anything — see
# there for why re-enabling an enabled API is what exhausts the serviceusage quota.
. "$ROOT/deploy/lib_setup.sh"
ensure_apis \
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

# Adopt resources that already exist but are NOT in the state file.
#
# Terraform's state is the only record that it created something. Lose the state and `apply`
# tries to create the resource again, which fails with ALREADY_EXISTS on a resource that is
# perfectly healthy — and the fix looks like "delete your registry", which would take the
# images in it with it.
#
# State goes missing more easily than it sounds: a Cloud Build run keeps it in the build
# workspace and only persists it when the build ENDS, so a cancelled or timed-out install
# leaves the resources created and the state gone. Importing first makes the step idempotent
# with or without state.
tf_adopt() {   # tf_adopt <terraform address> <import id>
  terraform -chdir=deploy/terraform/foundations state show "$1" >/dev/null 2>&1 && return 0
  terraform -chdir=deploy/terraform/foundations import \
    -var project="$PROJECT" -var region="$REGION" \
    -var pubsub_topic="${PUBSUB_TOPIC:-vibeflix-mesh-events}" "$1" "$2" >/dev/null 2>&1 \
    && echo "  ✓ adopted pre-existing $1 into terraform state"
  return 0   # not existing in the cloud either is the normal first-run case
}
tf_adopt google_artifact_registry_repository.vibeflix \
  "projects/$PROJECT/locations/$REGION/repositories/${AR_REPO_ID:-vibeflix}"
tf_adopt google_pubsub_topic.telemetry \
  "projects/$PROJECT/topics/${PUBSUB_TOPIC:-vibeflix-mesh-events}"
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

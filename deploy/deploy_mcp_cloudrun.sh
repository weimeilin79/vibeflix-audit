#!/usr/bin/env bash
#
# deploy_mcp_cloudrun.sh — build the 3 MCP-server images and apply the Terraform
# that owns the MCP tier (cloud phase 1).
#
#   images:   gcloud builds submit  (deploy/cloudbuild-mcp.yaml, one per group)
#   infra:    deploy/terraform/mcp  (Cloud Run services, runtime SAs, IAM)
#
# The IAM story (see deploy/terraform/mcp/main.tf for the full rationale):
#   vibeflix-mcp-licensing  → Firestore READ/WRITE + topic-scoped Pub/Sub publish
#   vibeflix-mcp-readonly   → Firestore READ-ONLY  + topic-scoped Pub/Sub publish
#   services are --no-allow-unauthenticated; callers need roles/run.invoker.
#   Pass the agents' runtime SA later via: TF_VAR_invoker_members='["serviceAccount:…"]'
#
# Config from deploy/.env (PROJECT, REGION). Usage:
#   ./deploy/deploy_mcp_cloudrun.sh            # build all 3 + terraform apply
#   ./deploy/deploy_mcp_cloudrun.sh --no-build # terraform apply only
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }

PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:?set PROJECT in deploy/.env}}"
REGION="${REGION:-us-central1}"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib_setup.sh"
DEPLOYER="$(iam_self_member)"   # user: or serviceAccount:, whichever this caller is
AR="$REGION-docker.pkg.dev/$PROJECT/vibeflix"

echo "[mcp-deploy] project=$PROJECT region=$REGION deployer=$DEPLOYER"
ensure_apis run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

# The builds push to $REGION-docker.pkg.dev/$PROJECT/vibeflix. That Artifact Registry repo is
# owned by terraform/foundations now (apply it first) — assert it exists so a fresh project
# fails HERE with a clear message instead of an opaque `Repository "vibeflix" not found`.
gcloud artifacts repositories describe vibeflix --location="$REGION" --project="$PROJECT" \
  >/dev/null 2>&1 || {
    echo "ERROR: Artifact Registry repo 'vibeflix' not found in $REGION." >&2
    echo "       Apply deploy/terraform/foundations first (it owns the repo)." >&2
    exit 1
  }

if [ "${1:-}" != "--no-build" ]; then
# A build submitted from INSIDE a build has no default service account to fall back on. Projects
# created after Google's 2024 change get no <number>@cloudbuild.gserviceaccount.com, and the
# Compute Engine default SA only exists once compute.googleapis.com is enabled — so on a fresh
# project a nested `gcloud builds submit` with no --service-account is rejected outright.
# cloudbuild-mesh.yaml exports the account the outer build runs as; pass it down when present.
# Empty (a normal laptop/Cloud Shell run) → the flag is omitted and gcloud picks the default.
# A plain string, not an array: `"${arr[@]}"` on an EMPTY array is an "unbound variable" error
# under `set -u` on bash 3.2, which is still what macOS ships — and these scripts are run by
# hand there. The value never contains spaces, so unquoted expansion is safe and portable.
BUILD_SA_FLAG=""
[ -n "${CLOUDBUILD_SA:-}" ] && BUILD_SA_FLAG="--service-account=projects/$PROJECT/serviceAccounts/$CLOUDBUILD_SA"

  echo "[mcp-deploy] building images (parallel Cloud Build)…"
  for G in mcp_licensing mcp_market mcp_brand_style; do
    gcloud builds submit "$ROOT" --config "$HERE/cloudbuild-mcp.yaml" \
      $BUILD_SA_FLAG \
      --substitutions "_GROUP=$G,_IMAGE=$AR/${G//_/-}" --async --format 'value(id)'
  done
  echo "[mcp-deploy] waiting for builds…"
  until [ "$(gcloud builds list --project "$PROJECT" --ongoing --format 'value(id)' | wc -l | tr -d ' ')" = "0" ]; do
    sleep 15
  done
  FAILED="$(gcloud builds list --project "$PROJECT" --limit 3 --filter 'status!=SUCCESS' --format 'value(id)')"
  [ -z "$FAILED" ] || { echo "ERROR: build(s) failed: $FAILED" >&2; exit 1; }
fi

echo "[mcp-deploy] terraform apply…"
terraform -chdir="$HERE/terraform/mcp" init -upgrade -input=false >/dev/null
terraform -chdir="$HERE/terraform/mcp" apply -input=false -auto-approve \
  -var "project=$PROJECT" -var "region=$REGION" -var "deployer=$DEPLOYER"

echo "[mcp-deploy] done. MCP endpoints:"
terraform -chdir="$HERE/terraform/mcp" output mcp_urls

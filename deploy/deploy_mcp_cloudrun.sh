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
DEPLOYER="user:$(gcloud config get-value account 2>/dev/null)"
AR="$REGION-docker.pkg.dev/$PROJECT/vibeflix"

echo "[mcp-deploy] project=$PROJECT region=$REGION deployer=$DEPLOYER"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com --project "$PROJECT" >/dev/null

# The builds push to $REGION-docker.pkg.dev/$PROJECT/vibeflix — but nothing created that
# Artifact Registry repo, so a FRESH project failed the first build with
# `name unknown: Repository "vibeflix" not found`. Create it here (idempotent).
gcloud artifacts repositories create vibeflix --repository-format=docker \
  --location="$REGION" --project="$PROJECT" --description="Vibeflix container images" \
  >/dev/null 2>&1 || true

if [ "${1:-}" != "--no-build" ]; then
  echo "[mcp-deploy] building images (parallel Cloud Build)…"
  for G in mcp_licensing mcp_market mcp_brand_style; do
    gcloud builds submit "$ROOT" --config "$HERE/cloudbuild-mcp.yaml" \
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

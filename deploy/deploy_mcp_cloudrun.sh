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
  IDS=""
  for G in mcp_licensing mcp_market mcp_brand_style; do
    # tail -n1: `--format 'value(id)'` puts the id on stdout and progress on stderr, but a
    # deprecation notice or warning landing on stdout would make ID multi-line and every later
    # `describe "$ID"` fail. Take the last line and strip whitespace.
    ID="$(gcloud builds submit "$ROOT" --config "$HERE/cloudbuild-mcp.yaml" \
      $BUILD_SA_FLAG \
      --substitutions "_GROUP=$G,_IMAGE=$AR/${G//_/-}" --async --format 'value(id)' \
      | tail -n1 | tr -d '[:space:]')"
    [ -n "$ID" ] || { echo "ERROR: $G build was submitted but returned no build id." >&2; exit 1; }
    echo "  $G → $ID"
    IDS="$IDS $ID"
  done

  # Wait on OUR THREE BUILD IDS — never on "is anything still building in this project".
  #
  # The previous version polled `gcloud builds list --ongoing` until the count hit zero. That
  # works on a laptop and DEADLOCKS inside Cloud Build: the parent build running this script is
  # itself ongoing, so the count can never reach zero, and the parent cannot exit until this
  # loop does. The images finish in minutes; the install then hangs until the 3h build timeout
  # with nothing in the log but "waiting for builds…".
  #
  # It was also wrong in a quieter way — a colleague's unrelated build in the same project would
  # have held it up, and the failure check ("last 3 builds, any not SUCCESS") could report THEIR
  # failure as ours.
  echo "[mcp-deploy] waiting for builds…"
  RC=0
  for ID in $IDS; do
    MISSES=0
    while :; do
      ST="$(gcloud builds describe "$ID" --project "$PROJECT" --format='value(status)' 2>/dev/null)"
      case "$ST" in
        SUCCESS) echo "  ✓ $ID SUCCESS"; break ;;
        FAILURE|TIMEOUT|CANCELLED|EXPIRED|INTERNAL_ERROR)
          # Name the status: TIMEOUT (too slow / machine too small) and FAILURE (the image
          # genuinely does not build) need completely different fixes.
          echo "  ✗ $ID $ST" >&2
          echo "    https://console.cloud.google.com/cloud-build/builds/$ID?project=$PROJECT" >&2
          RC=1; break ;;
        "") # Unreadable status: a transient API blip is fine, but never wait forever on it —
            # that would trade one unterminable loop for another.
            MISSES=$((MISSES + 1))
            if [ "$MISSES" -ge 8 ]; then
              echo "  ✗ cannot read status of $ID after $MISSES tries (2 min) — giving up." >&2
              RC=1; break
            fi
            echo "  ! could not read status for $ID ($MISSES/8) — retrying" >&2; sleep 15 ;;
        *) MISSES=0; sleep 15 ;;
      esac
    done
  done
  [ "$RC" = 0 ] || { echo "ERROR: MCP image build(s) did not succeed — see the link(s) above" >&2; exit 1; }
fi

echo "[mcp-deploy] terraform apply…"
terraform -chdir="$HERE/terraform/mcp" init -upgrade -input=false >/dev/null
terraform -chdir="$HERE/terraform/mcp" apply -input=false -auto-approve \
  -var "project=$PROJECT" -var "region=$REGION" -var "deployer=$DEPLOYER"

echo "[mcp-deploy] done. MCP endpoints:"
terraform -chdir="$HERE/terraform/mcp" output mcp_urls

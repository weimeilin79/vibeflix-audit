#!/usr/bin/env bash
#
# run_mesh_cloudbuild.sh — run the whole mesh install in Cloud Build instead of your terminal.
#
#     ./deploy/run_mesh_cloudbuild.sh                  # submit and stream
#     ./deploy/run_mesh_cloudbuild.sh --resume         # continue where the last build stopped
#     ./deploy/run_mesh_cloudbuild.sh --async          # submit, print the log URL, return
#     ./deploy/run_mesh_cloudbuild.sh --grant-owner    # grant the build SA owner, then submit
#
# The install takes the better part of an hour and Cloud Shell cannot be relied on to live that
# long. A build runs on Google's infrastructure, so nothing on your side can interrupt it.
#
# ── THE PERMISSIONS DIFFERENCE, WHICH IS THE WHOLE CATCH ────────────────────────────────────
# In your shell you are the project OWNER, so nothing is ever denied. A build does not run as
# you — it runs as a SERVICE ACCOUNT, and by default that account cannot do most of this. The
# install creates service accounts, edits project IAM, creates buckets/Firestore/Pub-Sub/
# Artifact Registry, deploys Cloud Run services and Vertex agent engines, and registers an
# agent gateway. Between them those need, at minimum:
#
#   serviceusage.serviceUsageAdmin   iam.serviceAccountAdmin      resourcemanager.projectIamAdmin
#   storage.admin                    datastore.owner              pubsub.admin
#   artifactregistry.admin           run.admin                    iam.serviceAccountUser
#   cloudbuild.builds.editor         aiplatform.admin             networkservices/iap admin
#
# Enumerating them exactly is a losing game: miss one and the build fails forty minutes in, at
# whatever step happened to need it. On a throwaway DEMO project the honest answer is to grant
# the build service account roles/owner — which is why that is opt-in here, printed in full
# before it happens, and never done silently. On a project that is not disposable, don't:
# curate the list above instead, and expect to iterate.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"; cd "$ROOT"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }

GRANT_OWNER=0; ASYNC=0; MESH_ARGS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --grant-owner) GRANT_OWNER=1; shift ;;
    --async) ASYNC=1; shift ;;
    -h|--help) sed -n '3,10p' "$0"; exit 0 ;;
    *) MESH_ARGS="$MESH_ARGS $1"; shift ;;    # --resume / --from X / --skip-gateway
  esac
done
MESH_ARGS="${MESH_ARGS# }"

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
[ -n "$PROJECT" ] && [ "$PROJECT" != "(unset)" ] || {
  echo "✗ no project. Run: gcloud config set project <id>" >&2; exit 1; }
PNUM="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"

echo "▶ project      : $PROJECT ($PNUM)"
echo "▶ mesh args    : ${MESH_ARGS:-<none — full install>}"

# Cloud Build needs to exist before it can run anything.
gcloud services enable cloudbuild.googleapis.com --project="$PROJECT" >/dev/null 2>&1 || true

# Which identity will the build run as? Projects created before the 2024 change use the legacy
# Cloud Build SA; newer ones default to the Compute Engine default SA. Pick whichever exists
# rather than guessing, and let BUILD_SA override.
BUILD_SA="${BUILD_SA:-}"
if [ -z "$BUILD_SA" ]; then
  for CAND in "$PNUM-compute@developer.gserviceaccount.com" "$PNUM@cloudbuild.gserviceaccount.com"; do
    gcloud iam service-accounts describe "$CAND" --project="$PROJECT" >/dev/null 2>&1 && { BUILD_SA="$CAND"; break; }
  done
fi
[ -n "$BUILD_SA" ] || { echo "✗ could not find a build service account — set BUILD_SA=…" >&2; exit 1; }
echo "▶ build runs as: $BUILD_SA"

# Does it already have enough? Only owner is checked, because that is the only answer this
# script offers; a curated role set is a deliberate choice made outside it.
HAS_OWNER="$(gcloud projects get-iam-policy "$PROJECT" --flatten='bindings[].members' \
  --filter="bindings.role=roles/owner AND bindings.members:$BUILD_SA" \
  --format='value(bindings.role)' 2>/dev/null | head -1)"

if [ -z "$HAS_OWNER" ]; then
  if [ "$GRANT_OWNER" = 1 ]; then
    echo
    echo "  GRANTING roles/owner on $PROJECT to serviceAccount:$BUILD_SA"
    echo "  This lets any future build in this project do anything to it. Appropriate for a"
    echo "  disposable demo project; not for one that matters."
    gcloud projects add-iam-policy-binding "$PROJECT" \
      --member="serviceAccount:$BUILD_SA" --role=roles/owner --condition=None -q >/dev/null
    echo "  ✓ granted"
  else
    cat >&2 <<MSG

✗ $BUILD_SA is not an owner of $PROJECT, and the install will fail without
  broad permissions — probably deep into the run, when it first tries to create a service
  account or edit project IAM.

  For a disposable demo project, re-run with --grant-owner (or grant it yourself):

      gcloud projects add-iam-policy-binding $PROJECT \\
        --member="serviceAccount:$BUILD_SA" --role=roles/owner --condition=None

  For a project you care about, grant the curated role list in this script's header instead,
  and expect to add to it.
MSG
    exit 1
  fi
fi

echo "▶ submitting…"
# --ignore-file: the DEFAULT .gcloudignore is written for the agent/app IMAGE builds and drops
# workshop/ and deploy/img/ — the installer's own entry point and its seed data. See
# .gcloudignore-mesh.
set -x
gcloud builds submit "$ROOT" \
  --project="$PROJECT" \
  --config="$HERE/cloudbuild-mesh.yaml" \
  --ignore-file="$ROOT/.gcloudignore-mesh" \
  --substitutions="_MESH_ARGS=$MESH_ARGS" \
  $( [ "$ASYNC" = 1 ] && echo --async )

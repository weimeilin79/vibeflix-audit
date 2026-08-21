#!/usr/bin/env bash
#
# run_mesh_cloudbuild.sh — run the whole mesh install in Cloud Build instead of your terminal.
#
#     ./deploy/run_mesh_cloudbuild.sh                  # submit and stream
#     ./deploy/run_mesh_cloudbuild.sh --resume         # continue where the last build stopped
#     ./deploy/run_mesh_cloudbuild.sh --wait            # stay attached and stream the log
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

# Async by DEFAULT. The entire reason this path exists is that the install outlives a Cloud
# Shell session — so blocking the terminal on it recreates the problem we came here to solve.
# --wait opts back into streaming for anyone who wants to watch.
GRANT_OWNER=0; ASYNC=1; MESH_ARGS=""; JUST_GRANTED=0
while [ $# -gt 0 ]; do
  case "$1" in
    --grant-owner) GRANT_OWNER=1; shift ;;
    --async) ASYNC=1; shift ;;          # kept for compatibility; already the default
    --wait) ASYNC=0; shift ;;
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

# Cloud Build and IAM have to exist before anything below can use them. Fail loudly: a silenced
# failure here resurfaces as a confusing "service account not found" two commands later.
gcloud services enable cloudbuild.googleapis.com iam.googleapis.com \
  --project="$PROJECT" >/dev/null || {
    echo "✗ could not enable cloudbuild/iam on $PROJECT — check billing is linked." >&2; exit 1; }

# Which identity does the build run as?
#
# Not a default one. On a BRAND-NEW project there is nothing to find: the Compute Engine default
# SA only exists once compute.googleapis.com is enabled, and the legacy
# <number>@cloudbuild.gserviceaccount.com is not created at all for projects made after Google's
# 2024 change. Probing for either is how this script used to fail on exactly the project it is
# meant to bootstrap.
#
# So create a DEDICATED one instead. It works identically on a fresh or an established project,
# it is the account the --grant-owner decision applies to (rather than the compute default SA,
# which other workloads also use), and deleting it revokes this pipeline in one step.
BUILD_SA="${BUILD_SA:-vibeflix-mesh-builder@$PROJECT.iam.gserviceaccount.com}"
if ! gcloud iam service-accounts describe "$BUILD_SA" --project="$PROJECT" >/dev/null 2>&1; then
  SA_ID="${BUILD_SA%%@*}"
  echo "▶ creating build service account ${SA_ID}…"
  gcloud iam service-accounts create "$SA_ID" --project="$PROJECT" \
    --display-name "Vibeflix mesh installer (Cloud Build)" >/dev/null
  # IAM is eventually consistent; a grant or an actAs immediately after create can 404.
  for _ in 1 2 3 4 5 6; do
    gcloud iam service-accounts describe "$BUILD_SA" --project="$PROJECT" >/dev/null 2>&1 && break
    sleep 5
  done
fi
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
    JUST_GRANTED=1
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

# An IAM grant is not in force the moment it is written. The policy reads back with the new
# binding immediately, but enforcement — GCS especially — lags by a minute or more, so a submit
# fired straight after --grant-owner fails with a 403 on the source tarball that looks exactly
# like a missing role. Give it a head start rather than making the first attempt the canary.
if [ "$JUST_GRANTED" = 1 ]; then
  echo "▶ waiting 60s for the owner grant to take effect (IAM is eventually consistent)…"
  sleep 60
fi

echo "▶ submitting…"
# --ignore-file: the DEFAULT .gcloudignore is written for the agent/app IMAGE builds and drops
# workshop/ and deploy/img/ — the installer's own entry point and its seed data. See
# .gcloudignore-mesh.
ASYNC_FLAG=""; [ "$ASYNC" = 1 ] && ASYNC_FLAG="--async"
submit() {
  gcloud builds submit "$ROOT" \
    --project="$PROJECT" \
    --config="$HERE/cloudbuild-mesh.yaml" \
    --ignore-file="$ROOT/.gcloudignore-mesh" \
    --substitutions="_MESH_ARGS=$MESH_ARGS" \
    --service-account="projects/$PROJECT/serviceAccounts/$BUILD_SA" \
    $ASYNC_FLAG
}
# Retry ONLY a submit-side failure. Once a build has been created and run, a non-zero exit is
# the INSTALL failing — re-running it four times just repeats a doomed 40-minute build and
# reports it as "IAM propagation", which is both wrong and expensive. The two are easy to tell
# apart: a rejected submit never gets a build id.
OUT="$(mktemp)"; trap 'rm -f "$OUT"' EXIT
n=1
while :; do
  if submit 2>&1 | tee "$OUT"; then break; fi
  if grep -qE "BUILD FAILURE|completed with status|Build step failure" "$OUT"; then
    echo >&2
    echo "✗ the BUILD ran and failed — this is the install, not permissions." >&2
    echo "  Read the phase failure above (or in the Cloud Build log), fix it, then re-run." >&2
    echo "  Nothing is retried: the same build would fail the same way." >&2
    grep -oE "https://console\.cloud\.google\.com/cloud-build/builds/[^ ]*" "$OUT" | head -1 >&2
    exit 1
  fi
  if [ "$n" -ge 4 ]; then
    echo "✗ could not submit after $n attempts (never reached a build)." >&2
    echo "  A 403 on storage.objects.get for $BUILD_SA is IAM still propagating — wait a" >&2
    echo "  couple of minutes and re-run. Nothing needs undoing." >&2
    exit 1
  fi
  echo "! submit rejected before starting a build (attempt $n/4) — retrying in 45s"
  sleep 45; n=$((n + 1))
done

if [ "$ASYNC" = 1 ]; then
  BUILD_ID="$(grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$OUT" | head -1)"
  cat <<INFO

════════════════════════════════════════════════════════════════════
 Submitted. This shell is free — closing it will NOT stop the build.
════════════════════════════════════════════════════════════════════

  console : https://console.cloud.google.com/cloud-build/builds/$BUILD_ID?project=$PNUM

  status  : gcloud builds describe $BUILD_ID --project $PROJECT --format='value(status)'
  follow  : gcloud builds log $BUILD_ID --project $PROJECT --stream
  stop it : gcloud builds cancel $BUILD_ID --project $PROJECT

  Per-phase logs land in gs://$PROJECT-artifacts/mesh-logs/$BUILD_ID/
  once the foundations phase creates that bucket — on failure as well as success.

  If it fails, fix the cause and re-run this script: the build restores
  .env, agent_identities.json, terraform state and .mesh_state, so it
  continues rather than starting over.
INFO
fi

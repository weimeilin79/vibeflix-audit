#!/usr/bin/env bash
# setup_buckets.sh — create the GCS buckets the mesh needs, and seed the default
# mockup. Run this in Step 1 (foundations), BEFORE the terraform agents module (which only
# GRANTS iam on these buckets — google_storage_bucket_iam_member — and assumes they already
# exist) and before deploying the app.
#
# ⚠️ GCS bucket names are GLOBALLY unique. The historical hardcoded names
# (vibeflix-request-image / vibeflix-approved-assets) are already taken, so a FRESH project
# 409s on create. The defaults here are therefore PROJECT-PREFIXED and never collide.
# Override with REQUEST_IMAGE_BUCKET / APPROVED_ASSETS_BUCKET in deploy/.env (the existing
# pokedemo-test deploy pins them to its original unprefixed buckets for backward-compat).
#
#   REQUEST_IMAGE_BUCKET   — console mockup UPLOADS + the default scenario image live here.
#   APPROVED_ASSETS_BUCKET — an approved image source (brand_style's asset-source gate).
#   BUCKET                 — the private staging/artifacts bucket. setup_legal_rag.sh stages
#                            resource/legal/docs/ here before RAG imports them, and
#                            setup_memory.sh uses it too. Created HERE because legal RAG runs
#                            in Step 4, long before setup_memory.sh would have made it — on a
#                            fresh project that failed with 'The specified bucket does not exist'.
#
# Usage:  PROJECT=… REGION=… ./deploy/setup_buckets.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:?set PROJECT in deploy/.env}}"
REGION="${REGION:-us-central1}"
RIB="${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image}"
AAB="${APPROVED_ASSETS_BUCKET:-$PROJECT-approved-assets}"
BKT="${BUCKET:-$PROJECT-artifacts}"

echo "[setup_buckets] project=$PROJECT region=$REGION"
for B in "$RIB" "$AAB" "$BKT"; do
  if gcloud storage buckets describe "gs://$B" --project="$PROJECT" >/dev/null 2>&1; then
    echo "  ✓ gs://$B already exists"
  elif gcloud storage buckets create "gs://$B" --project="$PROJECT" --location="$REGION" \
         --uniform-bucket-level-access >/dev/null 2>&1; then
    echo "  ✓ created gs://$B"
  else
    echo "  ✗ could not create gs://$B — the name is taken GLOBALLY. Pick a unique name:" >&2
    echo "    add REQUEST_IMAGE_BUCKET / APPROVED_ASSETS_BUCKET / BUCKET =<unique> to" >&2
    echo "    deploy/.env and re-run." >&2
    exit 1
  fi
done

# Seed EVERY mock-up in deploy/img/ into the request-image bucket, not just the default one.
# Adding a scenario should mean dropping a file in that folder — nothing here to edit. The
# console's form default and the guided scenarios point at vendor_request_refine.png, so that
# one is called out separately if it's missing.
IMG_DIR="$ROOT/deploy/img"
shopt -s nullglob
IMGS=("$IMG_DIR"/*.png "$IMG_DIR"/*.jpg "$IMG_DIR"/*.jpeg "$IMG_DIR"/*.webp)
shopt -u nullglob
if [ ${#IMGS[@]} -eq 0 ]; then
  echo "  ⚠️ no mock-ups found in $IMG_DIR"
else
  for f in "${IMGS[@]}"; do
    B="$(basename "$f")"
    gcloud storage cp "$f" "gs://$RIB/$B" --project="$PROJECT" >/dev/null \
      && echo "  ✓ seeded $B → gs://$RIB/$B" \
      || echo "  ✗ could not upload $B" >&2
  done
fi
[ -f "$IMG_DIR/vendor_request_refine.png" ] \
  || echo "  ⚠️ vendor_request_refine.png is missing — the console form's default image will 404"

echo
echo "[setup_buckets] PIN these in deploy/.env so the app, the seed, and terraform all agree:"
echo "  REQUEST_IMAGE_BUCKET=$RIB"
echo "  APPROVED_ASSETS_BUCKET=$AAB"
echo "  BUCKET=$BKT"
echo "  (terraform agents module: pass -var upload_bucket=\$REQUEST_IMAGE_BUCKET and"
echo "   -var 'asset_buckets=[\"'\$REQUEST_IMAGE_BUCKET'\",\"'\$APPROVED_ASSETS_BUCKET'\"]')"

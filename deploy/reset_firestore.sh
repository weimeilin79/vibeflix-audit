#!/usr/bin/env bash
#
# reset_firestore.sh — restore the Vibeflix demo state to its ORIGINAL condition:
#
#   1. registries re-seeded to defaults (brand_style_registry / legal_registry /
#      market_policy — undoes any live edits)
#   2. vendors restored to the 12 pristine defaults; vendors onboarded at runtime
#      are DELETED, categories added to defaults are removed  (RESET_VENDORS=1)
#   3. the `audit_history` collection wiped (every completed audit)
#   4. uploaded mockups deleted from the request-image GCS bucket
#      (gs://vibeflix-request-image — the curated approved-assets bucket is
#      never touched)
#   5. the local JSONL history fallback removed (data/app/audit_history.jsonl)
#
# NOTE: executed contracts + the app's in-memory history live in running
# processes — if the mesh is up, either click **Reset database** in the console's
# Audit History tab (does all of this via POST /api/reset) or restart:
#   docker compose restart mcp_licensing vendor_clearance legal deal_pricing app
#
# Config comes from deploy/.env (PROJECT / REGION / DATABASE / BUCKETS), same as
# the other deploy scripts; shell env vars override.
#
# Usage:
#   ./deploy/reset_firestore.sh          # asks for confirmation
#   ./deploy/reset_firestore.sh -y       # skip the confirmation (or FORCE=1)
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

ENV_FILE="$HERE/.env"
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi
PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
DATABASE="${DATABASE:-${FIRESTORE_DATABASE:-vibeflix-registry}}"
UPLOAD_BUCKET="${REQUEST_IMAGE_BUCKET:-vibeflix-request-image}"
[ -n "$PROJECT" ] || { echo "ERROR: PROJECT not set — add PROJECT=... to deploy/.env" >&2; exit 1; }

echo "[reset_firestore] project=$PROJECT database=$DATABASE upload-bucket=gs://$UPLOAD_BUCKET"

if [ "${1:-}" != "-y" ] && [ "${FORCE:-}" != "1" ]; then
  read -r -p "Restore ORIGINAL demo state (wipes audit history, onboarded vendors, uploads)? [y/N] " ans
  case "$ans" in y|Y) ;; *) echo "aborted."; exit 1;; esac
fi

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "[reset_firestore] 1-2/5 re-seeding registries + resetting vendors…"
GOOGLE_CLOUD_PROJECT="$PROJECT" FIRESTORE_DATABASE="$DATABASE" RESET_VENDORS=1 \
  "$PY" "$ROOT/deploy/seed_firestore.py"

echo "[reset_firestore] 3/5 wiping the audit_history collection…"
GOOGLE_CLOUD_PROJECT="$PROJECT" FIRESTORE_DATABASE="$DATABASE" "$PY" - <<'PY'
import os
from google.cloud import firestore

col = firestore.Client(database=os.environ["FIRESTORE_DATABASE"]).collection("audit_history")
n = 0
for doc in col.stream():
    doc.reference.delete()
    n += 1
print(f"   audit_history: {n} audit(s) deleted")
PY

echo "[reset_firestore] 4/5 deleting uploaded mockups from gs://$UPLOAD_BUCKET/…"
gcloud storage rm "gs://$UPLOAD_BUCKET/**" --project "$PROJECT" 2>/dev/null \
  || echo "   (bucket already empty)"

echo "[reset_firestore] 5/5 removing the local JSONL fallback…"
rm -f "$ROOT/data/app/audit_history.jsonl" && echo "   removed" || true

echo "[reset_firestore] done."
echo "If the mesh is RUNNING, bounce it so in-memory state (contracts, loaded"
echo "history) matches: docker compose restart mcp_licensing vendor_clearance legal deal_pricing app"

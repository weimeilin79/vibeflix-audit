#!/usr/bin/env bash
#
# setup_firestore.sh — provision EVERYTHING Vibeflix keeps in Firestore:
#
#   1. the dedicated named database (default: vibeflix-registry, native mode)
#   2. the semantic registries the MCP servers read (seeded by seed_firestore.py;
#      live-editable rules — brand terms, printed media, legal registry, caps)
#      + the `vendors` collection (mcp_licensing's CRUD store: create-missing by
#      default; RESET_VENDORS=1 ./deploy/setup_firestore.sh restores the defaults)
#   3. the `audit_history` collection the app writes (one document per audit
#      ORDER, doc id = order id; no seeding needed — verified with a smoke test)
#
# The mesh runs WITHOUT Firestore too: MCP servers fall back to hardcoded
# defaults and the app falls back to data/app/audit_history.jsonl. This script
# enables the managed backend.
#
# Config comes from deploy/.env (PROJECT / REGION / DATABASE), same as the other
# deploy scripts; real shell env vars override the file.
#
# Usage:
#   ./deploy/setup_firestore.sh
#   PROJECT=my-proj REGION=us-central1 DATABASE=vibeflix-registry ./deploy/setup_firestore.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
. "$HERE/lib_setup.sh"

# --- config: deploy/.env (the same file the other setup scripts load) ---
ENV_FILE="$HERE/.env"
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi
PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
REGION="${REGION:-us-central1}"
DATABASE="${DATABASE:-${FIRESTORE_DATABASE:-vibeflix-registry}}"
[ -n "$PROJECT" ] || { echo "ERROR: PROJECT not set — add PROJECT=... to deploy/.env" >&2; exit 1; }

echo "[setup_firestore] project=$PROJECT region=$REGION database=$DATABASE"
gcloud config set project "$PROJECT" >/dev/null

echo "[setup_firestore] 1/4 enabling the Firestore API…"
gcloud services enable firestore.googleapis.com

echo "[setup_firestore] 2/4 creating the '$DATABASE' database (native mode)…"
# Dedicated named DB — isolated from the project's shared (default) database.
ensure_created "the '$DATABASE' database" \
  gcloud firestore databases create \
  --database="$DATABASE" --location="$REGION" \
  --type=firestore-native --project="$PROJECT"

# Prefer the repo venv's python if present (has google-cloud-firestore).
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "[setup_firestore] 3/4 seeding the semantic registries…"
GOOGLE_CLOUD_PROJECT="$PROJECT" FIRESTORE_DATABASE="$DATABASE" \
  "$PY" "$ROOT/deploy/seed_firestore.py"

echo "[setup_firestore] 4/4 smoke-testing the audit_history collection…"
GOOGLE_CLOUD_PROJECT="$PROJECT" FIRESTORE_DATABASE="$DATABASE" "$PY" - <<'PY'
import os
from google.cloud import firestore

db = firestore.Client(database=os.environ["FIRESTORE_DATABASE"])
col = db.collection("audit_history")
probe = col.document("_setup_probe")
probe.set({"probe": True})
probe.delete()
n = sum(1 for _ in col.limit(500).stream())
print(f"   audit_history: write/delete OK · {n} audit(s) currently stored")
PY

echo "[setup_firestore] done."
echo
echo "Enable it by setting FIRESTORE_DATABASE=$DATABASE:"
echo "  • docker compose: the app service already defaults to '$DATABASE'"
echo "    (registries: FIRESTORE_DATABASE=$DATABASE docker compose up for the 3 MCP servers)"
echo "  • local:          export FIRESTORE_DATABASE=$DATABASE before ./run_local.sh"
echo "  • Cloud Run:      set FIRESTORE_DATABASE on the app + MCP services; the runtime"
echo "                    service account needs roles/datastore.user on $PROJECT."
echo
echo "What lives where:"
echo "  • registries (MCP servers read):  brand_style_registry / legal_registry / market_policy"
echo "  • vendors (mcp_licensing CRUD):   vendors — onboarding survives restarts;"
echo "                                    RESET_VENDORS=1 $0 restores the defaults"
echo "  • audit history (app writes):     audit_history — one doc per audit order (latest state)"

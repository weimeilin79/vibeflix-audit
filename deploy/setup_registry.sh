#!/usr/bin/env bash
#
# setup_registry.sh — provision the Firestore semantic-registry backend (Phase 2):
# a dedicated Firestore database + seed the current registry values.
#
# The MCP servers read registries from this database when FIRESTORE_DATABASE is
# set, and fall back to their hardcoded defaults otherwise — so this is optional
# (the mesh runs without it) and enables live-editable rules without a redeploy.
#
# Usage:
#   PROJECT=pokedemo-test REGION=us-central1 DATABASE=vibeflix-registry \
#     ./deploy/setup_registry.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${PROJECT:-pokedemo-test}"
REGION="${REGION:-us-central1}"
DATABASE="${DATABASE:-vibeflix-registry}"

echo "[setup_registry] project=$PROJECT region=$REGION database=$DATABASE"
gcloud config set project "$PROJECT" >/dev/null

echo "[setup_registry] 1/3 enabling Firestore API…"
gcloud services enable firestore.googleapis.com

echo "[setup_registry] 2/3 creating the '$DATABASE' database (native)…"
# Dedicated DB — isolated from the project's shared (default) database.
gcloud firestore databases create \
  --database="$DATABASE" --location="$REGION" \
  --type=firestore-native --project="$PROJECT" \
  || echo "   (database may already exist — continuing)"

echo "[setup_registry] 3/3 seeding registry values…"
# Prefer the repo venv's python if present (has google-cloud-firestore).
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
GOOGLE_CLOUD_PROJECT="$PROJECT" FIRESTORE_DATABASE="$DATABASE" \
  "$PY" "$ROOT/deploy/seed_firestore.py"

echo "[setup_registry] done."
echo "[setup_registry] Enable it by setting FIRESTORE_DATABASE=$DATABASE"
echo "                 (local: export it before ./run_local.sh mcp;"
echo "                  compose: FIRESTORE_DATABASE=$DATABASE docker compose up)."
echo "[setup_registry] Grant the runtime service account roles/datastore.user if"
echo "                 it isn't your ADC user."

#!/usr/bin/env bash
#
# setup_legal_rag.sh — provision the Legal knowledge-base RAG corpus (replicable setup).
#
# Ingests resource/legal/docs/ into a Vertex AI RAG Engine corpus backed by the
# RAG-managed Vertex AI Vector Search store, via the Agent Platform 2.0 SDK.
# Wraps deploy/setup_legal_rag.py: ensures the SDK + APIs, then runs it.
#
# Usage:
#   PROJECT=pokedemo-test REGION=us-central1 BUCKET=vibeflix-artifacts \
#     ./deploy/setup_legal_rag.sh
#
set -euo pipefail

PROJECT="${PROJECT:-pokedemo-test}"
REGION="${REGION:-us-central1}"          # RAG Engine is regional, not "global"
BUCKET="${BUCKET:-vibeflix-artifacts}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"

echo "[setup_legal_rag] project=$PROJECT region=$REGION bucket=$BUCKET"
[ -x "$PY" ] || { echo "No python at $PY — set PY=/path/to/python"; exit 1; }

echo "[setup_legal_rag] 1/3 enabling APIs…"
gcloud services enable aiplatform.googleapis.com storage.googleapis.com --project "$PROJECT"

echo "[setup_legal_rag] 2/3 ensuring provisioning SDK (deploy/requirements-legal-rag.txt)…"
"$PY" -c "import agentplatform, pandas" 2>/dev/null \
  || "$PY" -m pip install --quiet -r "$ROOT/deploy/requirements-legal-rag.txt"

echo "[setup_legal_rag] 3/3 creating corpus + importing docs…"
PROJECT="$PROJECT" REGION="$REGION" BUCKET="$BUCKET" "$PY" "$ROOT/deploy/setup_legal_rag.py"

echo "[setup_legal_rag] done. Copy the printed RAG_CORPUS/RAG_LOCATION into the legal"
echo "                  agent's env (docker-compose 'legal' service or agents/legal/.env)."

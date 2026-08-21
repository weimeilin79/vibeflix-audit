#!/usr/bin/env bash
#
# setup_legal_rag.sh — provision the Legal knowledge-base RAG corpus (replicable setup).
#
# Ingests resource/legal/docs/ into a Vertex AI RAG Engine corpus backed by the
# RAG-managed Vertex AI Vector Search store, via the Agent Platform 2.0 SDK.
# Wraps deploy/setup_legal_rag.py: ensures the SDK + APIs, then runs it.
#
# Usage:
#   PROJECT=<your-project> REGION=us-central1 BUCKET=vibeflix-artifacts \
#     ./deploy/setup_legal_rag.sh
#
set -euo pipefail

if [ -z "${PROJECT:-}" ]; then
  echo "✗ PROJECT is not set. Refusing to guess." >&2
  echo "  This used to default to a hardcoded project — so forgetting to export PROJECT" >&2
  echo "  silently deployed to (or read from) SOMEONE ELSE'S project." >&2
  echo "  Run:  export PROJECT=<your-project> REGION=<your-region>" >&2
  exit 1
fi
PROJECT="${PROJECT}"
REGION="${REGION:-us-central1}"          # RAG Engine is regional, not "global"
BUCKET="${BUCKET:-vibeflix-artifacts}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib_setup.sh"

echo "[setup_legal_rag] project=$PROJECT region=$REGION bucket=$BUCKET"
[ -x "$PY" ] || { echo "No python at $PY — set PY=/path/to/python"; exit 1; }

echo "[setup_legal_rag] 1/3 enabling APIs…"
ensure_apis aiplatform.googleapis.com storage.googleapis.com

echo "[setup_legal_rag] 2/3 ensuring provisioning SDK (deploy/requirements-legal-rag.txt)…"
"$PY" -c "import agentplatform, pandas" 2>/dev/null \
  || "$PY" -m pip install --quiet -r "$ROOT/deploy/requirements-legal-rag.txt"

echo "[setup_legal_rag] 3/3 creating corpus + importing docs…"
PROJECT="$PROJECT" REGION="$REGION" BUCKET="$BUCKET" "$PY" "$ROOT/deploy/setup_legal_rag.py"

echo "[setup_legal_rag] done. RAG_CORPUS/RAG_LOCATION were written to deploy/.env — the next"
echo "                  'source ./env.sh' exports them, and deploying legal picks them up."

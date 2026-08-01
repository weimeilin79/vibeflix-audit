#!/usr/bin/env bash
# init.sh — one-time workshop init. Run ONCE from the repo root, right after cloning:
#
#     git clone https://github.com/weimeilin79/vibeflix-audit
#     cd vibeflix-audit
#     ./init.sh
#
# It consolidates the whole "get ready" step:
#   1. confirms you're authenticated to gcloud
#   2. resolves your project id, points gcloud at it, and records it to ~/project_id.txt
#   3. defaults the region to us-central1 (override with REGION=… ./init.sh)
#   4. creates the Python venv (.venv) and installs every dependency
#   5. writes deploy/.env — the config file every workshop script reads
#
# Idempotent: safe to re-run. It reuses an existing .venv and won't clobber an existing .env.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"

# ── 1. gcloud auth sanity check ──────────────────────────────────────────────
echo "▶ Checking gcloud authentication…"
ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1)"
if [ -z "$ACCOUNT" ]; then
  echo "  ✗ No active gcloud account. Authenticate first, then re-run:" >&2
  echo "      gcloud auth login" >&2
  echo "      gcloud auth application-default login   # ADC — needed for deploys + the RAG setup" >&2
  exit 1
fi
echo "  ✓ Authenticated as: $ACCOUNT"

# ── 2. Resolve the project id: arg > ~/project_id.txt > $PROJECT_ID > gcloud config > prompt ──
PROJECT_ID="${1:-${PROJECT_ID:-}}"
if [ -z "$PROJECT_ID" ] && [ -f "$HOME/project_id.txt" ]; then
  PROJECT_ID="$(tr -d '[:space:]' < "$HOME/project_id.txt")"
fi
[ -n "$PROJECT_ID" ] || PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
if [ -z "${PROJECT_ID}" ] || [ "${PROJECT_ID}" = "(unset)" ]; then
  read -r -p "Enter your Google Cloud Project ID: " PROJECT_ID
fi
[ -n "${PROJECT_ID}" ] || { echo "No project id given — aborting." >&2; exit 1; }

# Region: honour $REGION if set, otherwise default to us-central1.
REGION="${REGION:-us-central1}"

echo "▶ Project: $PROJECT_ID    Region: $REGION"
gcloud config set project "$PROJECT_ID" --quiet
# Record it so later scripts (and a fresh Cloud Shell tab) resolve it with no prompt.
printf '%s\n' "$PROJECT_ID" > "$HOME/project_id.txt"
echo "  ✓ Saved project id to ~/project_id.txt"

# ── 3. Python venv + dependencies ────────────────────────────────────────────
if [ ! -d .venv ]; then
  echo "▶ Creating Python virtual environment (.venv)…"
  python3 -m venv .venv
else
  echo "▶ Reusing existing .venv"
fi
# Use the venv's interpreters directly — activating inside a script wouldn't persist to your
# shell anyway, and the workshop invokes tools as `.venv/bin/python …`.
echo "▶ Installing dependencies (a few minutes)…"
.venv/bin/python -m pip install --upgrade pip --quiet
# --pre: the ADK 2.0 Workflow API is pre-GA (see the header of agents/requirements.txt); the
# version caps/pins in that file keep --pre from pulling anything too new.
.venv/bin/pip install --pre --quiet -r agents/requirements.txt -r deploy/requirements-legal-rag.txt
.venv/bin/pip install --quiet -e packages/vibeflix-common
echo "  ✓ Installed agent + legal-RAG deps and the vibeflix-common package (editable)."

# ── 4. Write deploy/.env (idempotent) ────────────────────────────────────────
ENV_FILE="deploy/.env"
if [ -f "$ENV_FILE" ]; then
  echo "▶ $ENV_FILE already exists — leaving it untouched (delete it to regenerate)."
else
  cp deploy/.env.example "$ENV_FILE"
  sed -i.bak \
    -e "s|^PROJECT=.*|PROJECT=$PROJECT_ID|" \
    -e "s|^GOOGLE_CLOUD_PROJECT=.*|GOOGLE_CLOUD_PROJECT=$PROJECT_ID|" \
    -e "s|^REGION=.*|REGION=$REGION|" \
    -e "s|^RAG_LOCATION=.*|RAG_LOCATION=$REGION|" \
    -e "s|^BUCKET=.*|BUCKET=$PROJECT_ID-artifacts|" \
    -e "s|^TASK_STORE_KEY=.*|TASK_STORE_KEY=$(openssl rand -hex 24)|" \
    "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  echo "  ✓ Wrote $ENV_FILE (PROJECT=$PROJECT_ID, REGION=$REGION, fresh TASK_STORE_KEY)."
fi

echo
echo "✅ Init done."
echo "   • Authenticated: $ACCOUNT"
echo "   • Project:       $PROJECT_ID   (Region: $REGION, saved to ~/project_id.txt)"
echo "   • venv:          .venv         (activate for your own shell with:  source .venv/bin/activate)"
echo "   • Next:          ./workshop/setup.sh"

#!/usr/bin/env bash
# init.sh — one-time workshop init. Run ONCE from the repo root, right after cloning:
#
#     git clone https://github.com/weimeilin79/vibeflix-audit
#     cd vibeflix-audit
#     ./init.sh
#
# It consolidates the whole "get ready" step:
#   1. checks the environment has every CLI the workshop needs (delegates to deploy/preflight.sh
#      --pre-init, so the tool checklist lives in exactly ONE place) and that you're authenticated
#   2. resolves your project id, points gcloud at it, and records it to ~/project_id.txt
#   3. defaults the region to us-central1 (override with REGION=… ./init.sh)
#   4. creates the Python venv (.venv) and installs every dependency
#   5. installs terraform into ~/bin if it's missing (Cloud Shell no longer ships it)
#   6. installs agents-cli into its own venv (.venv-tools), isolated from the pinned agent deps
#   7. writes deploy/.env — the config file every workshop script reads
#
# Idempotent: safe to re-run. It reuses an existing .venv and terraform, and won't clobber
# an existing .env.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"

# On a re-run in a fresh tab, ~/.bashrc hasn't been re-sourced yet, so a terraform we installed
# on an earlier run isn't on PATH. Pick it up FIRST — before preflight (which would otherwise
# report the Cloud Shell placeholder) and before section 4 (which would re-download it).
[ -x "$HOME/bin/terraform" ] && export PATH="$HOME/bin:$PATH"

# ── 1. Environment check: every CLI + credential the workshop needs ──────────
# Delegated to preflight.sh so there is ONE tool checklist in the repo. --pre-init skips the
# two things init.sh is about to create itself (terraform, deploy/.env). Preflight exits
# non-zero if anything REQUIRED is missing, and `set -e` stops us here — nothing has been
# created yet, so re-running after a fix is clean.
echo "▶ Checking your environment…"
./deploy/preflight.sh --pre-init || {
  echo >&2
  echo "  ✗ Environment isn't ready — fix the ✗ lines above and re-run ./init.sh" >&2
  exit 1
}
ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1)"
echo

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
# Install the LOCK when it's there: every attendee then gets byte-identical versions, instead
# of re-resolving the `>=` ranges and drifting apart week to week. deploy/requirements.lock.txt
# documents how to regenerate it. The unlocked path stays as a fallback for a fresh checkout
# that hasn't got one (and needs --pre, since ADK 2.0 is pre-GA).
if [ -f deploy/requirements.lock.txt ]; then
  echo "   using deploy/requirements.lock.txt ($(grep -c '==' deploy/requirements.lock.txt) pinned packages)"
  .venv/bin/pip install --quiet -r deploy/requirements.lock.txt
else
  echo "   ! no lock file — resolving from the requirements files (versions may drift)"
  .venv/bin/pip install --pre --quiet -r agents/requirements.txt \
    -r deploy/requirements-legal-rag.txt -r deploy/requirements-deploy.txt
fi
.venv/bin/pip install --quiet -e packages/vibeflix-common
echo "  ✓ Installed agent + legal-RAG + deploy deps and the vibeflix-common package (editable)."
# Cloud Shell's home directory is capped at 5 GB and these installs are large (the venv is
# ~400 MB, agents-cli's isolated venv another ~500 MB). The wheel cache is pure duplication
# once installed, so drop it — a full home disk fails later steps in confusing ways.
.venv/bin/pip cache purge >/dev/null 2>&1 || true

# ── 4. terraform (Cloud Shell no longer pre-installs it) ─────────────────────
# Cloud Shell ships a PLACEHOLDER at /usr/bin/terraform that prints install instructions and
# exits 0 — so a plain `command -v terraform` check passes and `terraform apply` silently does
# nothing. Test for a real version string, not for presence. Install into ~/bin (which persists
# across Cloud Shell sessions, unlike `apt install`) and prepend it so it beats the placeholder.
tf_works() { terraform version 2>/dev/null | head -n1 | grep -q '^Terraform v'; }

if tf_works; then
  echo "▶ Reusing terraform $(terraform version | head -n1 | awk '{print $2}')"
else
  TF_VER="${TF_VER:-1.9.8}"
  case "$(uname -s)" in Darwin) TF_OS=darwin ;; *) TF_OS=linux ;; esac
  case "$(uname -m)" in aarch64|arm64) TF_ARCH=arm64 ;; *) TF_ARCH=amd64 ;; esac
  TF_ZIP="terraform_${TF_VER}_${TF_OS}_${TF_ARCH}.zip"
  command -v unzip >/dev/null 2>&1 || { echo "  ✗ need 'unzip' to install terraform" >&2; exit 1; }
  echo "▶ Installing terraform $TF_VER into ~/bin…"
  echo "    https://releases.hashicorp.com/terraform/${TF_VER}/${TF_ZIP}"
  mkdir -p "$HOME/bin"
  curl -fsSL -o "/tmp/$TF_ZIP" "https://releases.hashicorp.com/terraform/${TF_VER}/${TF_ZIP}"
  unzip -qo "/tmp/$TF_ZIP" terraform -d "$HOME/bin"
  rm -f "/tmp/$TF_ZIP"
  export PATH="$HOME/bin:$PATH"
  tf_works || { echo "  ✗ terraform still not runnable after install" >&2; exit 1; }
  echo "  ✓ terraform $(terraform version | head -n1 | awk '{print $2}') → $HOME/bin/terraform"
  # Persist the PATH for later Cloud Shell tabs (guarded — appended at most once).
  if ! grep -q 'vibeflix: terraform on PATH' "$HOME/.bashrc" 2>/dev/null; then
    printf '\n# vibeflix: terraform on PATH\nexport PATH="$HOME/bin:$PATH"\n' >> "$HOME/.bashrc"
    echo "  ✓ Added ~/bin to PATH in ~/.bashrc (new tabs pick it up automatically)."
    TF_NEEDS_PATH=1
  fi
fi

# ── 5. agents-cli (isolated, in .venv-tools) ─────────────────────────────────
# The lab talks to a deployed engine with `agents-cli`. It CANNOT share .venv — the two pin
# incompatible majors of the same package:
#     google-adk[a2a]==2.3.0    needs a2a-sdk >=0.3.4,<0.4
#     google-agents-cli==1.4.0  needs a2a-sdk >=1.0,<2
# (verified: `uv pip compile` of the two together is unsatisfiable). So it gets its own venv,
# and env.sh appends it to PATH. Costs ~500 MB — worth watching on Cloud Shell's 5 GB home.
# PINNED so the whole room runs the same CLI. Override with AGENTS_CLI_VER=… ./init.sh
AGENTS_CLI_VER="${AGENTS_CLI_VER:-1.4.0}"
_have_cli="$(.venv-tools/bin/pip show google-agents-cli 2>/dev/null | awk '/^Version:/{print $2}')"
if [ "$_have_cli" = "$AGENTS_CLI_VER" ]; then
  echo "▶ Reusing agents-cli $AGENTS_CLI_VER in .venv-tools"
else
  echo "▶ Installing agents-cli $AGENTS_CLI_VER (isolated in .venv-tools)…"
  [ -d .venv-tools ] || python3 -m venv .venv-tools
  .venv-tools/bin/python -m pip install --upgrade pip --quiet
  .venv-tools/bin/pip install --quiet "google-agents-cli==$AGENTS_CLI_VER"
  .venv-tools/bin/pip cache purge >/dev/null 2>&1 || true
  echo "  ✓ agents-cli $AGENTS_CLI_VER → .venv-tools/bin/agents-cli"
fi
unset _have_cli

# ── 6. Write deploy/.env (idempotent) ────────────────────────────────────────
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
echo "   • terraform:     $(command -v terraform)"
if [ -n "${TF_NEEDS_PATH:-}" ]; then
  echo
  echo "   ⚠️  terraform was just installed to ~/bin. In THIS shell, run:"
  echo "         export PATH=\"\$HOME/bin:\$PATH\""
  echo "       (new tabs get it automatically.)"
fi
echo "   • Next:          ./workshop/setup.sh"

#!/usr/bin/env bash
# preflight.sh — RUN THIS FIRST, before asking the agent to deploy vibeflix.
#
# Verifies every CLI tool, gcloud component, credential, and config file the runbook needs,
# so a from-scratch deploy doesn't die halfway on a missing dependency. Exits non-zero if a
# REQUIRED item is missing (fix those before starting); warnings (!) are advisory.
#
#   ./deploy/preflight.sh
set -uo pipefail
FAIL=0; WARN=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=1; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; WARN=1; }
have() { command -v "$1" >/dev/null 2>&1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "── Required tools ──────────────────────────────────────────────"

# Python 3.10–3.13 (the deploy scripts run locally: seed_firestore, deploy_agents_a2a,
# setup_legal_rag, collect_agent_identities). 3.14's pip is fragile — prefer 3.12/3.13.
if have python3; then
  PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "?")
  PYMIN=${PYV#*.}
  if [ "${PYV%%.*}" = "3" ] && [ "${PYMIN:-0}" -ge 10 ] 2>/dev/null && [ "${PYMIN:-0}" -le 13 ] 2>/dev/null; then
    ok "python3 $PYV"
  elif [ "${PYV%%.*}" = "3" ] && [ "${PYMIN:-0}" -ge 14 ] 2>/dev/null; then
    warn "python3 $PYV — 3.14's pip is fragile; use a 3.12/3.13 venv or 'uv venv' (runbook Step 0)"
  else
    bad "python3 $PYV — need 3.10–3.13 (install Python 3.12: https://www.python.org/downloads/)"
  fi
else
  bad "python3 not found — install Python 3.12 (https://www.python.org/downloads/)"
fi

# gcloud + the alpha/beta components (agent-registry, ai, iap live under alpha/beta) + auth.
if have gcloud; then
  ok "gcloud $(gcloud version 2>/dev/null | awk '/Google Cloud SDK/{print $NF}')"
  gcloud alpha --help >/dev/null 2>&1 && ok "gcloud alpha component" \
    || bad "gcloud alpha missing — run: gcloud components install alpha"
  gcloud beta  --help >/dev/null 2>&1 && ok "gcloud beta component" \
    || bad "gcloud beta missing — run: gcloud components install beta"
  ACCT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1)
  [ -n "$ACCT" ] && ok "gcloud authenticated ($ACCT)" \
    || bad "gcloud not authenticated — run: gcloud auth login"
  # Application Default Credentials (the python SDKs + terraform use ADC). A STALE
  # quota project here silently breaks the RAG bucket-ownership check — flag it.
  if gcloud auth application-default print-access-token >/dev/null 2>&1; then
    ok "application-default credentials present"
    QP=$(gcloud config get-value billing/quota_project 2>/dev/null)
    [ -n "$QP" ] && [ "$QP" != "(unset)" ] && warn "ADC quota project = $QP — make sure this project still EXISTS (a deleted one breaks the RAG SDK)"
  else
    bad "ADC missing — run: gcloud auth application-default login"
  fi
else
  bad "gcloud not found — install the Cloud SDK: https://cloud.google.com/sdk/docs/install"
fi

# terraform (deploy/terraform/{agents,mcp})
if have terraform; then ok "terraform $(terraform version 2>/dev/null | head -1 | awk '{print $2}')"
else bad "terraform not found — https://developer.hashicorp.com/terraform/install"; fi

# jq — grant_agent_iam.sh / setup_gateway.sh parse agent_identities.json with it.
have jq      && ok "jq"      || bad "jq not found — 'brew install jq' or 'apt-get install jq'"
# openssl — generates TASK_STORE_KEY.
have openssl && ok "openssl" || bad "openssl not found (needed to generate TASK_STORE_KEY)"
# curl — verify_deployment.sh probes the MCP/app endpoints.
have curl    && ok "curl"    || bad "curl not found"
# git — you cloned the repo; used for the vendored-common copy step.
have git     && ok "git"     || warn "git not found (expected in a clone)"

echo
echo "── Recommended ─────────────────────────────────────────────────"
have uv && ok "uv (fast venv/pip — ideal on Python 3.14)" \
  || warn "uv not installed (optional: 'pip install uv' or https://docs.astral.sh/uv)"
# docker (+ compose plugin) — REQUIRED to run the mesh LOCALLY ('./run_local.sh up' /
# 'docker compose up --build'). NOT needed for a cloud deploy: that builds via Cloud
# Build ('gcloud builds submit'). Advisory here since preflight targets the cloud deploy.
if have docker; then
  if docker compose version >/dev/null 2>&1; then ok "docker + compose plugin (for local 'docker compose up')"
  else warn "docker present but 'docker compose' plugin missing — needed to run the mesh locally"; fi
else
  warn "docker not installed — required only to run the mesh LOCALLY (run_local.sh); a cloud deploy uses Cloud Build"
fi

echo
echo "── Config ──────────────────────────────────────────────────────"
if [ -f "$HERE/.env" ]; then
  ok "deploy/.env present"
  grep -qE "^PROJECT=" "$HERE/.env" && ok "PROJECT set in deploy/.env" \
    || bad "PROJECT not set in deploy/.env"
else
  bad "deploy/.env missing — copy deploy/.env.example → deploy/.env and set PROJECT/REGION"
fi

echo
if [ "$FAIL" = 1 ]; then
  echo "❌ Missing REQUIRED items above — install/fix the ✗ lines, then re-run preflight."
  echo "   Do NOT start the deploy until this passes."
  exit 1
elif [ "$WARN" = 1 ]; then
  echo "⚠️  Ready, with warnings — skim the ! lines (they can bite mid-deploy). Then, in the"
  echo "   repo root: create the Python venv (runbook Step 0) and start the deploy."
  exit 0
else
  echo "✅ All prerequisites present. Next: create the Python venv (runbook Step 0), then deploy."
fi

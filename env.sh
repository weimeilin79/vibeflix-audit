#!/usr/bin/env bash
# env.sh — prepare THIS shell for any python / adk command in the workshop.
#
#     source ./env.sh
#
# Why it exists: every Cloud Shell tab starts fresh — no virtualenv, no exported project.
# Running `python deploy/…` in such a tab picks up Cloud Shell's SYSTEM python, which has a
# different (and incompatible) set of Google libraries installed, and fails with an import
# error that looks nothing like "you used the wrong python". Sourcing this file first makes
# that impossible.
#
# It is SOURCED, not executed, because it changes the current shell (that's the whole point).
# Safe to source as many times as you like.
#
# What it sets up:
#   • the repo's .venv          (so `python` is the right interpreter, with the right deps)
#   • deploy/.env               (PROJECT, REGION, and everything else the scripts read)
#   • PROJECT_ID / PROJECT_NUMBER
#   • GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION / GOOGLE_GENAI_USE_VERTEXAI
#   • ~/bin on PATH             (where init.sh installs terraform)

# Executed instead of sourced? Nothing would persist — say so rather than silently no-op.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "✗ env.sh has to be SOURCED so it can change this shell. Run:" >&2
  echo "      source ./env.sh" >&2
  exit 1
fi

_VF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -x "$_VF_ROOT/.venv/bin/python" ]; then
  echo "✗ no .venv in $_VF_ROOT — run ./init.sh first (it creates it)." >&2
  unset _VF_ROOT
  return 1
fi

# shellcheck disable=SC1091
. "$_VF_ROOT/.venv/bin/activate"

if [ -f "$_VF_ROOT/deploy/.env" ]; then
  set -a; . "$_VF_ROOT/deploy/.env"; set +a
else
  echo "! deploy/.env not found — run ./init.sh to write it." >&2
fi

export PROJECT_ID="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null)"
export GOOGLE_CLOUD_PROJECT="$PROJECT_ID"
# The ENGINES run in 'global' (deploy_agents_a2a.py and each agents/*/.env set it too); the
# deploy itself still targets $REGION from deploy/.env. Different things — both correct.
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
export GOOGLE_GENAI_USE_VERTEXAI=true
# Point local runs at the SAME seeded registries the workshop created in Step 1. Without this
# the MCP servers silently use their hardcoded fallback data, so editing Firestore appears to
# do nothing locally. registry_get() still falls back if Firestore is unreachable.
export FIRESTORE_DATABASE="${FIRESTORE_DATABASE:-vibeflix-registry}"
# init.sh installs terraform here when Cloud Shell doesn't ship a working one.
[ -x "$HOME/bin/terraform" ] && export PATH="$HOME/bin:$PATH"

echo "✓ shell ready — project=$PROJECT_ID region=${REGION:-us-central1} $(python -V 2>&1)"
unset _VF_ROOT

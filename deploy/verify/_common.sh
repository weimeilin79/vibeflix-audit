#!/usr/bin/env bash
# Shared helpers for the workshop per-step verify scripts (deploy/verify/step*.sh).
# SOURCED by those scripts — not run directly.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -f "$ROOT/deploy/.env" ] && { set -a; . "$ROOT/deploy/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"
REGION="${REGION:-us-central1}"
VERIFY_FAIL=0

ok()  { printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad() { printf "  \033[31m✗\033[0m %s\n" "$1"; VERIFY_FAIL=1; }

finish() {
  echo
  if [ "$VERIFY_FAIL" = 0 ]; then echo "✅ $1 — all checks passed."; else
    echo "❌ $1 — fix the ✗ items above, then re-run."; exit 1; fi
}

# Project IAM policy, fetched at most once per run (step4 checks two agents).
_PROJECT_POLICY=""
_project_policy() {
  [ -n "$_PROJECT_POLICY" ] || _PROJECT_POLICY="$(gcloud projects get-iam-policy "$PROJECT" --format=json 2>/dev/null)"
  printf '%s' "$_PROJECT_POLICY"
}

# check_agent <display-name> <label> — assert an agent engine is deployed WITH an agent identity,
# AND that grant_agent_access.sh has actually run for it.
#
# The deploy and the grant are two separate commands, and skipping the grant is silent: the engine
# exists, the identity exists, and this script used to pass. The agent then fails much later —
# 403 from the MCP servers, or an endless hang on task polls (no agentContextEditor) — with
# nothing pointing back at the missing grant. So verify the two bindings that prove it ran.
check_agent() {
  local disp="$1" label="$2" ids="$ROOT/deploy/agent_identities.json" eng principal sa
  if [ ! -f "$ids" ]; then bad "$label: deploy/agent_identities.json missing — deploy an agent first"; return; fi
  eng=$(jq -r --arg k "$disp" '.[$k].engine // empty' "$ids")
  principal=$(jq -r --arg k "$disp" '.[$k].principal // empty' "$ids")
  [ -n "$eng" ] && ok "$label engine deployed (…/${eng##*/})" || bad "$label engine not found in agent_identities.json"
  if [ -z "$principal" ]; then bad "$label agent identity (principal) missing"; return; fi
  ok "$label AGENT IDENTITY present"

  # 1) can it call Vertex at all? (the project roles grant_agent_access.sh adds)
  if _project_policy | jq -e --arg m "$principal" \
       '.bindings[]? | select(.role=="roles/aiplatform.user") | .members[]? | select(.==$m)' >/dev/null 2>&1; then
    ok "$label has its project roles"
  else
    bad "$label has NO project IAM — run ./deploy/grant_agent_access.sh ${disp#vibeflix-}"
  fi

  # 2) can it reach the IAM-gated MCP servers? (impersonation of the shared invoker SA)
  sa="${MCP_INVOKER_SA:-vibeflix-mcp-invoker@$PROJECT.iam.gserviceaccount.com}"
  if gcloud iam service-accounts get-iam-policy "$sa" --project="$PROJECT" --format=json 2>/dev/null \
       | jq -e --arg m "$principal" \
         '.bindings[]? | select(.role=="roles/iam.serviceAccountTokenCreator") | .members[]? | select(.==$m)' >/dev/null 2>&1; then
    ok "$label may impersonate the MCP invoker SA"
  else
    bad "$label cannot reach the MCP servers — run ./deploy/grant_agent_access.sh ${disp#vibeflix-}"
  fi
}

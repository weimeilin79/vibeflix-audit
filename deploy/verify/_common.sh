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

# check_agent <display-name> <label> — assert an agent engine is deployed WITH an agent identity.
check_agent() {
  local disp="$1" label="$2" ids="$ROOT/deploy/agent_identities.json" eng principal
  if [ ! -f "$ids" ]; then bad "$label: deploy/agent_identities.json missing — deploy an agent first"; return; fi
  eng=$(jq -r --arg k "$disp" '.[$k].engine // empty' "$ids")
  principal=$(jq -r --arg k "$disp" '.[$k].principal // empty' "$ids")
  [ -n "$eng" ] && ok "$label engine deployed (…/${eng##*/})" || bad "$label engine not found in agent_identities.json"
  [ -n "$principal" ] && ok "$label AGENT IDENTITY present" || bad "$label agent identity (principal) missing"
}

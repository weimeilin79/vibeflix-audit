#!/usr/bin/env bash
# Verify workshop Step 4 — vendor_clearance + legal deployed with agent identities.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 4: vendor_clearance + legal ──"
check_agent vibeflix-legal "legal"
check_agent vibeflix-vendor-clearance "vendor_clearance"

# ── legal's RAG wiring — the part unique to this step ────────────────────────
# Checked here because a legal agent with no corpus does NOT look broken: it falls back to
# keyword search over the local files and keeps answering, just worse (see legal_kb.py).
# The usual cause is deploying legal BEFORE setup_legal_rag.sh wrote RAG_CORPUS into
# deploy/.env, so the local config is right while the deployed engine has nothing.
TOKEN="$(gcloud auth print-access-token 2>/dev/null)"
if [ -z "${RAG_CORPUS:-}" ]; then
  bad "RAG_CORPUS not set in deploy/.env — run ./deploy/setup_legal_rag.sh"
else
  ok "RAG_CORPUS set (…/${RAG_CORPUS##*/})"

  CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
         "https://$REGION-aiplatform.googleapis.com/v1beta1/$RAG_CORPUS" 2>/dev/null || echo 000)
  [ "$CODE" = "200" ] && ok "RAG corpus exists in $PROJECT" \
    || bad "RAG corpus not found (HTTP $CODE) — re-run ./deploy/setup_legal_rag.sh"

  ENG=$(jq -r '.["vibeflix-legal"].engine // empty' "$ROOT/deploy/agent_identities.json" 2>/dev/null)
  if [ -n "$ENG" ]; then
    DEPLOYED=$(curl -s -H "Authorization: Bearer $TOKEN" \
      "https://$REGION-aiplatform.googleapis.com/v1beta1/$ENG" 2>/dev/null \
      | jq -r '[.spec.deploymentSpec.env[]? | select(.name=="RAG_CORPUS") | .value] | first // empty')
    if [ -z "$DEPLOYED" ]; then
      bad "the DEPLOYED legal engine has no RAG_CORPUS — it will silently use keyword search;
     add it to deploy/.env, then: python deploy/deploy_agents_a2a.py legal"
    elif [ "$DEPLOYED" != "$RAG_CORPUS" ]; then
      bad "deployed legal points at a DIFFERENT corpus (…/${DEPLOYED##*/}) — redeploy legal"
    else
      ok "deployed legal engine carries RAG_CORPUS"
    fi
  fi
fi

finish "Step 4"

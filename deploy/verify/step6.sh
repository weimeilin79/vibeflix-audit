#!/usr/bin/env bash
# Verify workshop Step 6 — the app (frontend + shared task store) is deployed and pinned 1/1.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 6: app (frontend + shared task store) ──"
URL=$(gcloud run services describe vibeflix-app --region="$REGION" --project="$PROJECT" \
      --format='value(status.url)' 2>/dev/null || true)
if [ -z "$URL" ]; then
  bad "vibeflix-app not deployed — build + deploy the app first"
else
  ok "vibeflix-app deployed ($URL)"
  SCALE=$(gcloud run services describe vibeflix-app --region="$REGION" --project="$PROJECT" --format=json 2>/dev/null \
    | python3 -c "import json,sys;a=json.load(sys.stdin)['spec']['template']['metadata']['annotations'];print(a.get('autoscaling.knative.dev/minScale','?'),a.get('autoscaling.knative.dev/maxScale','?'))" 2>/dev/null || echo "? ?")
  [ "$SCALE" = "1 1" ] && ok "pinned to a single instance (min=max=1) — the task store needs this" \
    || bad "app scale is '$SCALE' (want '1 1') — a 2nd instance split-brains the task store"
fi
check_agent vibeflix-orchestrator "orchestrator"

# ── every engine must carry TASK_STORE_URL ───────────────────────────────────
# Without it an engine silently falls back to a per-replica, in-memory task store, and A2A
# polls 404 whenever the load balancer picks a different replica than the one holding the task
# (measured: 86.8%). The engines get this at DEPLOY time — from the app's live URL, or from its
# deterministic https://vibeflix-app-<project-number>.<region>.run.app form when the app isn't
# up yet — so an engine deployed before that logic existed still has it empty.
TOKEN="$(gcloud auth print-access-token 2>/dev/null)"
IDS="$ROOT/deploy/agent_identities.json"
MISSING=""
for A in brand-style deal-pricing legal vendor-clearance ui-renderer orchestrator; do
  ENG=$(jq -r --arg k "vibeflix-$A" '.[$k].engine // empty' "$IDS" 2>/dev/null)
  [ -n "$ENG" ] || continue
  TS=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "https://$REGION-aiplatform.googleapis.com/v1beta1/$ENG" 2>/dev/null \
       | jq -r '[.spec.deploymentSpec.env[]? | select(.name=="TASK_STORE_URL") | .value] | first // empty')
  [ -n "$TS" ] || MISSING="$MISSING $A"
done
if [ -n "$MISSING" ]; then
  bad "no TASK_STORE_URL on:$MISSING — they will use a per-replica store and 404 their own polls.
     Fix: python deploy/deploy_agents_a2a.py   (no arg = all six)"
else
  ok "all engines carry TASK_STORE_URL (shared task store)"
fi

finish "Step 6"

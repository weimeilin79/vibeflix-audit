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
finish "Step 6"

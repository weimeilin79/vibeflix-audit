#!/usr/bin/env bash
# Layer 3: app → ui_renderer (presenter). Grant if gateway-routed + probe via a full audit.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; D="$DIR/diag.sh"
if [ -z "${PROJECT:-}" ]; then
  echo "✗ PROJECT is not set. Refusing to guess." >&2
  echo "  This used to default to a hardcoded project — so forgetting to export PROJECT" >&2
  echo "  silently deployed to (or read from) SOMEONE ELSE'S project." >&2
  echo "  Run:  export PROJECT=<your-project> REGION=<your-region>" >&2
  exit 1
fi
export PROJECT="${PROJECT}" REGION="${REGION:-us-central1}"
APP_SA="serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com"
APP_URL=$(gcloud run services describe vibeflix-app --region $REGION --format 'value(status.url)')
echo "═══ 3a: grant app → ui_renderer ═══"; "$D" grant_a2a "$APP_SA" vibeflix-ui-renderer
echo "═══ 3b: audit through app; check presenter ═══"
curl -s -X POST $APP_URL/api/audit -H 'Content-Type: application/json' \
  -d '{"image_uri":"gs://vibeflix-request-image/0aa7dd74-vendor_request_refine.png","target_market":"Asia-Pacific","volume":1000,"character":"grogu","product_category":"Vinyl Figures","vendor":"VND-1001","medium":"vinyl figures","net_unit_price":15,"agreed_royalty_rate":0.18,"agreed_advance":88000,"agreed_mg":1500000}' \
  --max-time 250 | python3 -c "import json,sys;d=json.load(sys.stdin);print('status',d.get('status'))"
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="vibeflix-app"' --project $PROJECT --limit 20 --format 'value(textPayload)' --freshness 4m 2>/dev/null | grep -iE "presenter|panels|401|403" | head -6

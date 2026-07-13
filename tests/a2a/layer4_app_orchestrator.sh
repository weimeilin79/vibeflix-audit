#!/usr/bin/env bash
# Layer 4: app → orchestrator ENGINE (needs the runner→remote code switch first).
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; D="$DIR/diag.sh"
export PROJECT="${PROJECT:-pokedemo-test}" REGION="${REGION:-us-central1}"
APP_SA="serviceAccount:vibeflix-app@$PROJECT.iam.gserviceaccount.com"
echo "═══ 4b: grant app → orchestrator ═══"; "$D" grant_a2a "$APP_SA" vibeflix-orchestrator
echo "NOTE: 4a (code: app calls orchestrator engine) must be deployed first."
APP_URL=$(gcloud run services describe vibeflix-app --region $REGION --format 'value(status.url)')
echo "═══ 4c: full end-to-end audit ═══"
curl -s -X POST $APP_URL/api/audit -H 'Content-Type: application/json' \
  -d '{"image_uri":"gs://vibeflix-request-image/0aa7dd74-vendor_request_refine.png","target_market":"Asia-Pacific","volume":1000,"character":"grogu","product_category":"Vinyl Figures","vendor":"VND-1001","medium":"vinyl figures","net_unit_price":15,"agreed_royalty_rate":0.18,"agreed_advance":88000,"agreed_mg":1500000}' \
  --max-time 280 | python3 -c "import json,sys;d=json.load(sys.stdin);a=d.get('result') or {};print('status',d.get('status'),'reports',{k:(v or {}).get('status') for k,v in (a.get('reports') or {}).items()},'contract',(a.get('contract') or {}).get('contract_id'))"

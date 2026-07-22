#!/usr/bin/env bash
# setup_app_iam.sh — the console app's service account + IAM + telemetry subscription.
# A Step-6 prerequisite (deploy_app.sh runs the app AS this SA). Idempotent; mirrors the app
# resources in deploy/terraform/agents without Terraform (so no org_id is needed).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"; REGION="${REGION:-us-central1}"
APP_SA="vibeflix-app@$PROJECT.iam.gserviceaccount.com"
TOPIC="${PUBSUB_TOPIC:-vibeflix-mesh-events}"; SUB="$TOPIC-app-cloud"
REQ_BUCKET="${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image}"

echo "[app-iam] service account $APP_SA"
gcloud iam service-accounts describe "$APP_SA" --project="$PROJECT" >/dev/null 2>&1 \
  || gcloud iam service-accounts create vibeflix-app --project="$PROJECT" --display-name "Vibeflix console app"

# Project roles. agentContextEditor is the one people forget: the app reads/writes A2A task
# state on the agents' context surface — without it every GET /a2a/v1/tasks/{id} 401s and hangs.
for R in roles/aiplatform.user roles/aiplatform.agentContextEditor roles/aiplatform.agentDefaultAccess \
         roles/datastore.user roles/agentregistry.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$APP_SA" --role="$R" --condition=None -q >/dev/null
done

# GCS: the app writes uploaded mock-ups and cleans them up on reset.
gcloud storage buckets add-iam-policy-binding "gs://$REQ_BUCKET" \
  --member="serviceAccount:$APP_SA" --role=roles/storage.objectAdmin >/dev/null 2>&1 \
  || echo "  (bucket gs://$REQ_BUCKET grant skipped — create it in Step 1 setup)"

# Pub/Sub: the app publishes app-side events and is the single mesh-telemetry consumer.
gcloud pubsub topics add-iam-policy-binding "$TOPIC" --project="$PROJECT" \
  --member="serviceAccount:$APP_SA" --role=roles/pubsub.publisher >/dev/null
gcloud pubsub subscriptions describe "$SUB" --project="$PROJECT" >/dev/null 2>&1 \
  || gcloud pubsub subscriptions create "$SUB" --topic="$TOPIC" --project="$PROJECT" \
       --ack-deadline=10 --message-retention-duration=10m --expiration-period=never
gcloud pubsub subscriptions add-iam-policy-binding "$SUB" --project="$PROJECT" \
  --member="serviceAccount:$APP_SA" --role=roles/pubsub.subscriber >/dev/null

echo "[app-iam] done — app SA ready, telemetry subscription '$SUB' present."

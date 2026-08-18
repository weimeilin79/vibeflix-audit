#!/usr/bin/env bash
# Verify workshop Step 1 — foundations + the 3 MCP servers are up and IAM-gated.
set -uo pipefail
. "$(dirname "$0")/_common.sh"

echo "── Verify Step 1: foundations + 3 MCP servers ──"
TOPIC="${PUBSUB_TOPIC:-vibeflix-mesh-events}"
DB="${FIRESTORE_DATABASE:-vibeflix-registry}"

gcloud artifacts repositories describe vibeflix --location="$REGION" --project="$PROJECT" >/dev/null 2>&1 \
  && ok "Artifact Registry repo 'vibeflix'" || bad "Artifact Registry repo 'vibeflix' not found"

gcloud pubsub topics describe "$TOPIC" --project="$PROJECT" >/dev/null 2>&1 \
  && ok "Pub/Sub topic '$TOPIC'" || bad "Pub/Sub topic '$TOPIC' not found"

gcloud firestore databases describe --database="$DB" --project="$PROJECT" >/dev/null 2>&1 \
  && ok "Firestore database '$DB'" || bad "Firestore database '$DB' not found"

for s in vibeflix-mcp-brand-style vibeflix-mcp-licensing vibeflix-mcp-market; do
  URL=$(gcloud run services describe "$s" --region="$REGION" --project="$PROJECT" \
        --format='value(status.url)' 2>/dev/null || true)
  if [ -z "$URL" ]; then bad "$s not deployed"; continue; fi
  CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/mcp" || echo "000")
  if [ "$CODE" = "403" ]; then ok "$s up + IAM-gated (anonymous → 403)"
  else bad "$s up but anonymous POST → $CODE (expected 403 — is it public?)"; fi
done

for S in licensing market brand-style; do
  gcloud alpha agent-registry services describe "vibeflix-mcp-$S" \
    --location="$REGION" --project="$PROJECT" >/dev/null 2>&1 \
    && ok "vibeflix-mcp-$S registered in the Agent Registry" \
    || bad "vibeflix-mcp-$S not registered — re-run ./workshop/setup.sh (step 9/9 registers them)"
done

finish "Step 1"

#!/usr/bin/env bash
#
# enable_otel.sh — turn on OpenTelemetry observability for EVERY vibeflix engine
# on Agent Runtime (Cloud Trace + the console's Observability panel).
#
# New deploys get this from deploy_agents.sh's `--otel_to_cloud`; this script
# retrofits ALREADY-DEPLOYED engines by patching their deployment env:
#   GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true
#   ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=true   (full prompt/response in spans —
#                                                demo-friendly; set false for privacy)
# Usage:  PROJECT=… REGION=… ./deploy/enable_otel.sh
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?}"; REGION="${REGION:-us-central1}"
TOK=$(gcloud auth print-access-token)
API="https://$REGION-aiplatform.googleapis.com/v1beta1"
PN=$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')

curl -s -H "Authorization: Bearer $TOK" \
  "$API/projects/$PN/locations/$REGION/reasoningEngines" \
  | jq -r '.reasoningEngines[] | select(.displayName // "" | startswith("vibeflix-")) | .name' \
  | while read -r E; do
    echo "── $E"
    curl -s -H "Authorization: Bearer $TOK" "$API/$E" \
      | jq '{spec: {deploymentSpec: {env: ((.spec.deploymentSpec.env // [])
          | map(select(.name != "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"
                       and .name != "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"))
          + [{"name":"GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY","value":"true"},
             {"name":"ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS","value":"true"}])}}}' \
      > /tmp/otel_patch.json
    curl -s -X PATCH -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
      "$API/$E?updateMask=spec.deployment_spec.env" -d @/tmp/otel_patch.json \
      | jq -r 'if .error then "   ⚠️ " + .error.message else "   telemetry env patched (done=" + (.done|tostring) + ")" end'
  done
echo "[enable_otel] done — traces land in Cloud Trace; console Observability panel activates per engine."

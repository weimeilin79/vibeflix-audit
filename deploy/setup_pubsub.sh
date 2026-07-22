#!/usr/bin/env bash
#
# setup_pubsub.sh — provision the Pub/Sub backbone for LIVE mesh telemetry.
#
# Purpose: agents, MCP servers, and app functions EMIT fine-grained events
# (started / tool_call / needs_input / completed …) onto one topic; the app
# subscribes and relays them to the console, so the Workflow graph lights up
# from REAL signals as the mesh works — not just from the SSE report stream.
#
#   emitters (agents · MCPs · app fns) ──publish──► topic ──pull──► app ──SSE/WS──► graph
#
# The topic (vibeflix-mesh-events) is owned by terraform/foundations — apply that FIRST.
# Creates:
#   1. subscription   vibeflix-mesh-events-app   (pull; the app's live bridge)
#      - ack deadline 10s, retention 10m, never expires — UI telemetry is
#        ephemeral: late events are useless, so nothing needs to be durable.
#   3. smoke test     publish one event, pull it back (via gcloud)
#
# EVENT SCHEMA (the contract emitters and the UI bridge agree on):
#   data (JSON): {
#     "run_id":  "<audit order/run id — lets the UI scope events to a run>",
#     "source":  "orchestrator|brand_style|vendor_clearance|deal_pricing|legal|ui_renderer|mcp_licensing|mcp_brand_style|mcp_market|app",
#     "node":    "<graph node id the event belongs to (matches the Workflow graph)>",
#     "tool":    "<MCP tool name when the event is a tool invocation, else empty>",
#     "event":   "started|tool_call|needs_input|completed|failed|handoff",
#     "status":  "<optional node status: running|cleared|blocked|flagged|...>",
#     "detail":  "<short human-readable line for the UI, e.g. 'get_vendor(VND-1001)'>",
#     "ts":      <epoch millis>
#   }
#   attributes: source=<source>, event=<event>   (for server-side filtering)
#
# Config comes from deploy/.env (PROJECT; PUBSUB_TOPIC / PUBSUB_SUBSCRIPTION
# override the defaults), same as the other deploy scripts.
#
# Usage:
#   ./deploy/setup_pubsub.sh
#   PROJECT=my-proj PUBSUB_TOPIC=my-topic ./deploy/setup_pubsub.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_FILE="$HERE/.env"
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi
PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
TOPIC="${PUBSUB_TOPIC:-vibeflix-mesh-events}"
SUBSCRIPTION="${PUBSUB_SUBSCRIPTION:-${TOPIC}-app}"
[ -n "$PROJECT" ] || { echo "ERROR: PROJECT not set — add PROJECT=... to deploy/.env" >&2; exit 1; }

echo "[setup_pubsub] project=$PROJECT topic=$TOPIC subscription=$SUBSCRIPTION"
gcloud config set project "$PROJECT" >/dev/null

echo "[setup_pubsub] 1/4 enabling the Pub/Sub API…"
gcloud services enable pubsub.googleapis.com

echo "[setup_pubsub] 2/4 verifying topic '$TOPIC' (owned by terraform/foundations)…"
# The topic is created declaratively by terraform/foundations now — this script only owns the
# local bridge subscription + smoke test. Assert the topic exists rather than creating it.
gcloud pubsub topics describe "$TOPIC" --project "$PROJECT" >/dev/null 2>&1 || {
  echo "ERROR: topic '$TOPIC' not found — apply deploy/terraform/foundations first (it owns the topic)." >&2
  exit 1
}

echo "[setup_pubsub] 3/4 creating pull subscription '$SUBSCRIPTION'…"
# UI telemetry is ephemeral: short retention, no expiry (the app reconnects at will).
gcloud pubsub subscriptions create "$SUBSCRIPTION" \
  --topic "$TOPIC" --project "$PROJECT" \
  --ack-deadline 10 \
  --message-retention-duration 10m \
  --expiration-period never \
  || echo "   (subscription may already exist — continuing)"

echo "[setup_pubsub] 4/4 smoke test: publish → pull…"
gcloud pubsub topics publish "$TOPIC" --project "$PROJECT" \
  --attribute "source=setup,event=smoke" \
  --message '{"run_id":"setup-probe","source":"setup","node":"orchestrator","event":"completed","detail":"setup_pubsub smoke test","ts":0}' >/dev/null
sleep 3
# Newer gcloud prints message.data already DECODED; older versions print base64.
RAW="$(gcloud pubsub subscriptions pull "$SUBSCRIPTION" --project "$PROJECT" --auto-ack --limit 5 --format 'value(message.data)' || true)"
DECODED="$(echo "$RAW" | base64 -d 2>/dev/null || true)"
if echo "$RAW $DECODED" | grep -q "setup_pubsub smoke test"; then
  echo "   publish/pull OK"
else
  echo "   WARNING: smoke-test message not pulled back (may just be timing — re-run step 4 manually):"
  echo "   gcloud pubsub subscriptions pull $SUBSCRIPTION --auto-ack --limit 5"
fi

echo "[setup_pubsub] done."
echo
echo "Env contract for the mesh (compose/Cloud Run):"
echo "  PUBSUB_TOPIC=$TOPIC              # emitters (agents, MCP servers, app functions)"
echo "  PUBSUB_SUBSCRIPTION=$SUBSCRIPTION  # the app's live-graph bridge (pull)"
echo
echo "IAM (only needed when NOT running on your ADC user):"
echo "  emitters:  roles/pubsub.publisher   on projects/$PROJECT/topics/$TOPIC"
echo "  app:       roles/pubsub.subscriber  on projects/$PROJECT/subscriptions/$SUBSCRIPTION"
echo
echo "Next steps (not done by this script):"
echo "  • vibeflix-common: a small emit_event() helper (google-cloud-pubsub) for agents/MCPs"
echo "  • app: streaming-pull bridge → relay events onto the console's SSE/graph channel"
echo "  • frontend: Workflow graph consumes the events (same node ids, richer states)"

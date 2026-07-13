#!/usr/bin/env bash
#
# run_layers.sh — exercise the 4 mesh layers and VERIFY each from the backend's logs.
#
#   ./tests/a2a/run_layers.sh            # all layers
#   ./tests/a2a/run_layers.sh 1          # just layer 1
#   ./tests/a2a/run_layers.sh 2 3        # layers 2 and 3
#
# ⚠️ NEVER judge a layer by the agent's own reply. An agent whose toolset failed
# still emits a confident, clean verdict — we watched brand_style report
# status:"success", findings:[] with a plausible checks_run list while the MCP had
# ZERO CallToolRequest (the model invented the check names; they changed run to
# run). The pass criterion is always the BACKEND's log:
#     MCP layer  → CallToolRequest in the MCP's Cloud Run log
#     A2A layer  → the callee engine's log shows it ran
#
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
PROJECT="${PROJECT:-pokedemo-test}"; REGION="${REGION:-us-central1}"
PY="$ROOT/.venv/bin/python"
IDENT="$ROOT/deploy/agent_identities.json"
eng() { jq -r --arg k "vibeflix-$1" '.[$k].engine' "$IDENT" | sed 's#.*/##'; }
BASE="https://$REGION-aiplatform.googleapis.com/v1beta1/projects/789872749985/locations/$REGION/reasoningEngines"

send() {  # send <engine_id> <brief>   → prints the agent's reply (truncated)
  GOOGLE_CLOUD_PROJECT=$PROJECT "$PY" - "$1" "$2" <<'PYEOF'
import sys, asyncio, pathlib
sys.path.insert(0, str(pathlib.Path.cwd() / "packages/vibeflix-common"))
from vibeflix_common.a2a_engine import a2a_engine_send
base = ("https://us-central1-aiplatform.googleapis.com/v1beta1/projects/789872749985"
        f"/locations/us-central1/reasoningEngines/{sys.argv[1]}")
# 1800s. The full chain (brand + vendor ↔ legal Q&A round-trip + deal) runs well past the
# old 560s deadline; _extract_reply then returns "" on an unfinished task and the layer
# looks failed even though the work COMPLETED server-side (legal's own log showed 5 model
# calls while our client had already given up). An empty reply here means "still running",
# not "broken" — check the callee's log before believing a failure.
print(asyncio.run(a2a_engine_send(base, sys.argv[2], timeout=1800))[:400].replace("\n", " "))
PYEOF
}

calltools() {  # calltools <cloud-run-service> <since>  → count of CallToolRequest
  gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$1\" AND timestamp>=\"$2\"" \
    --project="$PROJECT" --limit=400 --format='value(textPayload,jsonPayload.message)' 2>/dev/null \
    | grep -oic 'CallToolRequest' || echo 0
}

engine_ran() {  # engine_ran <engine_id> <since> → lines showing the model actually ran
  gcloud logging read "resource.type=\"aiplatform.googleapis.com/ReasoningEngine\" AND resource.labels.reasoning_engine_id=\"$1\" AND timestamp>=\"$2\"" \
    --project="$PROJECT" --limit=300 --format='value(textPayload)' 2>/dev/null \
    | grep -ci 'Sending out request, model' || echo 0
}

mcp_401s() {  # any 401 back from an MCP (the intermittent issue — see README)
  gcloud logging read "resource.type=\"aiplatform.googleapis.com/ReasoningEngine\" AND resource.labels.reasoning_engine_id=\"$1\" AND timestamp>=\"$2\"" \
    --project="$PROJECT" --limit=300 --format='value(textPayload)' 2>/dev/null \
    | grep -c '401 Unauthorized' || echo 0
}

layer1() {
  echo "══ LAYER 1 — every agent → its MCP server"
  local T; T=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  echo "  brand_style      → $(send "$(eng brand-style)" 'Run the brand compliance audit. image: gs://vibeflix-request-image/84d5370c-vendor_request_refine.png ; character: grogu ; medium: vinyl figures')"
  echo "  vendor_clearance → $(send "$(eng vendor-clearance)" 'Clear vendor VND-1001 for character grogu, territory Asia-Pacific, product category Vinyl Figures.')"
  echo "  deal_pricing     → $(send "$(eng deal-pricing)" 'Price check: character grogu, category Vinyl Figures, volume 50000, net unit price 12.5, agreed royalty 0.12, advance 50000, MG 100000.')"
  echo "  ── proof (CallToolRequest on each MCP; 0 = the verdict was FABRICATED):"
  for S in vibeflix-mcp-brand-style vibeflix-mcp-licensing vibeflix-mcp-market; do
    printf "     %-28s %s\n" "$S" "$(calltools "$S" "$T")"
  done
  printf "     %-28s %s  (see README: intermittent, retried)\n" "engine 401s (brand_style)" "$(mcp_401s "$(eng brand-style)" "$T")"
}

layer2() {
  echo "══ LAYER 2 — vendor_clearance → legal (private A2A hand-off)"
  local T; T=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  # The legal hand-off fires ONLY when a category is actually ONBOARDED (the
  # update_vendor fact) — clearing an already-eligible vendor/category correctly
  # skips legal. So force an onboarding: a category the vendor doesn't yet carry.
  # …and the onboarding itself needs explicit approval (needs: add_category_approved),
  # so grant it up front or the agent stops at needs_input and never reaches legal.
  # Phrase the brief in the reasoner's own state vocabulary (vendor / character_id /
  # target_market / product_category / add_category_approved). Prose confuses it: it
  # has no output_schema, so a chatty brief makes it emit free-form keys and the graph
  # never sees a `legal_request` → the legal node is skipped.
  #
  # ⚠️ Legal is only consulted when a VENDOR IS ONBOARDED — i.e. a vendor that is NOT
  # already in the licensing registry. Reusing an existing vendor (VND-1001) makes the
  # agent correctly find it eligible, onboard nothing, emit no `legal_request`, and skip
  # the legal node — which looks like a broken hand-off but is the agent behaving right.
  # This test MUTATES the registry, so the vendor name must be NEW on every run.
  local NEWVENDOR="Kessel Run Collectibles $(date -u +%H%M%S)"
  echo "  onboarding NEW vendor: $NEWVENDOR"
  # Use the EXACT brief shape the orchestrator sends in production
  # (orchestrator/agent.py::_build_brief): prose + "Additional operator-provided
  # inputs: k=v; k=v.". The reasoner has no output_schema, so an invented brief
  # format makes it emit free-form keys and the graph never sees `legal_request`.
  echo "  vendor_clearance → $(send "$(eng vendor-clearance)" "Audit the 'grogu' mockup at gs://vibeflix-request-image/84d5370c-vendor_request_refine.png for the Asia-Pacific market at a production volume of 50000 units. Additional operator-provided inputs: vendor=$NEWVENDOR; new_vendor=$NEWVENDOR — a new manufacturer in Taiwan, contact ops@kesselrun.example, specialises in vinyl figures; product_category=Vinyl Figures; add_category_approved=yes.")"
  echo "  ── proof: did the LEGAL engine actually run? (model invocations)"
  printf "     legal engine model calls: %s   (0 = no hand-off happened)\n" "$(engine_ran "$(eng legal)" "$T")"
}

layer3() {
  echo "══ LAYER 3 — orchestrator → brand/vendor/deal (A2A fan-out)"
  local T; T=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  # Send the JSON payload the app sends (orchestrator/_parse_audit_request accepts JSON
  # or natural language). JSON is the real contract: it populates the SESSION STATE
  # ({vendor?}, {add_category_approved?}, …) that the domain agents template on. Driving
  # vendor_clearance with raw prose over A2A is unreliable — its clearance reasoner has no
  # output_schema, so it free-styles the JSON shape and the graph never sees `legal_request`
  # (⇒ the legal hand-off silently never fires). The hand-off is exercised properly HERE.
  # A BRAND-NEW vendor every run — that (not a new category) is what triggers onboarding,
  # hence the vendor→legal hand-off. An existing vendor is simply cleared and legal never runs.
  local NEWVENDOR="Kessel Run Collectibles $(date -u +%H%M%S)"
  local PAYLOAD
  PAYLOAD=$(cat <<JSON
{"image_uri":"gs://vibeflix-request-image/84d5370c-vendor_request_refine.png",
 "target_market":"Asia-Pacific","volume":50000,"character":"grogu",
 "product_category":"Vinyl Figures","vendor":"$NEWVENDOR",
 "new_vendor":"$NEWVENDOR — new manufacturer in Taiwan, contact ops@kesselrun.example, specialises in vinyl figures",
 "add_category_approved":"yes",
 "medium":"vinyl figures","net_unit_price":12.5,"agreed_royalty_rate":0.12,
 "agreed_advance":50000,"agreed_mg":100000}
JSON
)
  echo "  onboarding NEW vendor: $NEWVENDOR (this is what forces the vendor→legal hand-off)"
  echo "  orchestrator → $(send "$(eng orchestrator)" "$PAYLOAD")"
  echo "  ── proof: each downstream engine actually ran (legal = the layer-2 hand-off)"
  for A in brand-style vendor-clearance deal-pricing legal; do
    printf "     %-18s model calls: %s\n" "$A" "$(engine_ran "$(eng "$A")" "$T")"
  done
}

layer4() {
  echo "══ LAYER 4 — app → orchestrator ENGINE → domain engines, + app → ui_renderer"
  echo "   The app is a THIN CLIENT: it calls the orchestrator over A2A (like ui_renderer)."
  echo "   It does NOT import root_agent and run the workflow in-process any more."
  local T; T=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  local APP; APP=$(gcloud run services describe vibeflix-app --region "$REGION" --project "$PROJECT" --format 'value(status.url)' 2>/dev/null)
  echo "  app: $APP"
  echo "  /api/ready → $(curl -s -m 60 -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$APP/api/ready" \
        | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ready="+str(d.get("ready")), "|", ", ".join(f"{c[\"name\"]}={c.get(\"ok\")}" for c in d.get("components",[])))' 2>/dev/null)"

  # A brand-new vendor so the run also exercises onboarding → the vendor→legal hand-off.
  local NEWVENDOR="Kessel Run Collectibles $(date -u +%H%M%S)"
  echo "  onboarding NEW vendor: $NEWVENDOR"
  local PAYLOAD
  PAYLOAD=$(cat <<JSON
{"image_uri":"gs://vibeflix-request-image/84d5370c-vendor_request_refine.png",
 "target_market":"Asia-Pacific","volume":50000,"character":"grogu",
 "product_category":"Vinyl Figures","vendor":"$NEWVENDOR",
 "new_vendor":"$NEWVENDOR — new manufacturer in Taiwan, contact ops@kesselrun.example, specialises in vinyl figures",
 "add_category_approved":"yes","medium":"vinyl figures","net_unit_price":12.5,
 "agreed_royalty_rate":0.12,"agreed_advance":50000,"agreed_mg":100000}
JSON
)
  echo "  POST /api/audit …"
  curl -s --max-time 1800 -X POST "$APP/api/audit" \
    -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    -H 'Content-Type: application/json' -d "$PAYLOAD" | head -c 200
  echo; echo

  echo "  ── proof (the BACKEND's logs, never the app's reply):"
  # ★ THE decisive check. The orchestrator engine sat deployed and IDLE for weeks —
  #   0 inbound calls — because the app ran the workflow in-process. A non-zero count
  #   here is what proves the orchestrator is a REAL independent agent: its own identity,
  #   its own gateway-governed egress, its own traces.
  local ORCH; ORCH="$(engine_ran "$(eng orchestrator)" "$T")"
  printf "     %-22s %s   %s\n" "★ orchestrator engine" "$ORCH" \
    "$([ "${ORCH:-0}" -gt 0 ] && echo '← app IS a thin client' || echo '← ✗ STILL running in-process!')"
  for A in brand-style vendor-clearance deal-pricing legal ui-renderer; do
    printf "     %-22s %s\n" "$A" "$(engine_ran "$(eng "$A")" "$T")"
  done
  echo "     ── MCP tools actually executed (0 ⇒ the verdicts were FABRICATED):"
  for S in vibeflix-mcp-brand-style vibeflix-mcp-licensing vibeflix-mcp-market; do
    printf "     %-28s CallToolRequest: %s\n" "$S" "$(calltools "$S" "$T")"
  done
  echo "     ── mesh telemetry (drives the console's graph + tool LEDs):"
  local EV; EV=$(gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"vibeflix-app\" AND timestamp>=\"$T\"" \
        --project="$PROJECT" --limit=300 --format='value(textPayload)' 2>/dev/null | grep -c '^\[mesh\]' || echo 0)
  printf "     %-28s %s  (0 ⇒ LEDs/graph stay dark — check the Pub/Sub bridge)\n" "[mesh] events received" "$EV"
}

cd "$ROOT"
LAYERS=("$@"); [ ${#LAYERS[@]} -eq 0 ] && LAYERS=(1 2 3 4)
for L in "${LAYERS[@]}"; do "layer$L"; echo; done

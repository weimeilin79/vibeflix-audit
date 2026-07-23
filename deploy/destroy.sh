#!/usr/bin/env bash
# destroy.sh — tear down EVERYTHING the workshop created. DESTRUCTIVE and IRREVERSIBLE.
# Run it only when you are completely finished. Reads deploy/.env for PROJECT / REGION.
#
#   ./deploy/destroy.sh              # delete the workshop's resources, keep the project
#   ./deploy/destroy.sh --project    # delete the WHOLE project (fastest + cleanest)
#
# Best-effort: already-gone resources are skipped (|| true), so it's safe to re-run.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
# DESTROY_PROJECT wins over .env, so you can target a DIFFERENT project than your working config
# without editing .env — destroying the wrong project is not a mistake you want to be one typo from.
PROJECT="${DESTROY_PROJECT:-${PROJECT:?set PROJECT in deploy/.env (or pass DESTROY_PROJECT=…)}}"
REGION="${REGION:-us-central1}"
TOPIC="${PUBSUB_TOPIC:-vibeflix-mesh-events}"; DB="${FIRESTORE_DATABASE:-vibeflix-registry}"
REQ_BUCKET="${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image}"
ASSET_BUCKET="${APPROVED_ASSETS_BUCKET:-$PROJECT-approved-assets}"

echo "⚠️  This DELETES workshop resources in project '$PROJECT'. This CANNOT be undone."
[ "${1:-}" = "--project" ] && echo "    Mode: DELETE THE ENTIRE PROJECT."
printf "Type the project id (%s) to confirm: " "$PROJECT"; read -r CONFIRM
[ "$CONFIRM" = "$PROJECT" ] || { echo "Aborted — nothing deleted."; exit 1; }

# ── Fast path: nuke the whole project ────────────────────────────────────────
if [ "${1:-}" = "--project" ]; then
  echo "Deleting project '$PROJECT'…"
  gcloud projects delete "$PROJECT" --quiet
  echo "✅ Project scheduled for deletion."
  exit 0
fi

# ── Resource-by-resource (keep the project) ──────────────────────────────────
echo "▶ Agent Runtime engines (the 6 agents)"
"$ROOT/.venv/bin/python" - <<'PY' || true
import os, vertexai
c = vertexai.Client(project=os.environ["PROJECT"], location=os.environ["REGION"])
for e in c.agent_engines.list():
    r = e.api_resource
    if (r.display_name or "").startswith("vibeflix-"):
        print("   deleting", r.display_name)
        try: c.agent_engines.delete(name=r.name, force=True)
        except Exception as ex: print("   (skip)", type(ex).__name__, ex)
PY

echo "▶ Cloud Run: the app"
gcloud run services delete vibeflix-app --region "$REGION" --project "$PROJECT" --quiet 2>/dev/null || true

echo "▶ Agent Gateway + IAP policy + registry entries (Step 7)"
gcloud alpha network-services agent-gateways delete vibeflix-gateway --location "$REGION" --project "$PROJECT" --quiet 2>/dev/null || true
for a in brand-style vendor-clearance deal-pricing legal ui-renderer orchestrator; do
  gcloud alpha agent-registry services delete "vibeflix-$a-agent" --location "$REGION" --project "$PROJECT" --quiet 2>/dev/null || true
done
for m in licensing market brand-style; do
  gcloud alpha agent-registry services delete "vibeflix-mcp-$m" --location "$REGION" --project "$PROJECT" --quiet 2>/dev/null || true
done

echo "▶ Pub/Sub subscriptions"
gcloud pubsub subscriptions delete "$TOPIC-app-cloud"                --project "$PROJECT" --quiet 2>/dev/null || true
gcloud pubsub subscriptions delete "${PUBSUB_SUBSCRIPTION:-$TOPIC-app}" --project "$PROJECT" --quiet 2>/dev/null || true

echo "▶ Terraform-managed infra (MCP services + SAs, then foundations: AR repo + topic)"
terraform -chdir="$HERE/terraform/mcp" init -input=false >/dev/null 2>&1 || true
terraform -chdir="$HERE/terraform/mcp" destroy -auto-approve \
  -var project="$PROJECT" -var region="$REGION" -var deployer="user:$(gcloud config get-value account 2>/dev/null)" 2>/dev/null || true
terraform -chdir="$HERE/terraform/foundations" init -input=false >/dev/null 2>&1 || true
terraform -chdir="$HERE/terraform/foundations" destroy -auto-approve \
  -var project="$PROJECT" -var region="$REGION" -var pubsub_topic="$TOPIC" 2>/dev/null || true

echo "▶ GCS buckets"
for b in "$REQ_BUCKET" "$ASSET_BUCKET"; do
  gcloud storage rm -r "gs://$b" --project "$PROJECT" 2>/dev/null || true
done

echo "▶ Firestore database '$DB'"
gcloud firestore databases delete --database="$DB" --project "$PROJECT" --quiet 2>/dev/null \
  || echo "   (could not delete '$DB' automatically — remove it from the console if you want it gone)"

echo "▶ Service accounts (app + MCP invoker)"
for sa in vibeflix-app vibeflix-mcp-invoker; do
  gcloud iam service-accounts delete "$sa@$PROJECT.iam.gserviceaccount.com" --project "$PROJECT" --quiet 2>/dev/null || true
done

echo
echo "✅ Workshop resources deleted."
echo "   IAM bindings left on deleted principals are harmless leftovers; for a truly clean slate"
echo "   run:  ./deploy/destroy.sh --project"

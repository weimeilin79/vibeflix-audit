#!/usr/bin/env bash
#
# setup_memory.sh — provision the Vertex AI backends for persistence memory
# (Phase 1): a private GCS artifacts bucket + an (empty) Agent Engine instance
# that hosts the managed Sessions API and Memory Bank.
#
# NOTE: your agents do NOT run on Agent Engine. The instance is only the managed
# backend that VertexAiSessionService / VertexAiMemoryBankService talk to,
# scoped by the agent_engine_id this script prints at the end. Your agents keep
# running in the A2A mesh (local / Cloud Run).
#
# Usage:
#   PROJECT=pokedemo-test REGION=us-central1 BUCKET=vibeflix-artifacts \
#     ./deploy/setup_memory.sh
#
set -euo pipefail

PROJECT="${PROJECT:-pokedemo-test}"
# ⚠️ Agent Engine + Memory Bank need a REGION, not "global" (the Gemini location).
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-vibeflix-artifacts}"

echo "[setup_memory] project=$PROJECT region=$REGION bucket=$BUCKET"
gcloud config set project "$PROJECT" >/dev/null

echo "[setup_memory] 1/3 enabling APIs…"
gcloud services enable aiplatform.googleapis.com storage.googleapis.com

echo "[setup_memory] 2/3 creating private artifacts bucket…"
gcloud storage buckets create "gs://$BUCKET" \
  --project="$PROJECT" --location="$REGION" \
  --uniform-bucket-level-access --public-access-prevention \
  || echo "   (bucket may already exist — continuing)"

echo "[setup_memory] 3/3 creating Agent Engine instance (Sessions + Memory Bank)…"
# Agent Engine creation is a Vertex SDK call, not gcloud. Needs the SDK:
#   pip install "google-cloud-aiplatform[agent_engines]"
python - "$PROJECT" "$REGION" "$BUCKET" <<'PY'
import sys
project, region, bucket = sys.argv[1:4]
try:
    import vertexai
    from vertexai import agent_engines
except ImportError:
    sys.exit("Missing SDK. Run:  pip install 'google-cloud-aiplatform[agent_engines]'")

vertexai.init(project=project, location=region, staging_bucket=f"gs://{bucket}")
try:
    ae = agent_engines.create()          # empty instance = managed memory/session backend
except Exception as e:                     # SDK versions vary — fall back to REST (see README)
    sys.exit(f"agent_engines.create() failed: {e}\n"
             "Use the REST fallback in deploy/README.md if your SDK differs.")

rid = ae.resource_name.split("/")[-1]
print("\n=== Agent Engine created ===")
print("RESOURCE        :", ae.resource_name)
print("AGENT_ENGINE_ID :", rid)
print("\nAdd these to agents/orchestrator/.env (local) — or set as container env:")
print(f"  AGENT_ENGINE_ID={rid}")
print(f"  MEMORY_LOCATION={region}")
print(f"  ARTIFACTS_BUCKET={bucket}")
PY

echo "[setup_memory] done."
echo "[setup_memory] Grant the runtime service account roles/aiplatform.user"
echo "               and storage access on gs://$BUCKET if it isn't your ADC user."

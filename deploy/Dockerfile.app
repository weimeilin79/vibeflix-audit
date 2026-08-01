# Container 1: frontend (built static) + FastAPI proxy + Sourcing Orchestrator.
# The orchestrator is an A2A *client* — it calls the three agent services over A2A.
# Build context = repo root:  docker build -f deploy/Dockerfile.app .
# syntax=docker/dockerfile:1

# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS frontend
WORKDIR /build
# Build-time default mockup image, baked into the bundle by Vite (VITE_* env var). Empty ⇒
# the app's JS fallback (the pokedemo-test bucket) is used. Set per-project via the
# _DEFAULT_IMAGE Cloud Build substitution (see cloudbuild-app.yaml).
ARG VITE_DEFAULT_IMAGE=""
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=https://registry.npmjs.org/
COPY frontend/ ./
RUN VITE_DEFAULT_IMAGE="$VITE_DEFAULT_IMAGE" npm run build

# ---- Stage 2: FastAPI + orchestrator ----
FROM python:3.12-slim AS app
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=5 \
    PORT=8000 \
    FRONTEND_DIST=/app/frontend/dist

COPY agents/requirements.txt agents/requirements.txt
RUN pip install --pre -r agents/requirements.txt

# The APP (Cloud Run) needs `vertexai` for note_responder's Memory Bank read. The agents
# get vertexai from the Agent Runtime env, so it's NOT in the shared agents/requirements.txt.
# Default ON so cloud builds always have it; local compose sets WITH_GCP=0 to skip the heavy
# google-cloud-aiplatform download (the app falls back to in-memory recall locally anyway).
ARG WITH_GCP=1
RUN if [ "$WITH_GCP" != "0" ]; then pip install --pre "google-adk[gcp]==2.3.0"; fi

# Shared package (modules only; deps came from requirements above).
COPY packages/vibeflix-common ./vibeflix-common
RUN pip install ./vibeflix-common --no-deps

COPY agents/ agents/
COPY --from=frontend /build/dist /app/frontend/dist

EXPOSE 8000
# Honor Cloud Run's injected $PORT; defaults to 8000 locally.
CMD ["sh", "-c", "uvicorn agents.app:app --host 0.0.0.0 --port ${PORT}"]

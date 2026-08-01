"""Phase 1 persistence — env-gated session / memory / artifact services + caching.

Session + artifact services are env-gated:
    AGENT_ENGINE_ID    Vertex AI Agent Engine id backing app-level Sessions (usually UNSET —
                       the app is a thin client, so its own sessions stay in-memory)
    ARTIFACTS_BUCKET   GCS bucket for artifacts (images/reports)

Memory is separate and scoped: `build_memory_service(agent_engine_id=…)` backs the
orchestrator's cross-audit recall with the ORCHESTRATOR's own Agent Engine Memory Bank (the
only place that searches memory). Without an engine id everything falls back to in-memory, so
local `run_local.sh` / adk web keep working with zero setup and nothing persists.

Note: `VertexAiSessionService` takes the Agent Engine id in its **constructor**
and resolves sessions against it, ignoring `app_name` for that purpose — so
`app_name` is just a logical label (must start with a letter, per App validation).
The same `APP_NAME` is used across the whole mesh so episodic memory is unified.
"""

import os

# Config comes from the environment. The app entrypoint (agents/app.py) loads its
# .env before importing this module.
from google.adk.sessions import InMemorySessionService, VertexAiSessionService
from google.adk.memory import InMemoryMemoryService, VertexAiMemoryBankService
from google.adk.artifacts import InMemoryArtifactService, GcsArtifactService
from google.adk.agents.context_cache_config import ContextCacheConfig

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID")
MEMORY_LOCATION = os.environ.get("MEMORY_LOCATION", "us-central1")
ARTIFACTS_BUCKET = os.environ.get("ARTIFACTS_BUCKET")

VERTEX_MEMORY = bool(AGENT_ENGINE_ID)
# Logical app name (identifier). The Agent Engine id is passed to the Vertex
# service constructor, not here.
APP_NAME = "vibeflix_audit"


def build_session_service():
    if VERTEX_MEMORY:
        return VertexAiSessionService(
            project=PROJECT, location=MEMORY_LOCATION, agent_engine_id=AGENT_ENGINE_ID
        )
    return InMemorySessionService()


def build_memory_service(agent_engine_id: str | None = None, location: str | None = None):
    """Memory Bank on a SPECIFIC Agent Engine. The app backs the note-responder's cross-audit
    recall (its `load_memory` tool + `_persist_audit`) with the ORCHESTRATOR's OWN engine — passed
    in from ORCHESTRATOR_A2A_URL — so only the orchestrator's memory is durable, with no dedicated
    memory engine and no change to the app's own sessions. In-memory when no engine id is given
    (local dev, or a non-engine URL)."""
    if agent_engine_id and PROJECT:
        try:
            return VertexAiMemoryBankService(
                project=PROJECT, location=location or MEMORY_LOCATION, agent_engine_id=agent_engine_id
            )
        except Exception as e:  # noqa: BLE001 — missing google-cloud-aiplatform, bad engine, etc.
            # Memory is a best-effort feature; degrade to in-memory rather than crash the app.
            print(f"[memory] VertexAiMemoryBankService unavailable "
                  f"({type(e).__name__}: {e}) — falling back to in-memory recall", flush=True)
    return InMemoryMemoryService()


def build_artifact_service():
    if ARTIFACTS_BUCKET:
        return GcsArtifactService(bucket_name=ARTIFACTS_BUCKET)
    return InMemoryArtifactService()


def build_context_cache_config() -> ContextCacheConfig:
    """Vertex-side prompt caching for the stable instruction/semantic prefix."""
    return ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10)


def summary() -> str:
    sess = f"VertexAI({AGENT_ENGINE_ID})" if VERTEX_MEMORY else "InMemory"
    art = f"GCS({ARTIFACTS_BUCKET})" if ARTIFACTS_BUCKET else "InMemory"
    return f"sessions/memory={sess} artifacts={art} app_name={APP_NAME}"

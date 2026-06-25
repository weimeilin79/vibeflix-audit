"""FastAPI proxy that drives the ADK 2.0 Sourcing Orchestrator workflow.

`/api/audit` runs the graph and returns the aggregated reports the frontend
expects. When the requested volume exceeds the vendor cap, the workflow's
human-in-the-loop sourcing gate interrupts; the response then carries
`hitl_required` plus a `session_id`, and the client resolves it via
`/api/resume` (Scenario 3, Option A / Option B).
"""

import os
import json
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.genai import types

from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import InMemoryRunner

from agents.orchestrator.agent import root_agent

APP_NAME = "vibeflix_audit"

# Initialize FastAPI App
app = FastAPI(title="ADK 2.0 Multi-Agent Procurement Service")

# Allow CORS for local frontend React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
class AuditRequest(BaseModel):
    image_path: str = "grogu_mockup_box.png"
    target_market: str = "North America"
    volume: int = 15000


class ResumeRequest(BaseModel):
    session_id: str
    choice: str  # "A" (split to addendum) or "B" (cap and cancel excess)


class TelemetryPayload(BaseModel):
    interaction_type: str
    element_id: str
    time_spent_ms: int
    overridden: bool


# A single resumable ADK app wrapping the workflow graph. Resumability lets the
# HITL sourcing gate pause and continue without replaying the whole graph.
adk_app = App(
    name=APP_NAME,
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
runner = InMemoryRunner(app=adk_app)

# Track sessions awaiting a HITL sourcing decision: session_id -> user_id.
_PENDING: dict[str, str] = {}


def _content(payload: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=payload)])


def _pending_request(event) -> str | None:
    """Return the HITL prompt if this event is requesting user input, else None."""
    req = getattr(event, "request_input", None)
    if req is not None:
        return getattr(req, "message", "Input required.")
    # Fallback for builds that surface the interrupt via actions.
    actions = getattr(event, "actions", None)
    if actions is not None and getattr(actions, "requested_input", None):
        return str(actions.requested_input)
    return None


async def _drain(user_id: str, session_id: str, message: str) -> dict:
    """Run/resume the workflow and collect the outcome.

    Returns either {"status": "completed", "result": <aggregate>} or
    {"status": "hitl_required", "message": <prompt>}.
    """
    final_result: dict | None = None
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=_content(message),
    ):
        prompt = _pending_request(event)
        if prompt is not None:
            return {"status": "hitl_required", "message": prompt}
        output = getattr(event, "output", None)
        if isinstance(output, dict) and "style_report" in output:
            final_result = output

    if final_result is None:
        raise HTTPException(status_code=500, detail="Workflow produced no audit result.")
    return {"status": "completed", "result": final_result}


@app.get("/")
def read_root():
    return {"message": "ADK 2.0 Agent Mesh Backend is online."}


@app.post("/api/audit")
async def run_audit(req: AuditRequest):
    try:
        user_id = f"audit-{uuid.uuid4().hex[:8]}"
        session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id=user_id
        )
        outcome = await _drain(user_id, session.id, req.model_dump_json())

        if outcome["status"] == "hitl_required":
            _PENDING[session.id] = user_id
            return {
                "hitl_required": True,
                "session_id": session.id,
                "message": outcome["message"],
                "vendor_cap": 25000,
                "requested_volume": req.volume,
            }
        return outcome["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/resume")
async def resume_audit(req: ResumeRequest):
    user_id = _PENDING.get(req.session_id)
    if user_id is None:
        raise HTTPException(status_code=404, detail="No audit awaiting a sourcing decision.")
    try:
        outcome = await _drain(user_id, req.session_id, req.choice)
        if outcome["status"] == "completed":
            _PENDING.pop(req.session_id, None)
            return outcome["result"]
        # Still awaiting input (unexpected for a single-gate flow).
        return {
            "hitl_required": True,
            "session_id": req.session_id,
            "message": outcome["message"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/telemetry")
async def log_telemetry(payload: TelemetryPayload):
    # Simulated writing user engagement maps back to governance-telemetry store
    print(f"[Telemetry Ingestion] Received interaction map on {payload.element_id}: Overridden={payload.overridden}")
    return {"status": "telemetry_captured"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("agents.app:app", host="0.0.0.0", port=port, reload=True)

import os
import json
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.orchestrator.agent import SourcingOrchestrator

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

class TelemetryPayload(BaseModel):
    interaction_type: str
    element_id: str
    time_spent_ms: int
    overridden: bool

# Initialize Sourcing Orchestrator graph
orchestrator = SourcingOrchestrator()

@app.get("/")
def read_root():
    return {"message": "ADK 2.0 Agent Mesh Backend is online."}

@app.post("/api/audit")
async def run_audit(req: AuditRequest):
    try:
        # Executes the multi-agent decision workflow
        result = orchestrator.execute_workflow({
            "image_path": req.image_path,
            "target_market": req.target_market,
            "volume": req.volume
        })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/telemetry")
async def log_telemetry(payload: TelemetryPayload):
    # Simulated writing user engagement maps back to governance-telemetry store
    print(f"[Telemetry Ingestion] Received interaction map on {payload.element_id}: Overridden={payload.overridden}")
    return {"status": "telemetry_captured"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)

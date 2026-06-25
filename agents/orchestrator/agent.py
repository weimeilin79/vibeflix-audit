"""Sourcing Orchestrator — ADK 2.0 graph Workflow (the coordinator / router).

Graph shape::

    START -> ingest -> ( brand_style ‖ ip_counsel ‖ storyline )
                     -> merge (JoinNode) -> compile_ui
                     -> sourcing_gate (HITL) -> finalize

`ingest` normalizes the audit request and seeds workflow state; the three
domain LlmAgents fan out in parallel (each calling its MCP tools); a JoinNode
fans their structured reports back in; `compile_ui` assembles the A2UI canvas
payload; `sourcing_gate` is a human-in-the-loop interrupt that only triggers
when the requested volume exceeds the vendor cap.
"""

import json
import os

from dotenv import load_dotenv
from pydantic import BaseModel
from google.genai import types

# Load the orchestrator's Vertex AI / project configuration from its local .env.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from google.adk.workflow import Workflow, JoinNode, node
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput

from agents.brand_style.agent import brand_style_agent
from agents.ip_counsel.agent import ip_counsel_agent
from agents.storyline.agent import storyline_agent

# Authorized primary-vendor ceiling — mirrors mcp_market.check_sku_volume_caps
# (`authorized_max_skus`). Volume above this triggers the HITL sourcing gate.
VENDOR_VOLUME_CAP = 25000
SECONDARY_ADDENDUM = "SC-7798-EU"


class AuditInput(BaseModel):
    """START input schema — parsed from the user message JSON."""

    image_path: str = "grogu_mockup_box.png"
    target_market: str = "North America"
    volume: int = 15000


def ingest(node_input: AuditInput) -> Event:
    """Capture the request, seed shared state, and emit a brief for the agents."""
    brief = (
        f"Audit mockup '{node_input.image_path}' for the {node_input.target_market} "
        f"market at a production volume of {node_input.volume} units."
    )
    return Event(
        output=brief,
        state={
            "image_path": node_input.image_path,
            "target_market": node_input.target_market,
            "volume": node_input.volume,
        },
    )


# Fan-in: collects the three agents' outputs into a dict keyed by agent name.
merge = JoinNode(name="merge_reports")


def compile_ui(ctx: Context, node_input: dict) -> Event:
    """Assemble the A2UI canvas payload from the three merged agent reports."""
    style_report = node_input.get("brand_style_compliance_agent", {})
    legal_report = node_input.get("ip_counsel_agent", {})
    storyline_report = node_input.get("franchise_storyline_agent", {})

    target_market = ctx.state.get("target_market", "North America")
    volume = ctx.state.get("volume", 0)
    blocked = legal_report.get("status") == "blocked"

    a2ui_payload = {
        "a2ui_version": "2.0",
        "canvas_layout": {
            "container": "procurement_audit_viewport",
            "components": [
                {
                    "type": "remediation_form",
                    "fields": [
                        {
                            "id": "target_market",
                            "value": target_market,
                            "status": "blocked" if blocked else "clear",
                        },
                        {"id": "production_volume", "value": volume},
                    ],
                }
            ],
        },
    }

    aggregate = {
        "style_report": style_report,
        "legal_report": legal_report,
        "storyline_report": storyline_report,
        "a2ui_payload": a2ui_payload,
    }
    return Event(output=aggregate, state={"audit_result": aggregate})


@node(name="sourcing_gate", rerun_on_resume=True)
async def sourcing_gate(ctx: Context, node_input: dict):
    """Human-in-the-loop sourcing-cap override (Scenario 3).

    Passes through when volume is within the vendor cap. Otherwise it interrupts
    and asks the user to choose: 'A' to split the excess to a secondary addendum
    contract, or 'B' to cap at the vendor limit and cancel the excess.
    """
    result = dict(node_input)
    volume = int(ctx.state.get("volume", 0))

    if volume <= VENDOR_VOLUME_CAP:
        result["sourcing"] = {
            "status": "auto_finalized",
            "volume": volume,
            "cap": VENDOR_VOLUME_CAP,
        }
        yield Event(output=result)
        return

    excess = volume - VENDOR_VOLUME_CAP
    if not ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="sourcing_cap_override",
            message=(
                f"Production volume {volume} exceeds the primary vendor cap "
                f"{VENDOR_VOLUME_CAP}. Choose 'A' to split the excess {excess} "
                f"units to Addendum Contract {SECONDARY_ADDENDUM}, or 'B' to cap "
                f"at {VENDOR_VOLUME_CAP} units and cancel the excess."
            ),
            response_schema={"type": "string", "enum": ["A", "B"]},
        )
        return

    choice = str(ctx.resume_inputs.get("sourcing_cap_override", "B")).strip().upper()
    if choice == "A":
        result["sourcing"] = {
            "status": "split_addendum",
            "primary_units": VENDOR_VOLUME_CAP,
            "addendum_contract": SECONDARY_ADDENDUM,
            "addendum_units": excess,
        }
    else:
        result["sourcing"] = {
            "status": "capped",
            "primary_units": VENDOR_VOLUME_CAP,
            "cancelled_units": excess,
        }
    yield Event(output=result)


def finalize(node_input: dict):
    """Emit a human-readable summary for the UI and the final result payload."""
    summary = json.dumps(node_input, indent=2)
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=summary)]))
    yield Event(output=node_input)


root_agent = Workflow(
    name="sourcing_orchestrator",
    input_schema=AuditInput,
    edges=[
        ("START", ingest),
        (ingest, (brand_style_agent, ip_counsel_agent, storyline_agent)),
        ((brand_style_agent, ip_counsel_agent, storyline_agent), merge),
        (merge, compile_ui),
        (compile_ui, sourcing_gate),
        (sourcing_gate, finalize),
    ],
)

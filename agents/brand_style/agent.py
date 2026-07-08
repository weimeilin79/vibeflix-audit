"""Brand Style Compliance Agent (the "Designer") — ADK 2.0 extract → audit agent.

The agent does the EXTRACTION (reading the mockup's printed text and product medium,
using its own multimodal vision when it can access the image); the MCP server is
fully deterministic and only runs the checks.

Output is a single `output_schema` (BrandStyleReport) that covers BOTH outcomes:
  * status == "needs_input" → `question` carries what to ask the user (e.g. the
    image link). This is how "conversation / needing more info" stays structured
    instead of crashing an output_schema agent with free prose.
  * status == "flagged" | "compliant" → `findings` merges the checks' results.
"""

import os
import pathlib

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset

from vibeflix_common.mcp_clients import mcp_toolset
from vibeflix_common.schema_guard import make_schema_guard
from vibeflix_common.image_input import require_image_before_model

# Load this agent's Vertex AI / project configuration from its local .env.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_SKILL_DIR = pathlib.Path(__file__).parent / "skills" / "brand-compliance-audit"


class Finding(BaseModel):
    """A single check finding. Fields are the union across the 3 checks (optional)."""

    element_id: str = ""
    issue_type: str = ""
    severity: str = ""
    description: str = ""
    word: str = ""
    suggestions: list[str] = Field(default_factory=list)
    medium: str = ""
    image_uri: str = ""


class Extracted(BaseModel):
    text: list[str] = Field(default_factory=list)
    medium: str = ""
    image_uri: str = ""


class BrandStyleReport(BaseModel):
    """Single structured output covering both the conversation and the result."""

    agent: str = "brand_style_compliance_agent"
    # "needs_input"  → missing info; ask the user (see `question`).
    # "rejected"     → the audit gate failed (unapproved image source); ask the
    #                  user for an approved image (see `question` + `findings`).
    # "flagged" / "compliant" → the audit ran; see `findings`.
    status: str
    # Populated when status is "needs_input" or "rejected": what to ask the user.
    question: str = ""
    # Which inputs are still needed from the user — e.g. ["image"], or ["medium"]
    # in the rare case the medium can't be classified from the mockup. Drives
    # which field(s) the frontend renders.
    needs: list[str] = Field(default_factory=list)
    extracted: Extracted = Field(default_factory=Extracted)
    checks_run: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


brand_style_agent = LlmAgent(
    name="brand_style_compliance_agent",
    model="gemini-flash-latest",
    description=(
        "Extracts a mockup's printed text and classifies its product medium from "
        "the image (an explicitly stated medium overrides), then runs the "
        "deterministic typo, printed-medium, and asset-source checks."
    ),
    instruction=(
        "You are the Brand Style Compliance Agent for the Vibeflix licensing "
        "pipeline. Known context (may be empty): image link `{image_uri?}`, market "
        "`{target_market?}`, licensed character/trademark under audit "
        "`{character_id?}`.\n\n"
        "To audit a product mockup, use the `brand-compliance-audit` skill and "
        "follow its steps exactly — it defines the fixed procedure and the only tool "
        "you may call. ALWAYS respond by filling the BrandStyleReport schema; never "
        "reply in prose."
    ),
    tools=[
        # Procedural knowledge is a versioned ADK Skill (the audit steps live in
        # skills/brand-compliance-audit/SKILL.md); the deterministic pipeline stays
        # the one MCP tool the skill is allowed to call.
        skill_toolset.SkillToolset(
            skills=[load_skill_from_dir(_SKILL_DIR)],
            additional_tools=[mcp_toolset("mcp_brand_style", tool_filter=["run_brand_audit"])],
        ),
    ],
    output_schema=BrandStyleReport,
    output_key="style_report",
    # Deterministic guard: no real image part in the request → return needs_input
    # without calling the model, so it can't hallucinate an extraction.
    before_model_callback=require_image_before_model,
    # Safety net: if the model ever answers in prose instead of the schema, treat
    # it as a question to the user (semantically correct for this agent).
    after_model_callback=make_schema_guard(
        lambda text: {"status": "needs_input", "question": text}
    ),
)

# ADK entrypoint convention — also the agent served standalone over A2A.
root_agent = brand_style_agent

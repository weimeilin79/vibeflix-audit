"""Brand Style Compliance Agent (the "Designer") — ADK 2.0 extract → audit agent.

The agent does the EXTRACTION (reading the artwork's printed text and product medium,
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
from vibeflix_common.tool_guard import make_toolset_health_guard

# Load this agent's Vertex AI / project configuration from its local .env.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_SKILL_DIR = pathlib.Path(__file__).parent / "skills" / "brand-compliance-audit"

# Held as a module-level ref so the fail-closed guard can probe the SAME toolset the
# skill calls through. (The model never sees `run_brand_audit` directly — SkillToolset
# only exposes list_skills/load_skill/run_skill_script — so the guard has to ask the
# MCP toolset itself, not the LLM's tool list.)
_BRAND_MCP = mcp_toolset("mcp_brand_style", tool_filter=["run_brand_audit"])


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
    # in the rare case the medium can't be classified from the artwork. Drives
    # which field(s) the frontend renders.
    needs: list[str] = Field(default_factory=list)
    extracted: Extracted = Field(default_factory=Extracted)
    checks_run: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


brand_style_agent = LlmAgent(
    name="brand_style_compliance_agent",
    model="gemini-2.5-flash",
    description=(
        "Verifies the submitted product artwork depicts the licensed "
        "character/trademark under audit, extracts its printed text and classifies "
        "the product medium from the image (an explicitly stated medium overrides), "
        "then runs the deterministic typo, printed-medium, and asset-source checks."
    ),
    instruction=(
        "You are the Brand Style Compliance Agent for the Vibeflix licensing "
        "pipeline. Known context (may be empty): image link `{image_uri?}`, market "
        "`{target_market?}`, licensed character/trademark under audit "
        "`{character_id?}`.\n\n"
        "To audit product artwork, use the `brand-compliance-audit` skill and "
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
            additional_tools=[_BRAND_MCP],
        ),
    ],
    output_schema=BrandStyleReport,
    output_key="style_report",
    before_model_callback=[
        # Deterministic guard: no real image part in the request → return needs_input
        # without calling the model, so it can't hallucinate an extraction.
        require_image_before_model,
        # Fail CLOSED if the MCP toolset can't reach its server: with no
        # run_brand_audit the model will happily invent checks_run and report
        # findings: [] — a clean "compliant" verdict for an audit that never ran.
        make_toolset_health_guard(
            _BRAND_MCP,
            "run_brand_audit",
            on_missing=lambda missing: {
                "status": "error",
                "question": (
                    "Brand audit unavailable: the deterministic check pipeline "
                    f"({', '.join(missing)}) could not be reached, so no audit was "
                    "run. This is NOT a pass — retry once the tool is reachable."
                ),
            },
        ),
    ],
    # Safety net: if the model ever answers in prose instead of the schema, treat
    # it as a question to the user (semantically correct for this agent).
    after_model_callback=make_schema_guard(
        lambda text: {"status": "needs_input", "question": text}
    ),
)

# ADK entrypoint convention — also the agent served standalone over A2A.
root_agent = brand_style_agent

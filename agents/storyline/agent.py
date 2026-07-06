"""Franchise Storyline & Lore Agent (the "Lore") — ADK 2.0 LlmAgent node.

Verifies a prototype concept against active filming scripts, canon lore and
spoiler embargoes. There is no dedicated MCP server for the script database in
this workspace, so the canon lookup is exposed as a local ADK FunctionTool.
"""

import os
import pathlib

from dotenv import load_dotenv
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset

from vibeflix_common.schema_guard import make_schema_guard

# Load this agent's Vertex AI / project configuration from its local .env.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_SKILL_DIR = pathlib.Path(__file__).parent / "skills" / "canon-check"


def query_script_canon(character_id: str, design_concept: str) -> dict:
    """Check a prototype design concept against the franchise script & canon database.

    Returns canon consistency and spoiler-embargo clearance for the concept.
    """
    if "grogu" in character_id.lower():
        return {
            "canon_consistent": True,
            "spoiler_embargo_cleared": True,
            "message": (
                "Concept (Grogu in hover-pram) matches approved season canon. "
                "No script leaks found."
            ),
        }
    return {
        "canon_consistent": False,
        "spoiler_embargo_cleared": False,
        "message": "Design concept could not be validated against official character scripts.",
    }


class StorylineReport(BaseModel):
    """Structured output passed downstream to the JoinNode / compile_ui node."""

    agent: str = "franchise_storyline_agent"
    status: str  # "compliant" | "unverified"
    canon_consistent: bool
    spoiler_embargo_cleared: bool
    message: str


storyline_agent = LlmAgent(
    name="franchise_storyline_agent",
    model="gemini-flash-latest",
    description=(
        "Validates prototype concepts against current canon story guidelines and "
        "marketing spoiler embargoes."
    ),
    instruction=(
        "You are the Franchise Storyline & Lore Compliance Agent for the Vibeflix "
        "licensing pipeline. The mockup under review is `{image_path?}` for the "
        "`{target_market?}` market.\n\n"
        "To check canon and spoiler compliance, use the `canon-check` skill and "
        "follow its steps exactly. Respond by filling the StorylineReport schema; "
        "never reply in prose."
    ),
    tools=[
        # Procedural knowledge is a versioned ADK Skill (skills/canon-check/); the
        # canon lookup is the local tool the skill is allowed to call.
        skill_toolset.SkillToolset(
            skills=[load_skill_from_dir(_SKILL_DIR)],
            additional_tools=[FunctionTool(func=query_script_canon)],
        ),
    ],
    output_schema=StorylineReport,
    output_key="storyline_report",
    # Stopgap: coerce a prose reply into a valid StorylineReport instead of
    # crashing. Remove if you drop output_schema to make this agent conversational.
    after_model_callback=make_schema_guard(
        lambda text: {
            "agent": "franchise_storyline_agent",
            "status": "unverified",
            "canon_consistent": False,
            "spoiler_embargo_cleared": False,
            "message": text,
        }
    ),
)

# ADK entrypoint convention — also the agent served standalone over A2A.
root_agent = storyline_agent

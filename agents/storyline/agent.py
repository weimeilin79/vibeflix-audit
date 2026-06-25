"""Franchise Storyline & Lore Agent (the "Lore") — ADK 2.0 LlmAgent node.

Verifies a prototype concept against active filming scripts, canon lore and
spoiler embargoes. There is no dedicated MCP server for the script database in
this workspace, so the canon lookup is exposed as a local ADK FunctionTool.
"""

import os

from dotenv import load_dotenv
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

# Load this agent's Vertex AI / project configuration from its local .env.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


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
        "licensing pipeline.\n"
        "The mockup under review is `{image_path}` for the `{target_market}` market.\n\n"
        "Call `query_script_canon` with character_id 'grogu' and design_concept "
        "'Grogu in hover-pram' to check the concept against the script/canon "
        "database.\n\n"
        "Respond with ONLY a JSON object matching the StorylineReport schema: set "
        "`status` to 'compliant' when the concept is canon-consistent AND the "
        "spoiler embargo is cleared, otherwise 'unverified'. Copy "
        "`canon_consistent`, `spoiler_embargo_cleared` and `message` from the tool "
        "result."
    ),
    tools=[FunctionTool(func=query_script_canon)],
    output_schema=StorylineReport,
    output_key="storyline_report",
)

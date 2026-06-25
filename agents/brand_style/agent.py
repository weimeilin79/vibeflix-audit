"""Brand Style Compliance Agent (the "Designer") — ADK 2.0 LlmAgent node.

Extracts typography/logo/color from the mockup via the vision MCP server and
checks it against the franchise style registry served by the legal MCP server.
Placed directly in the Sourcing Orchestrator workflow graph (auto-wrapped).
"""

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent

from agents.mcp_clients import mcp_toolset

# Load this agent's Vertex AI / project configuration from its local .env.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


class StyleAnomaly(BaseModel):
    element_id: str
    issue_type: str = "typography_anomaly"
    severity: str = "warning"
    description: str


class StyleReport(BaseModel):
    """Structured output passed downstream to the JoinNode / compile_ui node."""

    agent: str = "brand_style_compliance_agent"
    status: str  # "compliant" | "warning"
    anomalies: list[StyleAnomaly] = Field(default_factory=list)


brand_style_agent = LlmAgent(
    name="brand_style_compliance_agent",
    model="gemini-flash-latest",
    description=(
        "Extracts fonts, logos and colors from a product mockup and verifies them "
        "against the official franchise style registry."
    ),
    instruction=(
        "You are the Brand Style Compliance Agent for the Vibeflix licensing pipeline.\n"
        "The mockup under review is `{image_path}` for the `{target_market}` market.\n\n"
        "Do the following with your tools:\n"
        "1. Call `parse_design_elements` on the image to extract every text element, "
        "its font, and its color.\n"
        "2. Call `query_style_guidelines` with character_id 'grogu' to load the "
        "official `allowed_fonts` and `hex_palette`.\n"
        "3. For each extracted text element whose font is NOT in `allowed_fonts`, "
        "record a typography anomaly with severity 'warning', element_id derived "
        "from the text (e.g. 'text_the_child'), and a description naming the "
        "offending font and the allowed fonts.\n"
        "4. If you find an anomaly, you may call `flash_threat_vector` to highlight "
        "the element on the audit canvas.\n\n"
        "Respond with ONLY a JSON object matching the StyleReport schema: set "
        "`status` to 'warning' when there is at least one anomaly, otherwise "
        "'compliant'."
    ),
    tools=[
        mcp_toolset("mcp_vision_ui", tool_filter=["parse_design_elements", "flash_threat_vector"]),
        mcp_toolset("mcp_legal", tool_filter=["query_style_guidelines"]),
    ],
    output_schema=StyleReport,
    output_key="style_report",
)

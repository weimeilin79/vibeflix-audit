"""Global Market Clearance & IP Counsel Agent (the "Counsel") — ADK 2.0 LlmAgent.

Checks territorial exclusivity, trademark/customs registration and marketplace
leaks using the legal and market MCP servers. Runs in parallel with the brand
style and storyline agents inside the Sourcing Orchestrator workflow graph.
"""

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent

from agents.mcp_clients import mcp_toolset

# Load this agent's Vertex AI / project configuration from its local .env.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


class ClearanceIssue(BaseModel):
    element_id: str
    issue_type: str
    severity: str
    description: str
    partner_conflict: str | None = None


class LegalReport(BaseModel):
    """Structured output passed downstream to the JoinNode / compile_ui node."""

    agent: str = "ip_counsel_agent"
    status: str  # "cleared" | "blocked"
    issues: list[ClearanceIssue] = Field(default_factory=list)
    ecom_status: str = ""


ip_counsel_agent = LlmAgent(
    name="ip_counsel_agent",
    model="gemini-flash-latest",
    description=(
        "Verifies territorial rights, exclusivity collisions, trademark/customs "
        "registration and marketplace leaks for a licensed character."
    ),
    instruction=(
        "You are the Global Market Clearance & IP Counsel Agent for the Vibeflix "
        "licensing pipeline.\n"
        "Character under review: 'grogu'. Target territory: `{target_market}`.\n\n"
        "Do the following with your tools:\n"
        "1. Call `scan_global_exclusivity_clauses` for character 'grogu' in the "
        "territory. If the result has `has_conflict` true, record an "
        "'exclusivity_collision' issue with severity 'critical', set "
        "`partner_conflict` to the `conflicting_partner`, and describe the block.\n"
        "2. Call `verify_trademark_record` for 'grogu'. If `registration_status` is "
        "not 'Valid', record a 'customs_invalid' issue with severity 'warning'.\n"
        "3. Call `scan_ecom_marketplaces` for 'grogu' in the region and capture the "
        "returned `status` string as the e-commerce leak status.\n\n"
        "Respond with ONLY a JSON object matching the LegalReport schema: set "
        "`status` to 'blocked' when there is an exclusivity collision, otherwise "
        "'cleared'; put the scan status string in `ecom_status`."
    ),
    tools=[
        mcp_toolset(
            "mcp_legal",
            tool_filter=[
                "check_territorial_rights",
                "scan_global_exclusivity_clauses",
                "verify_trademark_record",
            ],
        ),
        mcp_toolset("mcp_market", tool_filter=["scan_ecom_marketplaces"]),
    ],
    output_schema=LegalReport,
    output_key="legal_report",
)

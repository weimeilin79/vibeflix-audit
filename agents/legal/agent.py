"""Legal Clearance Agent — an INDEPENDENT A2A service, private to vendor_clearance.

Not part of the orchestrator's audit fan-out. vendor_clearance calls it (over A2A)
when a vendor is newly onboarded for a product category, to auto-clear all the legal
work for that vendor × character × category × territory. It is a self-looping agent:
it runs the legal checklist and remediates any pending item (missing certification,
insufficient insurance) until everything is cleared, then executes the licensing
contract (persisted via mcp_licensing.upsert_contract).

The individual legal checks are MOCKED here (in-process function tools); only the final
contract write is real. Its own container / A2A service (:8005) — independently
deployable, like the domain agents.
"""

import os
import pathlib
import uuid

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset

from vibeflix_common.mcp_clients import mcp_toolset

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_SKILL_DIR = pathlib.Path(__file__).parent / "skills" / "legal-clearance"

# RAG over the scattered legal "tribal knowledge" docs (resource/legal/docs). Local
# keyword retriever by default; Vertex AI RAG Engine when RAG_CORPUS is set.
try:
    from agents.legal.legal_kb import search_legal_docs
except ImportError:  # loaded from the agent dir (e.g. `adk web agents/legal`)
    import sys as _sys
    _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from legal_kb import search_legal_docs


def _ref(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:4].upper()}"


# ---- Mocked legal-clearance steps (in-process tools) ----------------------
def draft_license_amendment(vendor_id: str, character: str, category: str, territory: str) -> dict:
    """Draft + register a master-license amendment adding this category for the vendor."""
    return {"step": "license_amendment", "amendment_id": _ref("LA"), "status": "registered",
            "scope": f"{character} · {category} · {territory}"}


def verify_certifications(category: str) -> dict:
    """Verify the safety certifications this product category requires. Returns
    `conditional` with the missing certs when something needs remediation."""
    required = {"Vinyl Figures": ["ASTM F963", "EN71", "CPSIA"],
                "Plush": ["ASTM F963", "EN71"], "Apparel": ["OEKO-TEX"],
                }.get(category, ["ASTM F963"])
    return {"step": "certifications", "required": required, "missing": ["EN71"] if "EN71" in required else [],
            "status": "conditional" if "EN71" in required else "cleared",
            "remediation": "call request_certification for each missing cert"}


def request_certification(vendor_id: str, certification: str) -> dict:
    """Request + attach a missing certification for the vendor (remediation)."""
    return {"step": "certification_request", "certification": certification,
            "vendor_id": vendor_id, "status": "granted", "certificate_id": _ref("CERT")}


def assign_customs_hs_code(category: str, territory: str) -> dict:
    """Assign the HS tariff code for the category and file customs recordation."""
    hs = {"Vinyl Figures": "9503.00.00", "Plush": "9503.00.41", "Apparel": "6109.10.00"}.get(category, "9503.00.00")
    return {"step": "customs", "hs_code": hs, "territory": territory, "recordation": "filed", "status": "cleared"}


def set_royalty_rate(character: str, category: str) -> dict:
    """Set the royalty rate for this character × category."""
    return {"step": "royalty", "character": character, "category": category,
            "rate_pct": 12, "status": "cleared"}


def verify_liability_insurance(vendor_id: str, category: str) -> dict:
    """Verify the vendor's product-liability insurance covers this category. Returns
    `insufficient` when a rider is needed."""
    return {"step": "insurance", "vendor_id": vendor_id, "status": "insufficient",
            "required_coverage_usd": 5_000_000, "remediation": "call request_insurance_rider"}


def request_insurance_rider(vendor_id: str, category: str) -> dict:
    """Request a product-liability insurance rider for the category (remediation)."""
    return {"step": "insurance_rider", "vendor_id": vendor_id, "category": category,
            "rider_id": _ref("RIDER"), "coverage_usd": 5_000_000, "status": "granted"}


legal_agent = LlmAgent(
    name="legal_clearance_agent",
    model="gemini-2.5-flash",
    description="Clears the legal work for a newly-onboarded vendor × category and "
                "executes the licensing contract. In this demo only vendor_clearance "
                "hands off to it, but any agent could.",
    instruction=(
        "You are the Legal Clearance Agent. Follow the `legal-clearance` skill. ALWAYS "
        "reply with exactly ONE JSON object (never prose, no markdown fences):\n"
        "- given a clearance BRIEF (a vendor + character + product category + territory, "
        "possibly with a royalty tier / safety-cert id) → status `ask_vendor` / "
        "`needs_user` / `done` as the skill dictates. When you ASK for a value, state the "
        "options in the `question` so the asker knows what to answer.\n"
        "- if the caller ASKS YOU a question — what a term means (e.g. 'annual-volume "
        "band'), what the options are, or how something works → status `answer` with an "
        "`answer` field explaining it (looked up via `search_legal_docs`)."
    ),
    tools=[
        skill_toolset.SkillToolset(
            skills=[load_skill_from_dir(_SKILL_DIR)],
            additional_tools=[
                # RAG the (undefined) process out of the scattered legal docs.
                search_legal_docs,
                draft_license_amendment,
                verify_certifications,
                request_certification,
                assign_customs_hs_code,
                set_royalty_rate,
                verify_liability_insurance,
                request_insurance_rider,
                # The one REAL side effect: persist the licensing contract.
                mcp_toolset("mcp_licensing", tool_filter=["upsert_contract"]),
            ],
        ),
    ],
)

root_agent = legal_agent

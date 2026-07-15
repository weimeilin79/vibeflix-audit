"""Deal Pricing Auditor — an ADK 2.0 Workflow served over A2A.

Audits the vendor's AGREED total consideration (royalty rate + advance + minimum
guarantee) for using the IP against the licensor's rate card
(`mcp_licensing.get_license_pricing`). Internal loop-engineering:

    START -> evaluate -> reconcile (LOOP) -> finalize

`evaluate` runs the pricing reasoner (pulls the rate card, computes the EXPECTED deal,
compares each component). `reconcile` is the loop: while any component is UNRESOLVED (the
vendor claims a factor that must be checked, e.g. a volume-tier discount), a resolver
adjudicates it and we recompute — up to MAX_ROUNDS — then settle the verdict
(APPROVED / NEEDS_ADJUSTMENT / UNDERPRICED).
"""

import os
import json
import pathlib

from dotenv import load_dotenv
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.workflow import Workflow, node
from google.adk.agents.context import Context
from google.adk.events.event import Event

from vibeflix_common.mcp_clients import mcp_toolset
from vibeflix_common.models import gemini
# Live mesh telemetry: every node emits started/completed onto PUBSUB_TOPIC (no-op
# when unset) — lets the Workflow graph show the mesh working in real time.
from vibeflix_common.telemetry import instrument_node

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
_SKILL_DIR = pathlib.Path(__file__).parent / "skills" / "deal-pricing-audit"

MAX_ROUNDS = 4


# ---- helpers (same shapes as vendor_clearance) ----------------------------
def _text_of(content) -> str:
    parts = getattr(content, "parts", None) or []
    return "".join(getattr(p, "text", "") or "" for p in parts)


def _latest_text(ctx: Context, author: str) -> str:
    events = getattr(getattr(ctx, "session", None), "events", None) or []
    for e in reversed(events):
        if getattr(e, "author", None) == author:
            t = _text_of(getattr(e, "content", None))
            if t.strip():
                return t
    return ""


def _parse(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    for c in (text, text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""):
        try:
            o = json.loads(c)
            if isinstance(o, dict):
                return o
        except (ValueError, TypeError):
            continue
    return {}


# ---- the pricing reasoner: rate card -> expected -> per-component compare ----
pricing_reasoner = LlmAgent(
    name="pricing_reasoner",
    model=gemini(),   # retries 429 with backoff — see vibeflix_common/models.py
    description="Reasons the deal-pricing audit: expected vs agreed royalty / advance / MG.",
    instruction=(
        "You are the Deal Pricing reasoner for the Vibeflix pipeline. The deal is: character "
        "`{character_id?}`, product category `{product_category?}`, territory "
        "`{target_market?}`, projected volume `{volume?}` units, net unit price "
        "`{net_unit_price?}`. The vendor's AGREED terms are: royalty rate "
        "`{agreed_royalty_rate?}`, advance `{agreed_advance?}`, minimum guarantee "
        "`{agreed_mg?}`. Anything blank was not provided.\n\n"
        "Follow the `deal-pricing-audit` skill EXACTLY. Call `get_license_pricing` WITH "
        "`volume` and `net_unit_price` so the tool returns the deterministically-computed "
        "`expected` deal — use those numbers verbatim, NEVER recompute the math. Include the "
        "returned `rate_card` and `expected` in your output. Respond "
        "with ONLY a single JSON object matching the skill's report shape "
        "(agent=\"deal_pricing_agent\", components[], expected, agreed, rate_card) — no prose, "
        "no markdown fences."
    ),
    tools=[
        skill_toolset.SkillToolset(
            skills=[load_skill_from_dir(_SKILL_DIR)],
            additional_tools=[mcp_toolset("mcp_licensing", tool_filter=["get_license_pricing"])],
        ),
    ],
)


# ---- the resolver: adjudicate ONE unresolved discrepancy against the rules ----
resolver = LlmAgent(
    name="pricing_resolver",
    model=gemini(),   # retries 429 with backoff — see vibeflix_common/models.py
    description="Adjudicates one unresolved pricing discrepancy against the rate-card rules.",
    instruction=(
        "You are given ONE unresolved pricing discrepancy plus the rate-card rules and deal "
        "facts, as JSON in the message. Decide whether a legitimate factor the vendor claims "
        "actually explains it — e.g. a volume-tier discount applies ONLY if the projected "
        "volume meets that tier's `min_units`; a category/territory modifier must match the "
        "rate card. Respond with ONLY one JSON object: "
        "{\"name\": str, \"resolved\": bool, \"explanation\": str, "
        "\"corrected_expected\": number|null}. `resolved:true` means the agreed value is "
        "justified; `false` means the discrepancy stands."
    ),
)


# ---- the graph -------------------------------------------------------------
@node(name="evaluate", rerun_on_resume=True)
@instrument_node("deal_pricing")
async def evaluate(ctx: Context, node_input):
    """Run the reasoner -> parse its per-component verdict."""
    await ctx.run_node(pricing_reasoner, node_input)
    report = _parse(_latest_text(ctx, "pricing_reasoner")) or {"status": "flagged", "components": []}
    report["agent"] = "deal_pricing_agent"
    yield Event(output=report)


@node(name="reconcile", rerun_on_resume=True)
@instrument_node("deal_pricing")
async def reconcile(ctx: Context, node_input):
    """LOOP: adjudicate UNRESOLVED components until none remain (or MAX_ROUNDS), then rule."""
    report = node_input if isinstance(node_input, dict) else {}
    card = report.get("rate_card", {})
    deal = {k: report.get(k) for k in ("expected", "agreed")}
    for _ in range(MAX_ROUNDS):
        unresolved = [c for c in report.get("components", []) if c.get("status") == "unresolved"]
        if not unresolved:
            break
        for c in unresolved:
            await ctx.run_node(resolver, json.dumps({"discrepancy": c, "rate_card": card, "deal": deal}))
            r = _parse(_latest_text(ctx, "pricing_resolver"))
            if r.get("resolved"):
                c["status"] = "clear"
            else:
                c["status"] = "discrepancy"
            c["note"] = r.get("explanation", "")
            if r.get("corrected_expected") is not None:
                c["expected"] = r["corrected_expected"]

    comps = report.get("components", [])
    if any(c.get("status") == "discrepancy" and c.get("below_floor") for c in comps):
        report["verdict"], report["status"] = "UNDERPRICED", "blocked"
    elif any(c.get("status") == "discrepancy" for c in comps):
        report["verdict"], report["status"] = "NEEDS_ADJUSTMENT", "flagged"
    else:
        report["verdict"], report["status"] = "APPROVED", "cleared"
    yield Event(output=report)


@instrument_node("deal_pricing")
def finalize(node_input):
    """Emit the final DealPricingReport (content = what A2A returns)."""
    report = node_input if isinstance(node_input, dict) else {}
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(report))]))
    yield Event(output=report)


root_agent = Workflow(
    name="deal_pricing",
    description=(
        "Audits the vendor's AGREED deal terms — royalty rate, advance, and minimum "
        "guarantee — against the licensor's official rate card: fetches the "
        "deterministically-computed EXPECTED deal for the character, category, "
        "territory, volume and net unit price (mcp_licensing.get_license_pricing), "
        "reconciles each discrepancy against legitimate rate-card factors (volume "
        "tiers, category/territory modifiers), and returns a cleared or flagged "
        "PricingReport itemizing any unjustified deviations."
    ),
    edges=[
        ("START", evaluate),
        (evaluate, reconcile),
        (reconcile, finalize),
    ],
)

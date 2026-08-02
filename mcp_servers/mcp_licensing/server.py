"""Vendor & Licensing Clearance Registry — MCP server.

The data backbone for the `vendor_clearance` agent. Holds three stores and exposes
tools to read, search, create and update them:

  * VENDORS      — approved manufacturing partners (who they are, where they may
                   operate, what they can make, capacity, certifications, status).
  * TRADEMARKS   — IP/trademark registrations per character/mark (owner, classes,
                   per-jurisdiction status, customs recordation, renewal).
  * EXCLUSIVITY  — active exclusivity contracts that lock a product category to a
                   partner in a territory (the "VND-1008 holds NA grogu vinyl" rule).

STORAGE: plain in-memory dicts, seeded with realistic sample data. They are
*writable* (create/update mutate them), which is exactly why this isn't the
read-only Firestore `registry_get` used elsewhere. Caveat — in-memory means
per-process, single-instance, and reset on restart; a production deployment would
back these with Firestore/Postgres behind the same tool surface.
"""

import os
import json
import copy
import random
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Vendor & Licensing Clearance Registry")

# Live mesh telemetry: every tool emits started/completed/failed onto PUBSUB_TOPIC
# (no-op when unset) — drives the Workflow graph's tool LEDs. Hooked at
# registration, so new tools are instrumented automatically.
from vibeflix_common.platform.telemetry import instrument_fastmcp
instrument_fastmcp(mcp, source="mcp_licensing")

# Seed data lives in data.py (keeps this file focused on the tools).
from data import (_TRADEMARKS, _EXCLUSIVITY, _CONTRACTS, _RATE_CARDS,
                  vendors_all, vendor_get, vendor_put, vendor_reset)

# Allowed-value hints surfaced to the agent in each tool's parameter schema.
_TERRITORIES = '"North America", "Europe", "Asia-Pacific", "Latin America", or "Middle East & Africa"'
_CATEGORIES = 'e.g. "Vinyl Figures", "Action Figures", "Plush", "Resin Statues", "Blind Box", "Apparel"'
_STATUSES = '"active", "suspended", or "pending_review"'
_CHARACTERS = '"grogu", "gremlins", "et", "stitch", "little_green_men", "minions"'


def _match_territory(vendor: dict, territory: str) -> bool:
    return not territory or territory in vendor.get("operating_territories", [])


def _match_category(vendor: dict, category: str) -> bool:
    return not category or category in vendor.get("product_categories", [])


# ---------------------------------------------------------------------------
# Tools — vendors
# ---------------------------------------------------------------------------
@mcp.tool()
def get_vendor(
    vendor_id: Annotated[str, Field(description='Vendor ID to fetch, e.g. "VND-1001" (case-insensitive).')],
) -> str:
    """Fetch a single approved manufacturing vendor's full record by its ID."""
    vendor = vendor_get((vendor_id or "").strip().upper())
    if not vendor:
        return json.dumps({"error": f"Vendor {vendor_id!r} not found.", "vendor_id": vendor_id})
    return json.dumps(vendor)


@mcp.tool()
def find_vendors(
    territory: Annotated[str, Field(description=f'Filter to vendors that operate in this territory: {_TERRITORIES}. Empty = any.')] = "",
    category: Annotated[str, Field(description=f'Filter to vendors that make this product category: {_CATEGORIES}. Empty = any.')] = "",
    status: Annotated[str, Field(description=f'Filter by vendor status: {_STATUSES}. Empty = any.')] = "",
) -> str:
    """Search the vendor registry by operating territory, product category, and/or
    status. Returns the matching vendor records."""
    results = [
        v for v in vendors_all().values()
        if _match_territory(v, territory)
        and _match_category(v, category)
        and (not status or v.get("status") == status)
    ]
    return json.dumps({
        "count": len(results),
        "filters": {"territory": territory, "category": category, "status": status},
        "vendors": results,
    })


@mcp.tool()
def create_vendor(
    vendor_json: Annotated[str, Field(description=(
        'JSON object for the new vendor. REQUIRED: "legal_name" (str), "hq_country" (str). '
        'OPTIONAL: "dba" (str), "operating_territories" (list of territories), '
        '"product_categories" (list), "manufacturing_capabilities" (list), "license_tier" (str), '
        '"status" (str), "annual_capacity_units" (int), "moq" (int), "lead_time_days" (int), '
        '"certifications" (list), "compliance_rating" (str), "last_audit" (YYYY-MM-DD), '
        '"contact" ({name,email,phone}), "onboarded" (YYYY-MM-DD), "notes" (str). '
        '"vendor_id" is auto-assigned (VND-####) if omitted. '
        'Example: {"legal_name":"Acme Toys","hq_country":"Vietnam","operating_territories":["Asia-Pacific"],"product_categories":["Vinyl Figures"]}'
    ))],
) -> str:
    """Create a new vendor from a JSON object. `vendor_id` is assigned if omitted.
    Required: `legal_name`, `hq_country`. Returns the created record."""
    try:
        data = json.loads(vendor_json)
        assert isinstance(data, dict)
    except (ValueError, AssertionError):
        return json.dumps({"error": "vendor_json must be a JSON object."})
    for req in ("legal_name", "hq_country"):
        if not data.get(req):
            return json.dumps({"error": f"Missing required field: {req!r}."})
    existing = vendors_all()
    vid = (data.get("vendor_id") or "").strip().upper()
    if not vid:
        nums = [int(k.split("-")[1]) for k in existing if k.startswith("VND-")]
        vid = f"VND-{(max(nums) + 1) if nums else 1001}"
    if vid in existing:
        return json.dumps({"error": f"Vendor {vid} already exists (use update_vendor)."})
    record = {
        "vendor_id": vid,
        "legal_name": data["legal_name"],
        "dba": data.get("dba", ""),
        "hq_country": data["hq_country"],
        "operating_territories": data.get("operating_territories", []),
        "product_categories": data.get("product_categories", []),
        "manufacturing_capabilities": data.get("manufacturing_capabilities", []),
        "license_tier": data.get("license_tier", "Tier 3 - Probation"),
        # New vendors are added ACTIVE so they're immediately usable for clearance.
        "status": data.get("status", "active"),
        "annual_capacity_units": data.get("annual_capacity_units", 0),
        "moq": data.get("moq", 0),
        "lead_time_days": data.get("lead_time_days", 0),
        "certifications": data.get("certifications", []),
        "compliance_rating": data.get("compliance_rating", "—"),
        "last_audit": data.get("last_audit", ""),
        "contact": data.get("contact", {}),
        "onboarded": data.get("onboarded", ""),
        "notes": data.get("notes", ""),
    }
    vendor_put(vid, record)
    return json.dumps({"created": True, "vendor": record})


@mcp.tool()
def update_vendor(
    vendor_id: Annotated[str, Field(description='ID of the vendor to update, e.g. "VND-1005".')],
    updates_json: Annotated[str, Field(description=(
        'JSON object of the fields to change, merged into the existing record. Any vendor '
        'field is allowed except "vendor_id" (immutable). '
        'Example: {"status":"active","compliance_rating":"B","operating_territories":["Europe","North America"]}'
    ))],
) -> str:
    """Update an existing vendor. `updates_json` is a JSON object of the fields to
    change (merged into the record). Returns the updated record."""
    vid = (vendor_id or "").strip().upper()
    current = vendor_get(vid)
    if not current:
        return json.dumps({"error": f"Vendor {vendor_id!r} not found."})
    try:
        updates = json.loads(updates_json)
        assert isinstance(updates, dict)
    except (ValueError, AssertionError):
        return json.dumps({"error": "updates_json must be a JSON object."})
    record = copy.deepcopy(current)
    updates.pop("vendor_id", None)  # id is immutable
    record.update(updates)
    vendor_put(vid, record)
    return json.dumps({"updated": True, "changed": sorted(updates), "vendor": record})


@mcp.tool()
def dump_stores() -> str:
    """READ-ONLY dump of every licensing store — vendors (Firestore-backed),
    trademarks, exclusivity contracts, executed licensing contracts, and rate
    cards. Powers the console's Database tab; not for agent reasoning."""
    return json.dumps({
        "vendors": vendors_all(),
        "trademarks": _TRADEMARKS,
        "exclusivity": _EXCLUSIVITY,
        "contracts": _CONTRACTS,
        "rate_cards": _RATE_CARDS,
    })


@mcp.tool()
def reset_vendors() -> str:
    """DEMO RESET: restore the vendor registry to its pristine default records —
    vendors onboarded at runtime are deleted, default vendors are overwritten (any
    categories added to them are removed) — and clear all executed licensing
    contracts. Not a production operation."""
    counts = vendor_reset()
    n_contracts = len(_CONTRACTS)
    _CONTRACTS.clear()
    return json.dumps({"reset": True, "vendors_restored": counts["restored"],
                       "extra_vendors_deleted": counts["deleted"],
                       "contracts_cleared": n_contracts})


# ---------------------------------------------------------------------------
# Tools — trademark & exclusivity clearance
# ---------------------------------------------------------------------------
@mcp.tool()
def list_trademarks() -> str:
    """List every licensed trademark/character in the registry — its canonical `id`
    (the value the clearance tools match on), display `mark`, and `owner`. Used to
    populate the character/trademark picker in the UI so callers select a valid id
    instead of free-typing (which silently misses trademark + exclusivity records)."""
    return json.dumps([
        {"id": k, "mark": v.get("mark", k), "owner": v.get("owner", "")}
        for k, v in _TRADEMARKS.items()
    ])


@mcp.tool()
def verify_trademark_record(
    character_id: Annotated[str, Field(description=f'Character/mark ID (case-insensitive): {_CHARACTERS}.')],
    territory: Annotated[str, Field(description=f'Optional — also return this jurisdiction\'s registration status: {_TERRITORIES}. Empty = registration summary only.')] = "",
) -> str:
    """Validate a character's trademark registration (and, if a `territory` is given,
    that jurisdiction's registration status + customs recordation) so shipments
    aren't seized at the border."""
    cid = (character_id or "").strip().lower()
    tm = _TRADEMARKS.get(cid)
    if not tm:
        return json.dumps({"character_id": character_id, "registration_status": "Unknown",
                           "error": "No trademark record found."})
    out = dict(tm)
    if territory:
        out["territory_queried"] = territory
        out["territory_status"] = tm.get("jurisdictions", {}).get(territory, "unregistered")
    return json.dumps(out)


@mcp.tool()
def scan_global_exclusivity_clauses(
    character_id: Annotated[str, Field(description=f'Character/mark ID (case-insensitive): {_CHARACTERS}.')],
    territory: Annotated[str, Field(description=f'Territory to check for an exclusivity lock: {_TERRITORIES}.')],
) -> str:
    """Crawl active exclusivity contracts to see if a competitor holds an exclusive
    lock on this character's product category in this territory (e.g. an exclusive partner vendor on
    vinyl figures in North America). Only ACTIVE, non-expired contracts count."""
    cid = (character_id or "").strip().lower()
    hits = [
        c for c in _EXCLUSIVITY.values()
        if c.get("character_id") == cid
        and c.get("territory") == territory
        and c.get("status") == "active"
    ]
    if hits:
        c = hits[0]
        return json.dumps({
            "has_conflict": True,
            "contract_id": c["contract_id"],
            "conflicting_partner": c["partner"],
            "exclusivity_type": c["category"],
            "contract_expiration": c["expiration"],
            "message": f"Block release. {c['partner']} holds exclusive rights for "
                       f"{c['category']} in {territory} until {c['expiration']}.",
        })
    return json.dumps({
        "has_conflict": False,
        "message": f"No active exclusivity lock for '{character_id}' in {territory}.",
    })


@mcp.tool()
def check_vendor_eligibility(
    vendor_id: Annotated[str, Field(description='Vendor ID to evaluate, e.g. "VND-1001".')],
    territory: Annotated[str, Field(description=f'Target market/territory: {_TERRITORIES}.')],
    category: Annotated[str, Field(description=f'Product category to manufacture: {_CATEGORIES}.')],
    character_id: Annotated[str, Field(description=f'Character/mark for the exclusivity check ({_CHARACTERS}). Defaults to "grogu".')] = "grogu",
) -> str:
    """Combined go/no-go for a vendor: is this vendor ACTIVE, cleared to operate in
    `territory`, able to make `category`, AND free of an exclusivity lock there?
    Returns `eligible` plus the specific blocking reasons."""
    vid = (vendor_id or "").strip().upper()
    vendor = vendor_get(vid)
    if not vendor:
        return json.dumps({"eligible": False, "reasons": [f"Vendor {vendor_id!r} not found."]})
    reasons = []
    if vendor.get("status") != "active":
        reasons.append(f"Vendor status is '{vendor.get('status')}', not active.")
    if not _match_territory(vendor, territory):
        reasons.append(f"Vendor is not cleared to operate in {territory}.")
    if not _match_category(vendor, category):
        reasons.append(f"Vendor does not manufacture category '{category}'.")
    excl = json.loads(scan_global_exclusivity_clauses(character_id, territory))
    if excl.get("has_conflict"):
        reasons.append(excl["message"])
    return json.dumps({
        "vendor_id": vid,
        "territory": territory,
        "category": category,
        "eligible": not reasons,
        "reasons": reasons or ["Vendor is eligible for this territory + category."],
    })


# ---------------------------------------------------------------------------
# Tools — licensing contracts (written by the Legal clearance agent).
# ---------------------------------------------------------------------------
@mcp.tool()
def upsert_contract(contract_json: str) -> str:
    """Create or update a licensing contract (vendor × character × category × territory).
    `contract_json` is a JSON object; required: `vendor_id`, `character_id`, `category`,
    `territory`. `contract_id` (LC-####) is assigned if omitted. Returns the record."""
    try:
        data = json.loads(contract_json)
        assert isinstance(data, dict)
    except (ValueError, AssertionError):
        return json.dumps({"error": "contract_json must be a JSON object."})
    for req in ("vendor_id", "character_id", "category", "territory"):
        if not data.get(req):
            return json.dumps({"error": f"Missing required field: {req!r}."})
    cid = (data.get("contract_id") or "").strip().upper()
    if not cid:
        # Random 6-digit serial (not a per-process counter): the store is in-memory,
        # so a counter re-issues LC-6001 after every restart — ids must stay unique
        # across restarts for the audit history to make sense.
        while True:
            cid = f"LC-{random.randint(100000, 999999)}"
            if cid not in _CONTRACTS:
                break
    record = {**_CONTRACTS.get(cid, {}), **data, "contract_id": cid,
              "status": data.get("status", "executed")}
    _CONTRACTS[cid] = record
    return json.dumps({"upserted": True, "contract": record})


@mcp.tool()
def get_contract(contract_id: str) -> str:
    """Fetch a licensing contract by id (LC-####)."""
    c = _CONTRACTS.get((contract_id or "").strip().upper())
    return json.dumps(c or {"error": f"Contract {contract_id!r} not found."})


def _expected_deal(card: dict, category: str, territory: str, volume: float, net_unit_price: float) -> dict:
    """Deterministic Step-2 pricing math — the SINGLE source of truth for the expected deal.
    rate card + deal basis -> effective royalty rate, projected royalty, minimum guarantee,
    advance. Kept out of the LLM so the arithmetic (tier lookup, clamp, multiplies) is exact."""
    cat = (category or "").strip().lower()
    terr = (territory or "").strip().lower()
    cat_mod = card.get("category_modifier", {}).get(cat, 1.0)
    terr_mod = card.get("territory_modifier", {}).get(terr, 1.0)
    vol_mult = 1.0
    for tier in sorted(card.get("volume_discount_tiers", []), key=lambda t: t.get("min_units", 0)):
        if volume >= tier.get("min_units", 0):
            vol_mult = tier.get("mult", 1.0)
    effective_rate = max(card.get("base_royalty_rate", 0.0) * cat_mod * terr_mod * vol_mult,
                         card.get("min_royalty_rate", 0.0))
    royalty = effective_rate * net_unit_price * volume
    mg_rule = card.get("mg_rule", {})
    mg = max(mg_rule.get("floor_usd", 0.0), mg_rule.get("pct_of_projected_royalty", 0.0) * royalty)
    advance = card.get("advance_rule", {}).get("pct_of_mg", 0.0) * mg
    return {
        "effective_rate": round(effective_rate, 4),
        "category_mult": cat_mod, "territory_mult": terr_mod, "volume_mult": vol_mult,
        "royalty": round(royalty, 2), "mg": round(mg, 2), "advance": round(advance, 2),
    }


@mcp.tool()
def get_license_pricing(
    character_id: Annotated[str, Field(description='Licensed character/property to price, e.g. "minions" (case-insensitive).')],
    product_category: Annotated[str, Field(description='Manufactured product category, e.g. "Apparel", "Collectibles".')] = "",
    territory: Annotated[str, Field(description='Target territory, e.g. "Europe".')] = "",
    volume: Annotated[float, Field(description='Projected annual production units. When >0 (with net_unit_price), the tool also returns the computed EXPECTED deal.')] = 0.0,
    net_unit_price: Annotated[float, Field(description='Wholesale/net price per unit ($) — the royalty basis; needed to compute the expected deal.')] = 0.0,
) -> str:
    """Return the licensor's rate card for a property AND — when `volume` + `net_unit_price`
    are given — the DETERMINISTICALLY-COMPUTED expected deal (effective_rate, royalty, minimum
    guarantee, advance). The deal_pricing agent compares the vendor's AGREED royalty/advance/MG
    against this `expected` block; it must NOT recompute the arithmetic itself."""
    card = _RATE_CARDS.get((character_id or "").strip().lower())
    if not card:
        return json.dumps({"found": False, "character_id": character_id,
                           "message": f"No rate card on file for {character_id!r}."})
    out = {"found": True, **card}
    if volume and net_unit_price:
        out["expected"] = _expected_deal(card, product_category, territory, volume, net_unit_price)
    return json.dumps(out)


if __name__ == "__main__":
    # stdio for local agent-spawned use; streamable-http when run as a service.
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "9002"))
        from mcp.server.transport_security import TransportSecuritySettings
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        # Cloud-only OTel tracing (Cloud Trace + Application Topology node);
        # no-op locally and without the otel packages.
        from vibeflix_common.mcpserver.otel import setup_otel
        setup_otel(os.environ.get("K_SERVICE", "mcp_licensing"))
        mcp.run(transport=transport)

"""Vendor & Licensing Clearance Registry — MCP server.

The data backbone for the `vendor_clearance` agent. Holds three stores and exposes
tools to read, search, create and update them:

  * VENDORS      — approved manufacturing partners (who they are, where they may
                   operate, what they can make, capacity, certifications, status).
  * TRADEMARKS   — IP/trademark registrations per character/mark (owner, classes,
                   per-jurisdiction status, customs recordation, renewal).
  * EXCLUSIVITY  — active exclusivity contracts that lock a product category to a
                   partner in a territory (the "Hasbro blocks NA vinyl figures" rule).

STORAGE: plain in-memory dicts, seeded with realistic sample data. They are
*writable* (create/update mutate them), which is exactly why this isn't the
read-only Firestore `registry_get` used elsewhere. Caveat — in-memory means
per-process, single-instance, and reset on restart; a production deployment would
back these with Firestore/Postgres behind the same tool surface.
"""

import os
import json
import copy
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Vendor & Licensing Clearance Registry")

# Seed data lives in data.py (keeps this file focused on the tools).
from data import _VENDORS, _TRADEMARKS, _EXCLUSIVITY, _CONTRACTS

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
    vendor = _VENDORS.get((vendor_id or "").strip().upper())
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
        v for v in _VENDORS.values()
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
    vid = (data.get("vendor_id") or "").strip().upper()
    if not vid:
        nums = [int(k.split("-")[1]) for k in _VENDORS if k.startswith("VND-")]
        vid = f"VND-{(max(nums) + 1) if nums else 1001}"
    if vid in _VENDORS:
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
    _VENDORS[vid] = record
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
    if vid not in _VENDORS:
        return json.dumps({"error": f"Vendor {vendor_id!r} not found."})
    try:
        updates = json.loads(updates_json)
        assert isinstance(updates, dict)
    except (ValueError, AssertionError):
        return json.dumps({"error": "updates_json must be a JSON object."})
    record = copy.deepcopy(_VENDORS[vid])
    updates.pop("vendor_id", None)  # id is immutable
    record.update(updates)
    _VENDORS[vid] = record
    return json.dumps({"updated": True, "changed": sorted(updates), "vendor": record})


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
    lock on this character's product category in this territory (e.g. Hasbro on
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
    vendor = _VENDORS.get(vid)
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
        nums = [int(k.split("-")[1]) for k in _CONTRACTS if k.startswith("LC-")]
        cid = f"LC-{(max(nums) + 1) if nums else 6001}"
    record = {**_CONTRACTS.get(cid, {}), **data, "contract_id": cid,
              "status": data.get("status", "executed")}
    _CONTRACTS[cid] = record
    return json.dumps({"upserted": True, "contract": record})


@mcp.tool()
def get_contract(contract_id: str) -> str:
    """Fetch a licensing contract by id (LC-####)."""
    c = _CONTRACTS.get((contract_id or "").strip().upper())
    return json.dumps(c or {"error": f"Contract {contract_id!r} not found."})


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
        mcp.run(transport=transport)

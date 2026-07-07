import os
import sys
import json

from spellchecker import SpellChecker
from mcp.server.fastmcp import FastMCP

# Brand Style Compliance Registry — fully deterministic, no LLM. Exposes the whole
# brand-compliance pipeline as ONE tool (`run_brand_audit`); the individual checks
# below are internal steps that the tool assembles in a fixed order. The agent's
# job is only to extract the inputs and call the workflow — it does not orchestrate
# the checks itself.
mcp = FastMCP("Brand Style Compliance Registry")


# ===========================================================================
# Internal deterministic checks (not exposed as tools — steps of the pipeline)
# ===========================================================================
from vibeflix_common.registry import registry_get

_spell = SpellChecker()

# Registries: sourced from Firestore when FIRESTORE_DATABASE is set, else the
# hardcoded defaults below (so the server is self-contained without Firestore).
# Brand / franchise terms a general dictionary would wrongly flag.
_BRAND_ALLOWLIST_DEFAULT = [
    "grogu", "mandalorian", "mando", "din", "djarin", "skywalker", "vibeflix",
    "funko", "pop", "vinyl", "sku", "starwars", "yoda",
    "boba", "fett", "ahsoka", "tano", "obi", "wan", "kenobi", "vader",
]
_ALLOWED_PRINTED_MEDIA_DEFAULT = [
    "vinyl figure box", "poster", "trading card", "apparel tag",
    "sticker sheet", "art print", "enamel pin card", "mug wrap", "T-shirt", "book cover", "comic book cover", "magazine cover",
    "shoes", "hat", "hoodie", "jacket", "backpack", "lunchbox", "water bottle", "phone case", "tablet case", "laptop sleeve",
]
_APPROVED_ASSET_SOURCES_DEFAULT = [
    "gs://vibeflix-approved-assets/",
    "gs://vibeflix-licensing/",
    "gs://vibeflix-request-image/",  # vendor uploads from the console
    "https://assets.vibeflix.com/",
]

_BRAND_ALLOWLIST = set(registry_get("brand_style_registry", "brand_terms", _BRAND_ALLOWLIST_DEFAULT, field="items"))
_ALLOWED_PRINTED_MEDIA = registry_get("brand_style_registry", "printed_media", _ALLOWED_PRINTED_MEDIA_DEFAULT, field="items")
_APPROVED_ASSET_SOURCES = registry_get("brand_style_registry", "approved_sources", _APPROVED_ASSET_SOURCES_DEFAULT, field="items")


def _words(text_arg: str):
    """Yield alphabetic words from a JSON array string or a plain string."""
    try:
        parsed = json.loads(text_arg)
        lines = parsed if isinstance(parsed, list) else [str(parsed)]
    except (ValueError, TypeError):
        lines = [text_arg]
    for line in lines:
        for raw in str(line).split():
            w = "".join(ch for ch in raw if ch.isalpha())
            if w:
                yield w


def _check_typos(text: str) -> dict:
    """Deterministic spellcheck over the printed copy; brand terms allow-listed."""
    findings = []
    seen = set()
    for w in _words(text or ""):
        if len(w) < 3:
            continue
        lw = w.lower()
        if lw in _BRAND_ALLOWLIST or lw in seen:
            continue
        if _spell.unknown([lw]):
            seen.add(lw)
            candidates = sorted(_spell.candidates(lw) or [])[:3]
            findings.append({
                "element_id": f"typo_{lw}",
                "issue_type": "typo",
                "severity": "warning",
                "word": w,
                "suggestions": candidates,
                "description": f"Possible misspelling '{w}'. Did you mean: {_spell.correction(lw)}?",
            })
    return {"check": "typo", "status": "flagged" if findings else "clean", "findings": findings}


def _norm_medium(s: str) -> str:
    """Normalize a medium name for matching: lowercase, alphanumerics only
    (so 'T-Shirt' / 't shirt' / 'tshirt' all compare equal)."""
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _check_printed_medium(medium: str) -> dict:
    """Categorize the observed medium against the approved allowlist (forgiving
    normalized contains-match). On a match, `medium_category` names the canonical
    approved medium it was categorized as."""
    m = _norm_medium(medium)
    if not m:
        return {"check": "printed_medium", "status": "unknown", "findings": [{
            "element_id": "printed_medium", "issue_type": "missing_medium",
            "severity": "warning", "description": "No printed medium was identified.",
        }]}
    for a in _ALLOWED_PRINTED_MEDIA:
        na = _norm_medium(a)
        if na in m or m in na:
            return {"check": "printed_medium", "status": "approved",
                    "medium_category": a, "findings": []}
    return {"check": "printed_medium", "status": "flagged", "findings": [{
        "element_id": "printed_medium", "issue_type": "unapproved_medium",
        "severity": "critical",
        "description": (
            f"Printed medium '{medium}' is not on the approved list: "
            f"{', '.join(_ALLOWED_PRINTED_MEDIA)}."
        ),
    }]}


def _check_asset_source(image_uri: str) -> dict:
    """Deterministic image-link provenance check against approved sources."""
    uri = (image_uri or "").strip()
    if not uri:
        return {"check": "asset_source", "status": "unknown", "findings": [{
            "element_id": "asset_source", "issue_type": "missing_asset_link",
            "severity": "warning",
            "description": "No image link supplied. Provide a Cloud Storage URI (gs://…) or approved URL.",
        }]}
    if any(uri.startswith(prefix) for prefix in _APPROVED_ASSET_SOURCES):
        return {"check": "asset_source", "status": "approved", "findings": []}
    return {"check": "asset_source", "status": "flagged", "findings": [{
        "element_id": "asset_source", "issue_type": "unapproved_source",
        "severity": "critical",
        "description": (
            f"Image link '{uri}' is not from an approved source: "
            f"{', '.join(_APPROVED_ASSET_SOURCES)}."
        ),
    }]}


# ===========================================================================
# The workflow — one tool that assembles the fixed deterministic pipeline
# ===========================================================================
@mcp.tool()
def run_brand_audit(text: str, medium: str, image_uri: str) -> str:
    """
    Run the full deterministic brand-compliance pipeline in one call and return the
    merged result. The agent extracts the inputs and calls this once — it does NOT
    orchestrate the individual checks.

    The asset-source check is a GATE: if the image link is not from an approved
    source, the pipeline FAILS FAST with status 'rejected' and skips the content
    checks (auditing the contents of an untrusted asset is pointless). The agent
    should then ask the user to supply an approved image.

    Args:
        text: the mockup's printed copy (a JSON array of strings or a plain string).
        medium: the product medium as observed/classified from the mockup image, or
            as explicitly stated by the vendor (e.g. 'vinyl figure box'). It is
            categorized here against the approved-media registry.
        image_uri: the image's storage link (e.g. a Cloud Storage gs:// URI).

    Returns JSON: {audit, status, checks{...}, checks_run[...], findings[...],
    medium_category}. `medium_category` is the canonical approved medium the input
    was categorized as (absent if it matched none). status is 'rejected' (gate
    failed), 'flagged' (issues found), or 'compliant'.
    """
    # Gate: the asset source must be approved before we audit its contents.
    src = _check_asset_source(image_uri)
    if src["status"] != "approved":
        return json.dumps({
            "audit": "brand_compliance",
            "status": "rejected",
            "gate": "asset_source",
            "checks": {"asset_source": src["status"]},
            "checks_run": ["asset_source"],
            "findings": src["findings"],
            "message": "Asset source not approved — content checks were skipped.",
        })

    # Source approved → run the content checks.
    medium_step = _check_printed_medium(medium)
    steps = [_check_typos(text), medium_step]
    findings = [f for step in steps for f in step["findings"]]
    checks = {"asset_source": "approved"}
    checks.update({step["check"]: step["status"] for step in steps})
    result = {
        "audit": "brand_compliance",
        "status": "flagged" if findings else "compliant",
        "checks": checks,
        "checks_run": ["asset_source", "typo", "printed_medium"],
        "findings": findings,
    }
    if medium_step.get("medium_category"):
        result["medium_category"] = medium_step["medium_category"]
    return json.dumps(result)


if __name__ == "__main__":
    # stdio for local agent-spawned use; streamable-http when run as a service.
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "9004"))
        # Internal mesh: agents reach this server by service name (not localhost),
        # so the Host header isn't localhost — disable MCP DNS-rebinding protection
        # (else the streamable-http handshake returns 421 Misdirected Request).
        from mcp.server.transport_security import TransportSecuritySettings
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mcp.run(transport=transport)

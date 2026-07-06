import os
import sys
import json

from mcp.server.fastmcp import FastMCP

# Vision & UI Services — fully deterministic, no LLM. Provides the mockup parse
# (used by the brand_style agent as an extraction fallback) and the A2UI canvas
# helpers. The branding compliance checks live in the separate mcp_brand_style
# server.
mcp = FastMCP("Vision & UI Services")


def _parse(image_path: str) -> dict:
    """Deterministic structural parse of a mockup (canned CV stub)."""
    return {
        "status": "success",
        "image_file": os.path.basename(image_path) if image_path else "",
        "detected_logos": ["star_wars_logo", "pop_vinyl_tag"],
        "extracted_text": [
            {"text": "STAR WARS", "font": "Outfit-Bold", "color": "#10b981"},
            {"text": "POP SERIES #339", "font": "Outfit-Light", "color": "#94a3b8"},
            {"text": "THE CHILD", "font": "SpaceGrotesk", "color": "#ffffff"},
            {"text": "LIMITED EDTION", "font": "SpaceGrotesk", "color": "#ffffff"},  # demo typo trigger
        ],
        "printed_medium": "vinyl figure box",
        "primary_colors": ["#10b981", "#0f172a", "#ffffff"],
    }


@mcp.tool()
def parse_design_elements(image_path: str) -> str:
    """
    Deterministic structural parse of a mockup: text elements (+font/color),
    detected logos, the printed medium, and the primary color palette. The
    branding agent can use this to obtain the copy/medium when it isn't given an
    actual image to read.
    """
    return json.dumps(_parse(image_path))


@mcp.tool()
def deploy_audit_canvas(json_schema: str) -> str:
    """
    Sends a dynamic configuration schema directly to the browser workspace
    to draw layouts, form elements, and maps.
    """
    layout = json.loads(json_schema)
    return json.dumps({
        "status": "deployed",
        "canvas_id": "audit_canvas_workspace_01",
        "components_registered": len(layout.get("components", []))
    })


@mcp.tool()
def flash_threat_vector(element_id: str, severity: str, descriptive_text: str) -> str:
    """
    Target-updates a component on the active layout canvas
    (e.g., coloring a text field red and attaching an error bubble).
    """
    return json.dumps({
        "status": "highlighted",
        "target_element": element_id,
        "severity": severity,
        "descriptive_text": descriptive_text
    })


if __name__ == "__main__":
    # stdio for local agent-spawned use; streamable-http when run as a service.
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "9001"))
        # Internal mesh: agents reach this server by service name (not localhost),
        # so the Host header isn't localhost — disable MCP DNS-rebinding protection
        # (else the streamable-http handshake returns 421 Misdirected Request).
        from mcp.server.transport_security import TransportSecuritySettings
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mcp.run(transport=transport)

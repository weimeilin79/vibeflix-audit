import os
import sys
import json
import time
from mcp.server.fastmcp import FastMCP

from vibeflix_common.registry import registry_get

mcp = FastMCP("Market Operations & Telemetry")

# Live mesh telemetry: every tool emits started/completed/failed onto PUBSUB_TOPIC
# (no-op when unset) — drives the Workflow graph's tool LEDs. Hooked at
# registration, so new tools are instrumented automatically.
from vibeflix_common.telemetry import instrument_fastmcp
instrument_fastmcp(mcp, source="mcp_market")

@mcp.tool()
def scan_ecom_marketplaces(character_id: str, region: str) -> str:
    """
    Scrapes active listings across global storefronts (Alibaba, eBay, Taobao) 
    to spot early product leaks or unauthorized pre-orders.
    """
    # Simulate scrapers checking listings
    return json.dumps({
        "character_id": character_id,
        "region": region,
        "platforms_scraped": ["Alibaba", "eBay", "Taobao", "Mercari"],
        "suspicious_listings_found": 0,
        "status": "Secure - No leaked pre-orders found for this SKU prototype design."
    })

@mcp.tool()
def check_sku_volume_caps(contract_id: str) -> str:
    """
    Checks the volume fields of the active production request against the 
    upper limits agreed upon in the master contract.
    """
    # Contract volume limits — from Firestore policy when configured, else default.
    fallback = {
        "contract_id": contract_id,
        "authorized_max_skus": 25000,
        "current_sourcing_cap_rules": "Volume overrides > 25,000 trigger structural splitter agent workflows to split capacity into distinct addendums.",
    }
    caps = registry_get("market_policy", "sourcing_caps", fallback)
    caps["contract_id"] = contract_id
    return json.dumps(caps)

@mcp.tool()
def capture_audit_map(interaction_payload: str) -> str:
    """
    Permanently writes the timeline of user cursor movements, field adjustments, 
    and agent decisions directly to the episodic memory store.
    """
    # Simulation: Log user adjustments, clicks, hover and telemetry
    log_entry = {
        "timestamp": time.time(),
        "payload": json.loads(interaction_payload),
        "status": "Saved to Episodic Memory Store"
    }
    # In a real environment, this might write to a database or local JSON log.
    return json.dumps(log_entry)

if __name__ == "__main__":
    # stdio for local agent-spawned use; streamable-http when run as a service.
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "9003"))
        # Internal mesh: agents reach this server by service name (not localhost),
        # so the Host header isn't localhost — disable MCP DNS-rebinding protection
        # (else the streamable-http handshake returns 421 Misdirected Request).
        from mcp.server.transport_security import TransportSecuritySettings
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        # Cloud-only OTel tracing (Cloud Trace + Application Topology node);
        # no-op locally and without the otel packages.
        from vibeflix_common.otel import setup_otel
        setup_otel(os.environ.get("K_SERVICE", "mcp_market"))
        mcp.run(transport=transport)

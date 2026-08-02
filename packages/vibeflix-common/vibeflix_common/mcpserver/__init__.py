"""MCP server — helpers only the FastMCP servers use.

    otel.py   OpenTelemetry tracing for the MCP servers (cloud-only)

Imported by: mcp_servers/ only.

Small on purpose. If you are looking for the Firestore registry reads, they are in
`platform/registry.py` — the orchestrator reads the same doc mcp_market does, so it is
not MCP-server-only. Telemetry is in `platform/telemetry.py` for the same reason
(`instrument_node` for agents, `instrument_fastmcp` for servers).
"""

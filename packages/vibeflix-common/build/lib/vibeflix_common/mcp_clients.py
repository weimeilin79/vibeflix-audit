"""Connect ADK agents to the decoupled MCP servers over the network.

In the distributed deployment each MCP group runs as its own service (its own
container / Cloud Run instance) speaking MCP over streamable-HTTP. Agents reach
them by URL, supplied per group via environment variables:

    MCP_LICENSING_URL   e.g. http://mcp_licensing:9002/mcp
    MCP_MARKET_URL      e.g. http://mcp_market:9003/mcp
"""

import os

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

# Env var holding the URL for each MCP server group.
_URL_ENV = {
    "mcp_brand_style": "MCP_BRAND_STYLE_URL",
    "mcp_licensing": "MCP_LICENSING_URL",
    "mcp_market": "MCP_MARKET_URL",
}


def mcp_toolset(group: str, tool_filter: list[str] | None = None) -> McpToolset:
    """Build an ``McpToolset`` bound to one remote MCP server group.

    Args:
        group: one of ``mcp_brand_style`` / ``mcp_licensing`` / ``mcp_market``.
        tool_filter: optional allow-list of tool names to expose to the agent.
    """
    env = _URL_ENV.get(group)
    if env is None:
        raise ValueError(f"Unknown MCP group: {group!r}")
    url = os.environ.get(env)
    if not url:
        raise RuntimeError(
            f"MCP URL not configured for {group}: set the {env} environment variable "
            f"(e.g. http://{group}:9001/mcp)."
        )
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=url),
        tool_filter=tool_filter,
    )

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

from vibeflix_common.cloud_auth import run_local, mcp_httpx_factory, prewarm_id_token

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
    # RUN_LOCAL=false (cloud): every connection the toolset opens attaches a
    # fresh Google ID token — Cloud Run / Agent Gateway MCP endpoints are IAM-gated.
    #
    # timeout: ADK applies StreamableHTTPConnectionParams.timeout to the WHOLE
    # handshake (mcp_toolset._execute_with_session wraps list_tools in
    # asyncio.wait_for). Its default is 5s, which an agent-identity engine cannot
    # meet on a cold connection: before it can even say hello it must mint an
    # impersonated ID token, and that call is itself routed through the governed
    # gateway. Blowing the 5s budget surfaces as `TimeoutError` inside an opaque
    # "Failed to create MCP session: unhandled errors in a TaskGroup" — which
    # looks exactly like an auth failure and sent us chasing 401s. 60s is slack,
    # not latency: once the token is cached the handshake is fast.
    params = (
        StreamableHTTPConnectionParams(url=url)
        if run_local()
        else StreamableHTTPConnectionParams(
            url=url, httpx_client_factory=mcp_httpx_factory, timeout=60.0)
    )
    if not run_local():
        prewarm_id_token(url)  # pay the impersonation cost at import, not mid-audit
    return McpToolset(connection_params=params, tool_filter=tool_filter)

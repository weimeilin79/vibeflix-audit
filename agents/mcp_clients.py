"""Shared helpers for connecting ADK agents to the decoupled MCP servers.

Each domain server under ``mcp_servers/`` is a standalone FastMCP process. ADK
agents reach them over stdio with ``McpToolset`` (one toolset per server group),
which spawns ``python <server>/server.py`` and speaks MCP on the pipe.
"""

import os
import sys

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Absolute repo paths — StdioServerParameters requires absolute, not relative.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_MCP_DIR = os.path.join(_REPO_ROOT, "mcp_servers")


def _server_path(group: str) -> str:
    return os.path.join(_MCP_DIR, group, "server.py")


def mcp_toolset(group: str, tool_filter: list[str] | None = None) -> McpToolset:
    """Build an ``McpToolset`` bound to one decoupled MCP server group.

    Args:
        group: directory name under ``mcp_servers/`` (e.g. ``"mcp_legal"``).
        tool_filter: optional allow-list of tool names to expose to the agent.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[_server_path(group)],
            ),
        ),
        tool_filter=tool_filter,
    )

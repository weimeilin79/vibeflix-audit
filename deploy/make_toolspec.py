"""Generate an Agent-Registry MCP tool spec from a live MCP server.

The registry's `--mcp-server-spec-content` wants the server's tool inventory
(the codelab ships hand-written src/*/toolspec.json files); this asks the
server itself via list_tools so the spec never drifts from the code.

Usage:  python deploy/make_toolspec.py <mcp_url> > toolspec.json
"""

import asyncio
import json
import sys

sys.path.insert(0, ".")
from vibeflix_common.cloud_auth import auth_headers  # noqa: E402


async def main(url: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url, headers=auth_headers(url)) as (r, w, _):
        async with ClientSession(r, w) as s:
            info = await s.initialize()
            tools = (await s.list_tools()).tools
    spec = {
        "name": info.serverInfo.name,
        "tools": [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema,
                **({"annotations": t.annotations.model_dump(exclude_none=True)}
                   if getattr(t, "annotations", None) else {}),
            }
            for t in tools
        ],
    }
    print(json.dumps(spec, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))

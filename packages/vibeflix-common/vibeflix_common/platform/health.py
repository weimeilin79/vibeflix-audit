"""Mesh health probes — the handshake-level check that a `None` report can't give.

An agent's A2A card serves fine even when its MCP tools are dead (the exact
failure that surfaced as a silent `None` in a report). So the real readiness
signal is: can the agent open an MCP session and list tools? This module does
that handshake against every ``MCP_*_URL`` in the environment.
"""

import asyncio
import os


# The MCP servers run on Cloud Run with no minimum instances, so the first
# handshake after an idle period pays a full cold start — container pull, uvicorn
# boot, FastMCP init — before `initialize` even gets a reply. Five seconds did not
# cover that, so a perfectly healthy server reported `TimeoutError` and the console
# painted every MCP node red while real tool calls were succeeding. A probe that
# cries wolf on a cold start is worse than no probe.
_PROBE_TIMEOUT = float(os.environ.get("MCP_PROBE_TIMEOUT", "20"))


async def _probe_one(url: str, timeout: float | None = None) -> dict:
    """Open a streamable-http MCP session and list tools; return {ok, detail}.

    Retries once on timeout: the first attempt is what wakes a scaled-to-zero
    server, so the retry is the one that measures a running service.
    """
    timeout = _PROBE_TIMEOUT if timeout is None else timeout

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    from vibeflix_common.platform.cloud_auth import auth_headers

    async def _go() -> int:
        async with streamablehttp_client(url, headers=auth_headers(url)) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                return len(listed.tools)

    last = "no attempt"
    for attempt in (1, 2):
        try:
            count = await asyncio.wait_for(_go(), timeout=timeout)
            warmed = " (after warm-up)" if attempt == 2 else ""
            return {"ok": True, "detail": f"{count} tools{warmed}"}
        except asyncio.TimeoutError:
            last = f"TimeoutError: no MCP handshake within {timeout:g}s"
            continue  # first attempt may have been spent on a cold start
        except Exception as e:  # connection/handshake — real, don't retry
            return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:140]}"}
    return {"ok": False, "detail": last}


async def probe_mcp_from_env() -> list[dict]:
    """Handshake every ``MCP_*_URL`` env var; return [{name, url, ok, detail}].

    Empty list when the agent has no MCP deps (e.g. ui_renderer) → treated as OK.
    """
    keys = sorted(
        k for k in os.environ
        if k.startswith("MCP_") and k.endswith("_URL") and os.environ.get(k)
    )
    results = await asyncio.gather(*(_probe_one(os.environ[k]) for k in keys))
    return [{"name": k, "url": os.environ[k], **r} for k, r in zip(keys, results)]


def banner(agent: str, mcp: list[dict]) -> str:
    """A human-readable startup banner for the MCP check."""
    if not mcp:
        return f"[serve_a2a:{agent}] MCP check: (no MCP dependencies)"
    lines = [f"[serve_a2a:{agent}] MCP check:"]
    for m in mcp:
        mark = "OK  " if m["ok"] else "FAIL"
        lines.append(f"  {mark} {m['name']:<20} {m['url']}  ({m['detail']})")
    return "\n".join(lines)

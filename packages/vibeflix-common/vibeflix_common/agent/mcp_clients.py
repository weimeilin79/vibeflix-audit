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

from vibeflix_common.platform.cloud_auth import (
    run_local, mcp_httpx_factory, prewarm_id_token, mcp_auth_header)

# Env var holding the URL for each MCP server group.
_URL_ENV = {
    "mcp_brand_style": "MCP_BRAND_STYLE_URL",
    "mcp_licensing": "MCP_LICENSING_URL",
    "mcp_market": "MCP_MARKET_URL",
}


def _disable_adk_mcp_mtls() -> None:
    """Stop ADK from hijacking MCP auth with the agent's ACCESS token.

    ROOT CAUSE (confirmed): `MCPSessionManager._get_mtls_transport` builds an mTLS transport
    whenever GOOGLE_API_USE_CLIENT_CERTIFICATE != "false" (its default "true"; we keep it UNSET
    so the SESSION service gets bound tokens). That transport authenticates via
    google-auth-aio's AsyncAuthorizedSession using `google.auth.default().token` — the AGENT'S
    ACCESS token — and REPLACES our httpx_client_factory, so our audience-bound ID-token logic
    never runs for MCP. Cloud Run REMOTELY verifies access tokens (token introspection), which
    flakes under the concurrent agent fan-out → the intermittent `401 "access token could not
    be verified"` that fails a tool-load and hangs the run. (Injecting our token via the
    header_provider did NOT help — the mTLS/AsyncAuthorizedSession path doesn't honor it.)

    Our MCP servers are plain IAM-gated Cloud Run (bearer token over the governed gateway), NOT
    mutual-TLS endpoints — so the mTLS transport is unnecessary. Neutering `_get_mtls_transport`
    makes ADK fall back to `_connection_params.httpx_client_factory` = our `mcp_httpx_factory`
    (GoogleAuth → LOCALLY-verified ID token via Proxy-Authorization + Authorization). The
    SESSION service uses google.auth directly and never touches this, so bound tokens are
    unaffected — no flag change, both needs satisfied.
    """
    try:
        from google.adk.tools.mcp_tool.mcp_session_manager import MCPSessionManager

        async def _no_mtls(self):  # noqa: ANN001 — matches _get_mtls_transport(self)
            return None

        MCPSessionManager._get_mtls_transport = _no_mtls
        print("[mcp] ADK mtls transport DISABLED → MCP uses our ID-token httpx factory",
              flush=True)
    except Exception as e:  # noqa: BLE001 — never break import; worst case we keep the bug
        print(f"[mcp] could not disable ADK mtls transport: {type(e).__name__}: {e}", flush=True)


if not run_local():
    _disable_adk_mcp_mtls()


def _log_leaf_exceptions(exc, group: str, _seen=None, _depth=0) -> None:
    """Unmask the REAL socket exception behind a failed MCP session.

    mcp/ADK create the session inside an asyncio TaskGroup AND then re-raise the group as
    a flat `ConnectionError(str(group))` — so `.exceptions` is already gone by the time we
    catch it and only the string `…unhandled errors in a TaskGroup (1 sub-exception)`
    remains. BUT Python preserves the original under `__context__` (auto-set when you raise
    inside an `except`) and/or `__cause__` (`raise … from`). So to reach the true leaf
    (`httpx.ConnectError` / `RemoteProtocolError` / `ReadError` / `TimeoutError`) we must
    follow BOTH `.exceptions` (group) AND the `__cause__`/`__context__` chain.
    """
    if _seen is None:
        _seen = set()
    if id(exc) in _seen or _depth > 15:
        return
    _seen.add(id(exc))

    subs = getattr(exc, "exceptions", None)          # ExceptionGroup / BaseExceptionGroup
    chain = [e for e in (getattr(exc, "__cause__", None),
                         getattr(exc, "__context__", None)) if e is not None]

    if subs:
        for s in subs:
            _log_leaf_exceptions(s, group, _seen, _depth + 1)
    elif chain:
        # not a group, but a wrapped exception — record this frame and follow the chain
        print(f"[mcp] {group} tool-load chain[{_depth}]: "
              f"{type(exc).__module__}.{type(exc).__name__}: {str(exc)[:120]}", flush=True)
        for nxt in chain:
            _log_leaf_exceptions(nxt, group, _seen, _depth + 1)
    else:
        print(f"[mcp] {group} tool-load REAL CAUSE (leaf): "
              f"{type(exc).__module__}.{type(exc).__name__}: {exc}", flush=True)


class _DiagnosticMcpToolset(McpToolset):
    """McpToolset that unmasks the swallowed sub-exception when tool-loading fails."""

    def __init__(self, *args, _group: str = "?", **kwargs):
        self._group = _group
        super().__init__(*args, **kwargs)

    async def get_tools(self, readonly_context=None):
        try:
            return await super().get_tools(readonly_context)
        except BaseException as e:  # noqa: BLE001 — log the real cause, then re-raise as-is
            _log_leaf_exceptions(e, self._group)
            raise


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
    # header_provider: a now-REDUNDANT secondary guard. The real fix is
    # _disable_adk_mcp_mtls() above — with ADK's mtls transport gone, our
    # httpx_client_factory (mcp_httpx_factory → GoogleAuth) sets the audience-bound
    # ID token itself, so this belt-and-suspenders header rarely matters. Kept as
    # defense if a future ADK version reintroduces a transport that ignores the
    # factory. Safe to drop for maximal cleanliness. None locally.
    header_provider = None if run_local() else (lambda _ctx, _u=url: mcp_auth_header(_u))
    return _DiagnosticMcpToolset(
        connection_params=params, tool_filter=tool_filter, _group=group,
        header_provider=header_provider)

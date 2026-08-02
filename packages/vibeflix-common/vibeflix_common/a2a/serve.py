"""Serve a single domain agent as a standalone A2A service.

Each domain agent (brand_style / vendor_clearance / deal_pricing / ui_renderer) runs in
its own container and exposes itself over the Agent-to-Agent (A2A) protocol so the
Sourcing Orchestrator can call it remotely. Driven by environment:

    A2A_AGENT     which agent package to serve: brand_style | vendor_clearance | deal_pricing | ui_renderer
    PORT          port to bind (Cloud Run injects this; default 8001)
    A2A_HOST      hostname advertised in the published agent card
                  (compose: the service name; Cloud Run: the *.run.app domain)
    A2A_PROTOCOL  http (default) or https (set https for Cloud Run)

Run:  python -m vibeflix_common.a2a.serve
"""

import asyncio
import importlib
import os

import uvicorn
from starlette.responses import JSONResponse
from starlette.routing import Route
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import InMemoryCredentialService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from vibeflix_common.platform.health import probe_mcp_from_env, banner

# `orchestrator` is here because it is an INDEPENDENT agent, not something the app
# hosts: the app is a thin A2A client in BOTH worlds (compose container :8006 / the
# vibeflix-orchestrator engine in cloud). This set used to omit it — back when the app
# imported root_agent and ran the workflow in-process.
_KNOWN = {"brand_style", "vendor_clearance", "deal_pricing", "ui_renderer", "legal",
          "orchestrator"}


def _runner_with_plugins(agent):
    """A Runner whose App carries ReflectAndRetryToolPlugin — so when a domain
    agent's TOOL call (e.g. an MCP tool) errors, the model reflects and retries it
    in place (tool-layer recovery), complementing the orchestrator's workflow-layer
    recovery node. No-op for the tool-less ui_renderer."""
    app = App(
        name=agent.name or "adk_agent",
        root_agent=agent,
        plugins=[ReflectAndRetryToolPlugin(max_retries=3)],
    )
    return Runner(
        app=app,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
        credential_service=InMemoryCredentialService(),
    )


def build_app():
    agent_name = os.environ.get("A2A_AGENT")
    if agent_name not in _KNOWN:
        raise RuntimeError(f"Set A2A_AGENT to one of {sorted(_KNOWN)} (got {agent_name!r}).")

    port = int(os.environ.get("PORT", "8001"))
    host = os.environ.get("A2A_HOST", agent_name)
    protocol = os.environ.get("A2A_PROTOCOL", "http")

    module = importlib.import_module(f"agents.{agent_name}.agent")
    agent = module.root_agent

    # `host`/`port`/`protocol` only shape the URL published in the agent card,
    # which is what the orchestrator (A2A client) uses to reach this service.
    # A custom runner carries the tool-retry plugin (to_a2a's default runner won't).
    a2a_app = to_a2a(agent, host=host, port=port, protocol=protocol,
                     runner=_runner_with_plugins(agent))

    # Layer 1 health gate: /healthz handshakes this agent's MCP servers live, so
    # the orchestrator's /api/ready can see a broken agent↔MCP link (which a
    # served agent card can't reveal). Non-fatal.
    async def _healthz(_request):
        mcp = await probe_mcp_from_env()
        return JSONResponse({"agent": agent_name, "ok": all(m["ok"] for m in mcp), "mcp": mcp})

    a2a_app.routes.append(Route("/healthz", _healthz, methods=["GET"]))

    async def _startup_check():
        # Retry to absorb parallel-boot warmup, then log a loud banner (once).
        mcp = []
        for _ in range(6):  # ~30s
            mcp = await probe_mcp_from_env()
            if not mcp or all(m["ok"] for m in mcp):
                break
            await asyncio.sleep(5)
        print(banner(agent_name, mcp), flush=True)
        if mcp and not all(m["ok"] for m in mcp):
            print(f"[serve_a2a:{agent_name}] ⚠️  MCP dependencies UNHEALTHY — this "
                  f"agent will return empty reports until they recover.", flush=True)

    # Run the banner check in the background at startup (non-blocking, so the
    # server accepts connections immediately). Register via the router's
    # on_startup list (portable across Starlette versions).
    async def _on_startup():
        asyncio.create_task(_startup_check())
    try:
        a2a_app.router.on_startup.append(_on_startup)
    except Exception:
        pass  # /healthz still works even if the boot banner can't be scheduled
    return a2a_app


# Module-level app so `uvicorn vibeflix_common.a2a.serve:app` also works.
app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8001")))

"""Resolve a cloud A2A agent through the Agent Registry (cloud-only).

In the cloud, domain agents run as Agent-Runtime engines that speak the
platform's REST/proto A2A dialect — a raw RemoteA2aAgent(agent_card=<url>) can't
reach them (no /a2a/v1/card route; JSON-RPC vs proto). The SDK's
`AgentRegistry.get_remote_a2a_agent()` returns a RemoteA2aAgent already wired to
the registered engine (registry lookup + correct client + agent-identity auth).

Callers gate on run_local(): local → the plain direct-URL RemoteA2aAgent
(unchanged compose behavior); cloud → registry_remote_agent().
"""

import os


def registry_remote_agent(adk_name: str, description: str, display_name: str,
                          httpx_client=None):
    """Return a RemoteA2aAgent for the registered agent whose registry
    displayName == display_name, with its `name` forced to `adk_name` so the
    orchestrator's workflow graph (which references agents by name) resolves."""
    from google.adk.integrations.agent_registry import AgentRegistry

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    # Registry is REGIONAL (us-central1) — NOT the Gemini `global` location.
    location = os.environ.get("AGENT_REGISTRY_LOCATION", "us-central1")
    reg = AgentRegistry(project_id=project, location=location)

    entries = reg.list_agents().get("agents", [])
    match = next((e for e in entries if e.get("displayName") == display_name), None)
    if not match:
        raise RuntimeError(
            f"Agent Registry has no entry named {display_name!r} "
            f"(project={project}, location={location}). Register it (step 4a-ii)."
        )
    # The A2A calls to the engine hit aiplatform.googleapis.com and need the
    # CALLER's own bearer token. get_remote_a2a_agent's default client uses
    # agent-identity auth, which yields 401 when the caller is a plain SA (the
    # console app). Attach a GoogleAuth client → the process's ADC access token
    # (works for the app SA AND for agent-identity engines).
    if httpx_client is None:
        from vibeflix_common.cloud_auth import GoogleAuth
        import httpx
        httpx_client = httpx.AsyncClient(auth=GoogleAuth(), timeout=300.0)
    agent = reg.get_remote_a2a_agent(match["name"], httpx_client=httpx_client)

    # Force the workflow-referenced name + our description (get_remote_a2a_agent
    # derives them from the card/displayName).
    updates = {"name": adk_name}
    if description:
        updates["description"] = description
    try:
        for k, v in updates.items():
            setattr(agent, k, v)
    except Exception:
        agent = agent.model_copy(update=updates)
    return agent

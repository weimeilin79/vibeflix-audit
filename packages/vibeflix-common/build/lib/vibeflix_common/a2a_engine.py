"""Direct REST/proto A2A client for Agent-Runtime engines (cloud).

Registry-based resolution (AgentRegistry.get_remote_a2a_agent) fails from a
GATEWAY-ATTACHED engine: it must call agentregistry.mtls to resolve, and that
outbound is gateway-filtered → 403 (agentregistry is the gateway's own
dependency; registering+granting it doesn't help). So instead we call the
target engine's A2A endpoint DIRECTLY:

    POST <engine_base>/a2a/v1/message:send   (proto-JSON body, ADC bearer)
    GET  <engine_base>/a2a/v1/tasks/{id}      (poll to completion)

This is INBOUND to the target engine (not gateway egress), so it works for any
caller with aiplatform access — the app SA and agent identities alike. The
gateway still governs the target engine's OWN outbound (agent→MCP tool policies),
which is the governance showcase.

`engine_base` is the reasoningEngine resource URL, e.g.
https://us-central1-aiplatform.googleapis.com/v1beta1/projects/…/reasoningEngines/ID
(the value already in BRAND_STYLE_A2A_URL etc.).
"""

import asyncio


async def a2a_engine_send(engine_base: str, text: str, timeout: float = 300.0) -> str:
    """Send one message to an engine's A2A endpoint and return the reply text.
    Runs SYNC requests in a worker thread — isolates the call from the ADK/OTel
    async context (contextvars Token errors) that break an in-node httpx client."""
    return await asyncio.to_thread(_send_sync, engine_base.rstrip("/"), text, timeout)


def _send_sync(base: str, text: str, timeout: float) -> str:
    import time as _time
    import google.auth
    import google.auth.transport.requests as _gar
    import requests

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(_gar.Request())
    hdr = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    body = {"message": {"role": "ROLE_USER", "messageId": "vibeflix",
                        "content": [{"text": text}]}}
    r = requests.post(f"{base}/a2a/v1/message:send", json=body, headers=hdr, timeout=60)
    r.raise_for_status()
    task = (r.json().get("task") or {})
    tid = task.get("id")
    state = (task.get("status") or {}).get("state")
    deadline = timeout
    while tid and state in ("TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", None) and deadline > 0:
        _time.sleep(5); deadline -= 5
        g = requests.get(f"{base}/a2a/v1/tasks/{tid}", params={"history_length": 50},
                         headers=hdr, timeout=60)
        if g.status_code in (400, 404):
            continue  # task briefly not visible / not-yet-queryable across instances
        g.raise_for_status()
        task = g.json()
        state = (task.get("status") or {}).get("state")
    return _extract_reply(task)


def _extract_reply(task: dict) -> str:
    """Pull the agent's reply text out of an A2A task (proto shape)."""
    for art in (task.get("artifacts") or []):
        for p in (art.get("parts") or []):
            if p.get("text"):
                return p["text"]
    # else the last non-user message in history
    for msg in reversed(task.get("history") or []):
        if msg.get("role") in ("ROLE_AGENT", "agent"):
            return "".join(p.get("text", "") for p in (msg.get("content") or msg.get("parts") or []))
    st = (task.get("status") or {}).get("message") or {}
    return "".join(p.get("text", "") for p in (st.get("content") or []))


def direct_engine_agent(name: str, description: str, engine_base: str):
    """A BaseAgent that runs a2a_engine_send and emits the reply as its event —
    so the orchestrator workflow can `ctx.run_node()` it exactly like a
    RemoteA2aAgent, but via the direct (gateway-free) path."""
    from google.adk.agents import BaseAgent
    from google.adk.events.event import Event
    from google.genai import types as _t

    class _DirectEngineAgent(BaseAgent):
        async def _run_async_impl(self, ctx):
            text = ""
            for ev in reversed(ctx.session.events):
                c = getattr(ev, "content", None)
                if c and getattr(c, "parts", None):
                    text = "".join(getattr(p, "text", "") or "" for p in c.parts)
                    if text:
                        break
            reply = await a2a_engine_send(engine_base, text)
            yield Event(author=self.name,
                        content=_t.Content(role="model", parts=[_t.Part(text=reply)]))

    return _DirectEngineAgent(name=name, description=description)

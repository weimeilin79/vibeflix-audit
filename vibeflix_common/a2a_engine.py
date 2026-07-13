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

    import os
    from vibeflix_common.cloud_auth import is_mtls_host, mtls_cert_files

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(_gar.Request())

    # TWO different parties need to authenticate this one request:
    #   Proxy-Authorization → the Agent Gateway (egress authorization, agent identity)
    #   Authorization       → the TARGET engine's aiplatform endpoint
    # This used to send ONLY Proxy-Authorization inside an engine, so Google's endpoint
    # saw no credential at all and answered 401 — which we spent a long time mistaking
    # for a missing client certificate.
    hdr = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "Connection": "close",
    }
    if os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
        hdr["Proxy-Authorization"] = f"Bearer {creds.token}"

    # The agent endpoints are REGISTERED with the mtls URL and the gateway only authorizes
    # the destination it has registered: a call to the PLAIN url is refused with
    # `403 Egress request is not authorized` even when that URL is added as an interface
    # AND the caller holds iap.egressor on the endpoint (measured, repeatedly). So we call
    # the mtls URL — and an mtls endpoint also wants the workload's CLIENT CERTIFICATE.
    cert = mtls_cert_files() if is_mtls_host(base) else None
    body = {"message": {"role": "ROLE_USER", "messageId": "vibeflix",
                        "content": [{"text": text}]}}
    url = f"{base}/a2a/v1/message:send"
    while True:
        with requests.Session() as s:
            r = s.post(url, json=body, headers=hdr, timeout=60, allow_redirects=False,
                       cert=cert)
        if r.status_code in (301, 302, 303, 307, 308):
            url = r.headers["Location"]
            continue
        break
    if r.status_code >= 400:
        print(f"DEBUG: message:send failed status={r.status_code} body={r.text}", flush=True)
    r.raise_for_status()
    task = (r.json().get("task") or {})
    tid = task.get("id")
    state = (task.get("status") or {}).get("state")
    deadline = timeout
    _RUNNING = ("TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", None)
    while tid and state in _RUNNING and deadline > 0:
        _time.sleep(5); deadline -= 5
        
        # Manually follow redirects for GET to keep auth headers
        url = f"{base}/a2a/v1/tasks/{tid}"
        params = {"history_length": 50}
        while True:
            with requests.Session() as s:
                g = s.get(url, params=params, headers=hdr, timeout=60, allow_redirects=False,
                          cert=cert)
            if g.status_code in (301, 302, 303, 307, 308):
                url = g.headers["Location"]
                params = None  # query parameters are already in the redirect URL
                continue
            break
            
        # 404 = task not yet visible on THIS engine replica (in-memory per-instance
        # task store, requests round-robin); keep polling — it lands on the owning
        # replica within a few tries. 400 during a run is the platform surfacing an
        # in-progress execution error; keep polling until the task reaches a
        # terminal state (FAILED), which we then report — don't silently drop it.
        if g.status_code in (400, 404):
            _time.sleep(2)
            deadline -= 2
            continue
        g.raise_for_status()
        task = g.json()
        state = (task.get("status") or {}).get("state")
    if state == "TASK_STATE_FAILED":
        return f"[A2A engine execution FAILED] {_status_error(task) or '(no detail)'}"
    return _extract_reply(task)


def _status_error(task: dict) -> str:
    """Any error/message text a FAILED task carries in its status."""
    st = (task.get("status") or {})
    msg = st.get("message") or {}
    parts = msg.get("content") or msg.get("parts") or []
    txt = "".join(p.get("text", "") for p in parts).strip()
    return txt or (st.get("error") or {}).get("message", "") or st.get("state", "")


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
            if ctx.user_content and ctx.user_content.parts:
                text = "".join(getattr(p, "text", "") or "" for p in ctx.user_content.parts)
            if not text:
                for ev in reversed(ctx.session.events):
                    c = getattr(ev, "content", None)
                    if c and getattr(c, "parts", None):
                        t = "".join(getattr(p, "text", "") or "" for p in c.parts)
                        if t and "__plan__" not in t:
                            text = t
                            break
            reply = await a2a_engine_send(engine_base, text)
            yield Event(author=self.name,
                        content=_t.Content(role="model", parts=[_t.Part(text=reply)]))

    return _DirectEngineAgent(name=name, description=description)

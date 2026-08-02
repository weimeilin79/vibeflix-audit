"""TEMPORARY EXPERIMENT — delete after the run.

THE QUESTION: from INSIDE a gateway-attached engine, which A2A call shape reaches another engine?

Round 3. Round 2 established (in-engine, full grants, control passing):
  · the documented AgentRegistry path RESOLVES fine          → the old "resolution 403s" was a grant gap
  · `Proxy-Authorization` is NOT required                    → mtls + Authorization alone = 200
  · the PLAIN host is refused even with both headers         → the host matters
  · `_genai` 403s while a raw `message:send` succeeds        → same host, same header ⇒ the PATH differs

Round 2's `_genai` calls went to **message:stream** (visible in the 403 URL) because every agent
card advertises `capabilities.streaming: true`, so the a2a ClientFactory picks the streaming
transport. This round tests that directly:

  1. MULTI-TARGET — the same three checks against ui_renderer, brand_style and orchestrator, to
     prove the result is a property of the gateway and not of one target agent.
  2. SELF (streaming=False) — this probe's OWN card is deployed with streaming=False, so an SDK
     client talking to it should fall back to message:send. If that succeeds where the others
     403, the card flag is the cause and the fix is a one-line card change.
"""

import json
import os
import traceback
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai import types

_REGION = "us-central1"
_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
_NUM = "789872749985"
_MTLS = f"https://{_REGION}-aiplatform.mtls.googleapis.com"
_PLAIN = f"https://{_REGION}-aiplatform.googleapis.com"
_BRIEF = json.dumps({"probe": {"agent": "probe", "status": "pass", "message": "in-engine probe"}})

def _res(engine_id: str) -> str:
    return f"projects/{_NUM}/locations/{_REGION}/reasoningEngines/{engine_id}"

# agent-to-agent targets: fast, medium, and the slow orchestrator — all three are real peers
_TARGETS = {
    "ui_renderer": _res("4545326643400409088"),
    "brand_style": _res("3483603031247814656"),
    "orchestrator": _res("3932837094078021632"),
}
_SELF = _res(os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID", "0"))


def _attempt(label, fn):
    try:
        return {"t": label, "ok": True, **fn()}
    except Exception as e:                                   # noqa: BLE001 — the failure IS the data
        return {"t": label, "ok": False, "err": f"{type(e).__name__}: {e}"[:240]}


def _raw_send(host: str, target: str, dual_auth: bool) -> dict:
    """One message:send with headers we control exactly."""
    import google.auth
    import google.auth.transport.requests as gar
    import requests

    creds, _ = google.auth.default()
    creds.refresh(gar.Request())
    h = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    if dual_auth:
        h["Proxy-Authorization"] = f"Bearer {creds.token}"
    body = {"message": {"role": "ROLE_USER", "messageId": "iso", "content": [{"text": _BRIEF}]}}
    with requests.Session() as s:
        r = s.post(f"{host}/v1beta1/{target}/a2a/v1/message:send",
                   headers=h, json=body, timeout=120, allow_redirects=False)
    return {"status": r.status_code, "body": r.text[:110]}


def _raw_stream(host: str, target: str) -> dict:
    """The path `_genai` actually uses when the card says streaming=true."""
    import google.auth
    import google.auth.transport.requests as gar
    import requests

    creds, _ = google.auth.default()
    creds.refresh(gar.Request())
    h = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    body = {"message": {"role": "ROLE_USER", "messageId": "iso", "content": [{"text": _BRIEF}]}}
    with requests.Session() as s:
        r = s.post(f"{host}/v1beta1/{target}/a2a/v1/message:stream",
                   headers=h, json=body, timeout=120, allow_redirects=False, stream=False)
    return {"status": r.status_code, "body": r.text[:110]}


async def _genai_call(target: str):
    """The SDK client. Which path it picks depends on the TARGET's advertised card."""
    import vertexai
    from google.genai.types import HttpOptions
    engine = vertexai.Client(project=_PROJECT, location=_REGION,
                             http_options=HttpOptions(base_url=_MTLS)).agent_engines.get(name=target)
    chunks = await engine.on_message_send(
        role="user", parts=[{"kind": "text", "text": _BRIEF}],
        messageId="probe", kind="message")
    first = chunks[0][0] if isinstance(chunks[0], (list, tuple)) else chunks[0]
    return {"type": type(first).__name__,
            "state": str(getattr(getattr(first, "status", None), "state", None))}


class _Probe(BaseAgent):
    async def _run_async_impl(self, ctx) -> AsyncGenerator[Event, None]:
        out = {"in_engine": bool(os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")),
               "self": _SELF, "by_target": {}}

        # 1 · the same three checks against three different peer agents
        for label, tgt in _TARGETS.items():
            out["by_target"][label] = [
                _attempt("mtls_SEND_single_auth", lambda t=tgt: _raw_send(_MTLS, t, False)),
                _attempt("mtls_STREAM_single_auth", lambda t=tgt: _raw_stream(_MTLS, t)),
                _attempt("plain_SEND_dual_auth", lambda t=tgt: _raw_send(_PLAIN, t, True)),
            ]

        # 2 · the card-flag hypothesis: this engine's own card is streaming=False
        try:
            out["self_streaming_false_genai"] = {"ok": True, **(await _genai_call(_SELF))}
        except Exception as e:                               # noqa: BLE001
            out["self_streaming_false_genai"] = {"ok": False, "err": f"{type(e).__name__}: {e}"[:240]}
        try:
            out["peer_streaming_true_genai"] = {"ok": True,
                                                **(await _genai_call(_TARGETS["ui_renderer"]))}
        except Exception as e:                               # noqa: BLE001
            out["peer_streaming_true_genai"] = {"ok": False, "err": f"{type(e).__name__}: {e}"[:240]}

        blob = json.dumps(out, indent=1)
        print("[probe]", blob, flush=True)
        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role="model", parts=[types.Part(text=blob)]))


root_agent = _Probe(name="a2a_probe", description="Temporary in-engine A2A transport probe.")

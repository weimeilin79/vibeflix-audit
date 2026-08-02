"""TEMPORARY EXPERIMENT — delete after the run (see eng-report/a2a-native-transport-findings.md
Appendix B). Not part of the mesh; nothing imports it.

QUESTION: can the Vertex SDK's `_genai` A2A client (`vertexai.Client(...).agent_engines.get(...)`
→ `on_message_send` / `on_get_task`) reach another engine FROM INSIDE a gateway-attached engine?

That is the one case the laptop test can't answer. The wrapper builds its own httpx client with a
single `Authorization` header and derives the host from the client's `base_url`; this mesh's
`a2a_engine.py` documents that an in-engine call needs the **mtls host** (the gateway authorizes
only the registered destination) AND **`Proxy-Authorization`** alongside `Authorization`. So we try
both hosts and report exactly what comes back.

Controls: the same call via `a2a_engine_send` (the known-good path) runs last, so a failure that is
really about grants/identity is distinguishable from one about the SDK client's request shape.
"""

import json
import os
import traceback
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai import types

_TARGET = os.environ.get("PROBE_TARGET", "")          # projects/…/reasoningEngines/ID
_REGION = os.environ.get("GOOGLE_CLOUD_LOCATION_A2A", "us-central1")
_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
_PLAIN = f"https://{_REGION}-aiplatform.googleapis.com"
_MTLS = f"https://{_REGION}-aiplatform.mtls.googleapis.com"

_BRIEF = json.dumps({"probe_agent": {"agent": "probe_agent", "status": "pass",
                                     "message": "probe"}})


async def _genai_call(base_url: str | None) -> dict:
    """One `on_message_send` through the SDK client, optionally re-hosted at `base_url`."""
    import vertexai
    from google.genai.types import HttpOptions

    kwargs = {"project": _PROJECT, "location": _REGION}
    if base_url:
        kwargs["http_options"] = HttpOptions(base_url=base_url)
    client = vertexai.Client(**kwargs)
    engine = client.agent_engines.get(name=_TARGET)
    chunks = await engine.on_message_send(
        role="user",
        parts=[{"kind": "text", "text": _BRIEF}],
        messageId="in-engine-probe",
        kind="message",
    )
    first = chunks[0][0] if isinstance(chunks[0], (list, tuple)) else chunks[0]
    return {"ok": True, "type": type(first).__name__,
            "state": str(getattr(getattr(first, "status", None), "state", None)),
            "task_id": getattr(first, "id", None)}


async def _attempt(label: str, coro) -> dict:
    try:
        return {"attempt": label, **(await coro)}
    except Exception as e:                                   # noqa: BLE001 — this IS the result
        return {"attempt": label, "ok": False,
                "error": f"{type(e).__name__}: {e}"[:600],
                "tail": traceback.format_exc()[-400:]}


class _Probe(BaseAgent):
    async def _run_async_impl(self, ctx) -> AsyncGenerator[Event, None]:
        results = [
            await _attempt("genai_plain_host", _genai_call(None)),
            await _attempt("genai_mtls_host", _genai_call(_MTLS)),
        ]
        # control: the known-good hand-rolled sender, same target, same identity
        try:
            from vibeflix_common.a2a_engine import a2a_engine_send
            reply = await a2a_engine_send(f"{_MTLS}/v1beta1/{_TARGET}", _BRIEF, timeout=300.0)
            results.append({"attempt": "control_a2a_engine_send", "ok": True,
                            "reply_head": (reply or "")[:120]})
        except Exception as e:                               # noqa: BLE001
            results.append({"attempt": "control_a2a_engine_send", "ok": False,
                            "error": f"{type(e).__name__}: {e}"[:400]})

        summary = json.dumps({"target": _TARGET, "in_engine": bool(
            os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")), "results": results}, indent=1)
        print("[probe]", summary, flush=True)
        yield Event(author=self.name,
                    content=types.Content(role="model", parts=[types.Part(text=summary)]))


root_agent = _Probe(name="a2a_probe", description="Temporary in-engine A2A transport probe.")

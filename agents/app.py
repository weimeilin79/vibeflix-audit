"""FastAPI proxy that drives the ADK 2.0 Sourcing Orchestrator workflow.

`/api/audit` runs the graph and returns the aggregated reports the frontend
expects. When the requested volume exceeds the vendor cap, the workflow's
human-in-the-loop sourcing gate interrupts; the response then carries
`hitl_required` plus a `session_id`, and the client resolves it via
`/api/resume` (Scenario 3, Option A / Option B).
"""

import os
import json
import time
import uuid
import asyncio

import httpx
from dotenv import load_dotenv

# Load the app/persistence config (incl. AGENT_ENGINE_ID/ARTIFACTS_BUCKET) before
# importing the persistence module, which reads them at import.
load_dotenv(os.path.join(os.path.dirname(__file__), "orchestrator", ".env"))

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google.genai import types

from google.adk.apps import App
from google.adk.runners import Runner, InMemoryRunner

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH

from agents.orchestrator.agent import root_agent, _parse_report_text, _text_of, note_responder
from agents.a2ui_surface import (
    build_surface, panels_fallback, stream_initial, stream_panel, stream_sourcing,
    title_from_name,
)
from vibeflix_common.memory import (
    APP_NAME,
    build_session_service,
    build_memory_service,
    build_artifact_service,
    build_context_cache_config,
    summary as memory_summary,
)

# Initialize FastAPI App
app = FastAPI(title="ADK 2.0 Multi-Agent Procurement Service")

# Allow CORS for local frontend React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
class AuditRequest(BaseModel):
    """The initial form: image link + market + volume kick off the audit."""

    image_path: str = "grogu_mockup_box.png"
    # Image LINK (e.g. a gs:// Cloud Storage URI). Passed to the agents by
    # reference as a file_data part — the blob is never uploaded.
    image_uri: str | None = None
    target_market: str = "North America"
    volume: int = 15000
    # Licensed character / trademark under review (any in the registry). No default —
    # if the caller omits it, the clearance agent asks for it.
    character: str = ""
    # Manufactured product category (e.g. "Vinyl Figures", "Plush"). No default — the
    # clearance agent asks unless it's unambiguous from the medium.
    product_category: str = ""
    # The manufacturing vendor to apply for (id or name). No default — the clearance
    # agent asks, verifies it exists, and offers to onboard it if it doesn't.
    vendor: str = ""
    # Details to onboard a not-yet-existing vendor (supplied on the follow-up run).
    new_vendor: str = ""
    # "yes"/"no" — approve adding the product category to the named vendor.
    add_category_approved: str = ""
    # Optional user-provided product medium; blank → brand_style infers it.
    medium: str = ""
    # Free-text operator note / question (the chat field) — threaded into the orchestrator
    # brief as extra context for the agents.
    note: str = ""
    # On a re-submit, the token from the prior audit — lets the orchestrator reason
    # about which workflows the change affects and reuse the rest.
    run_token: str | None = None


class ResumeRequest(BaseModel):
    """Answer a dynamic input request: the values the agent/orchestrator asked for."""

    session_id: str
    values: dict = {}  # e.g. {"image_uri": "gs://…"} or {"sourcing_choice": "A"}


class TelemetryPayload(BaseModel):
    interaction_type: str
    element_id: str
    time_spent_ms: int
    overridden: bool


# The ADK app wrapping the workflow graph. The orchestrator surfaces any needed
# input (a missing image, a sourcing decision) as a field in its aggregate; the
# app collects it and re-runs, so no in-graph interrupt/resumability is needed.
# context_cache_config caches the stable instruction/semantic prefix on Vertex.
adk_app = App(
    name=APP_NAME,
    root_agent=root_agent,
    context_cache_config=build_context_cache_config(),
)

# Env-gated persistence: managed Vertex (Sessions + Memory Bank + GCS) when
# AGENT_ENGINE_ID/ARTIFACTS_BUCKET are set, else in-memory (local dev).
session_service = build_session_service()
memory_service = build_memory_service()
artifact_service = build_artifact_service()
runner = Runner(
    app=adk_app,
    session_service=session_service,
    memory_service=memory_service,
    artifact_service=artifact_service,
)
print(f"[app] persistence: {memory_summary()}")

# The UI-Render agent is its own A2A service; the app reaches it as a
# RemoteA2aAgent (run via an in-memory runner). It turns the orchestrator's raw
# reports into A2UI panels, which we then assemble into a surface deterministically.
# If UI_RENDERER_A2A_URL is unset or the service is down, _present returns None and
# we fall back to a rule-based summary — the UI keeps working.
PRESENTER_APP = "a2ui_presenter"
_UI_RENDERER_URL = os.environ.get("UI_RENDERER_A2A_URL", "").rstrip("/")
presenter_runner = (
    InMemoryRunner(app=App(
        name=PRESENTER_APP,
        root_agent=RemoteA2aAgent(
            name="a2ui_presenter",
            agent_card=f"{_UI_RENDERER_URL}{AGENT_CARD_WELL_KNOWN_PATH}",
        ),
    ))
    if _UI_RENDERER_URL else None
)

# Audit conversations awaiting more input: token -> {user_id, request(accumulated)}.
_SESSIONS: dict[str, dict] = {}

# The orchestrator's note-responder runs as its own in-memory agent (like the presenter).
_NOTE_APP = "note_responder"
note_responder_runner = InMemoryRunner(app=App(name=_NOTE_APP, root_agent=note_responder))


async def _respond_to_note(note: str, reports: dict) -> str | None:
    """Run the orchestrator's note_responder on {note, reports} -> a short reply (or None)."""
    try:
        payload = json.dumps({"note": note, "reports": reports})
        session = await note_responder_runner.session_service.create_session(app_name=_NOTE_APP, user_id="note")
        text = ""
        async for event in note_responder_runner.run_async(
            user_id="note", session_id=session.id, new_message=_content(payload)
        ):
            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) if content else None
            text += "".join(getattr(p, "text", "") or "" for p in (parts or []))
        return text.strip() or None
    except Exception as e:
        print(f"[note_responder] failed: {type(e).__name__}: {e}", flush=True)
        return None


async def _present(reports: dict) -> list | None:
    """Call the UI-Render agent (over A2A) on an arbitrary set of reports → panels,
    or None if it's unconfigured/unreachable or produced nothing."""
    if presenter_runner is None:
        return None
    payload = json.dumps(reports)
    user_id = "presenter"
    session = await presenter_runner.session_service.create_session(app_name=PRESENTER_APP, user_id=user_id)
    data = None
    async for event in presenter_runner.run_async(
        user_id=user_id, session_id=session.id, new_message=_content(payload)
    ):
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        text = "".join(getattr(p, "text", "") or "" for p in (parts or [])).strip()
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "panels" in parsed:
                    data = parsed
            except ValueError:
                pass
    if not data or not data.get("panels"):
        return None
    return [
        {"title": p["title"], "status": p["status"], "headline": p["headline"],
         "lines": [(ln["text"], ln.get("resolve", "")) for ln in p.get("lines", [])]}
        for p in data["panels"]
    ]


async def _render_surface(aggregate: dict, market, volume) -> dict:
    """Turn the aggregate into an A2UI surface: presenter agent → panels →
    build_surface. Generic — renders EVERY `*_report` in the aggregate, so adding a
    new workflow needs no change here. Falls back to a rule-based summary on error."""
    reports = {k: v for k, v in aggregate.items() if k.endswith("_report") and isinstance(v, dict)}
    try:
        panels = await _present(reports)
        if not panels:
            raise ValueError("presenter returned no panels")
    except Exception as e:
        print(f"[app] a2ui presenter failed ({type(e).__name__}: {e}); using rule-based fallback", flush=True)
        panels = panels_fallback(reports)
    return build_surface(panels, aggregate.get("sourcing") or {}, market, volume)


async def _persist_audit(user_id: str, session_id: str, result: dict) -> None:
    """Best-effort: send the finished session to Memory Bank + store the report.

    Never fails the request — persistence errors are logged and swallowed.
    """
    try:
        session = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if session is not None:
            await memory_service.add_session_to_memory(session)
        await artifact_service.save_artifact(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            filename="audit_report.json",
            artifact=types.Part(
                inline_data=types.Blob(
                    mime_type="application/json",
                    data=json.dumps(result).encode("utf-8"),
                )
            ),
        )
    except Exception as e:  # persistence is non-critical to the API response
        print(f"[persist] non-fatal: {type(e).__name__}: {e}")


def _content(payload: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=payload)])


async def _run_once(request: dict) -> tuple[str, str, dict]:
    """Run the workflow to completion on a fresh session; return (user_id, sid, aggregate)."""
    user_id = f"audit-{uuid.uuid4().hex[:8]}"
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=user_id)
    aggregate: dict | None = None
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=_content(json.dumps(request))
    ):
        output = getattr(event, "output", None)
        if isinstance(output, dict) and "style_report" in output:
            aggregate = output  # keep the last (finalize's, which includes sourcing)
    if aggregate is None:
        raise HTTPException(status_code=500, detail="Workflow produced no audit result.")
    return user_id, session.id, aggregate


# Reliability is now handled INSIDE the orchestrator: its `recovery` node detects a
# failed workflow (report with no `status` — e.g. Gemini's malformed
# `set_model_response`) and re-runs ONLY that agent. So the app runs the graph once.


# Trademark/character options for the picker — pulled from the licensing registry
# (mcp_licensing.list_trademarks) so the UI offers valid ids; free-typing a variant
# like "Minion" silently misses trademark + exclusivity records.
_MCP_LICENSING_URL = os.environ.get("MCP_LICENSING_URL", "")
_TRADEMARK_OPTIONS: list = []


async def _fetch_trademarks() -> list:
    """Pull the licensed-trademark list from mcp_licensing → [{value:id, label:mark}]."""
    if not _MCP_LICENSING_URL:
        return []
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(_MCP_LICENSING_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("list_trademarks", {})
                text = "".join(getattr(c, "text", "") or "" for c in (res.content or []))
                data = json.loads(text) if text else []
                return [{"value": t["id"], "label": t.get("mark", t["id"])} for t in data]
    except Exception as e:
        print(f"[app] fetch trademarks failed: {type(e).__name__}: {e}", flush=True)
        return []


@app.get("/api/trademarks")
async def api_trademarks():
    """The licensed-trademark options for the character/trademark dropdown."""
    global _TRADEMARK_OPTIONS
    if not _TRADEMARK_OPTIONS:
        _TRADEMARK_OPTIONS = await _fetch_trademarks()
    return {"trademarks": _TRADEMARK_OPTIONS}


# Field specs for the data any agent can ask for (keyed by the `needs` token the
# report emits). Adding a new askable field = one entry here.
_FIELD_SPECS = {
    "character": {"name": "character", "label": "Licensed character / trademark to clear",
                  "type": "text", "placeholder": "e.g. grogu, stitch, minions, gremlins", "required": True},
    "category": {"name": "product_category", "label": "Manufactured product category",
                 "type": "text", "placeholder": "Vinyl Figures, Plush, Apparel, Resin Statues, Blind Box", "required": True},
    "vendor": {"name": "vendor", "label": "Manufacturing vendor to apply for",
               "type": "text", "placeholder": "vendor id (e.g. VND-1001) or name", "required": True},
    "new_vendor": {"name": "new_vendor", "label": "New vendor details (to onboard it)",
                   "type": "textarea", "placeholder": "legal name, HQ country, product categories, operating territories…", "required": True},
    "add_category_approved": {"name": "add_category_approved", "label": "Add this product category to the vendor?",
                              "type": "select", "options": [{"value": "yes", "label": "Yes — add it"}, {"value": "no", "label": "No"}], "required": True},
    "territory": {"name": "target_market", "label": "Target market / territory",
                  "type": "text", "placeholder": "North America, Europe, Asia-Pacific, Latin America…", "required": True},
    "image": {"name": "image_uri", "label": "Approved mockup image link",
              "type": "text", "placeholder": "gs://vibeflix-approved-assets/… or https://…", "required": True},
    "medium": {"name": "medium", "label": "Product medium — what will this be manufactured / printed as?",
               "type": "text", "placeholder": "e.g. vinyl figure box, poster, T-shirt", "required": True},
}


def _pending_input(aggregate: dict) -> dict | None:
    """If the run needs more input, return {prompt, fields:[...]} to collect it.

    Generic: ANY `*_report` with status `needs_input`/`rejected` surfaces here — the
    agent lists what it needs via `needs` (a list of field tokens) and a `question`.
    The sourcing gate over cap asks for the A/B decision. Returns None when nothing
    is pending.
    """
    style = aggregate.get("style_report") or {}
    tokens, prompts = [], []
    for key, report in aggregate.items():
        if not (key.endswith("_report") and isinstance(report, dict)):
            continue
        if report.get("status") not in ("needs_input", "rejected"):
            continue
        # brand_style historically defaults to asking for the image.
        for token in (report.get("needs") or (["image"] if key == "style_report" else [])):
            if token not in tokens:
                tokens.append(token)
        if report.get("question"):
            prompts.append(report["question"])
    if tokens:
        fields = []
        for token in tokens:
            spec = dict(_FIELD_SPECS.get(token, {"name": token, "label": token, "type": "text", "required": True}))
            if token == "medium":  # pre-fill brand_style's visual guess
                spec["value"] = (style.get("extracted") or {}).get("medium", "")
            if token == "character" and _TRADEMARK_OPTIONS:  # dropdown of valid trademarks
                spec = {**spec, "type": "select", "options": _TRADEMARK_OPTIONS}
            fields.append(spec)
        return {"prompt": " ".join(prompts) or "A bit more information is needed to run the audit.",
                "fields": fields}

    sourcing = aggregate.get("sourcing") or {}
    if sourcing.get("status") == "needs_choice":
        return {
            "prompt": sourcing.get("question") or "A sourcing-cap decision is required.",
            "fields": [
                {
                    "name": "sourcing_choice",
                    "label": "Sourcing decision",
                    "type": "select",
                    "options": sourcing.get(
                        "options", [{"value": "A", "label": "A"}, {"value": "B", "label": "B"}]
                    ),
                    "required": True,
                }
            ],
        }
    return None


async def _collect_or_complete(request: dict, token: str | None = None) -> dict:
    """Run the audit; if it needs input, register the session and return the fields;
    otherwise persist and return the completed aggregate."""
    user_id, sid, aggregate = await _run_once(request)
    # Paint the A2UI surface via the UI-Render agent (decoupled from the
    # orchestrator, which self-heals failed workflows and returns raw reports).
    aggregate["a2ui_payload"] = await _render_surface(
        aggregate, request.get("target_market", "North America"), request.get("volume", 0)
    )
    pending = _pending_input(aggregate)
    if pending is not None:
        tok = token or uuid.uuid4().hex[:12]
        _SESSIONS[tok] = {"user_id": user_id, "request": request}
        return {
            "status": "input_required",
            "session_id": tok,
            "prompt": pending["prompt"],
            "fields": pending["fields"],
            "partial": aggregate,  # show what's known so far while asking
        }
    if token:
        _SESSIONS.pop(token, None)
    await _persist_audit(user_id, sid, aggregate)
    return {"status": "completed", "result": aggregate}


# ---- Streaming (A2UI over SSE) --------------------------------------------
# The orchestrator DECIDES which workflows to show (it emits a `__plan__` event) and
# returns each report keyed by agent name — so this layer hardcodes NO workflow list.
# Adding a workflow is a change to the orchestrator's _AGENTS only; the app + frontend
# render whatever plan/reports arrive.

# Cache of finished/partial audits by token, so a re-submit can thread the prior
# reports + inputs to the orchestrator (which reasons about what to re-run).
_AUDIT_CACHE: dict[str, dict] = {}


def _cache_audit(aggregate: dict, request: dict) -> str:
    """Store {reports (by agent name), inputs} and return a fresh run token."""
    reports = {n: r for n, r in (aggregate.get("reports") or {}).items() if isinstance(r, dict)}
    inputs = {
        "image_uri": request.get("image_uri") or "",
        "target_market": request.get("target_market", "North America"),
        "volume": request.get("volume", 0),
        "medium": request.get("medium", ""),
        "character_id": request.get("character") or "",
        "product_category": request.get("product_category") or "",
        "vendor": request.get("vendor") or "",
    }
    token = uuid.uuid4().hex[:12]
    _AUDIT_CACHE[token] = {"reports": reports, "inputs": inputs}
    return token


def _apply_prior(request: dict) -> dict:
    """If the request carries a known run_token, thread its prior reports + inputs
    into the orchestrator request so `decide_reruns` can reason incrementally."""
    prior = _AUDIT_CACHE.get(request.get("run_token") or "")
    if prior:
        request = {**request, "prior_reports": prior["reports"], "prior_inputs": prior["inputs"]}
    return request


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def _panel_for(name: str, report: dict) -> dict:
    """One rendered panel for a single report (presenter agent, else fallback). Keyed
    by agent name; the presenter/fallback infer the title from the report itself."""
    try:
        panels = await _present({name: report})
        if panels:
            return panels[0]
    except Exception as e:
        print(f"[app] stream presenter failed ({type(e).__name__}); fallback", flush=True)
    fb = panels_fallback({name: report})
    return fb[0] if fb else {"title": title_from_name(name), "status": report.get("status", "?"), "headline": "—", "lines": []}


def _legal_graph_event(author: str, report: dict) -> dict | None:
    """Graph event for the PRIVATE Legal sub-node under vendor_clearance, when it acted
    (executed a contract → cleared; asked the user for the cert → needs_input)."""
    if author != "vendor_clearance_agent" or not isinstance(report, dict):
        return None
    if report.get("legal_cleared"):
        status = "cleared"
    elif "legal_safety_cert" in (report.get("needs") or []):
        status = "needs_input"
    else:
        return None
    return {"event": "graph", "op": "status", "id": "legal", "label": "⚖️ Legal Clearance",
            "parent": author, "status": status}


async def _stream_audit(request: dict):
    """SSE generator: the orchestrator emits a `__plan__` (which workflows to show) →
    we render pending panels for exactly those → fill each as its agent returns →
    sourcing → done/input_required. No workflow list is hardcoded here.

    Alongside the A2UI panels we emit structured `graph` events (plan + per-node status)
    so the client can draw the live workflow graph."""
    market = request.get("target_market", "North America")
    volume = request.get("volume", 0)
    request = _apply_prior(request)  # thread prior reports/inputs if re-submitting

    user_id = f"audit-{uuid.uuid4().hex[:8]}"
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=user_id)
    aggregate = None
    names, author_idx, filled = [], {}, set()
    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=_content(json.dumps(request))
        ):
            parsed = _parse_report_text(_text_of(getattr(event, "content", None)))
            # 1) the plan: build the pending surface for exactly the workflows the
            #    orchestrator says to show (titles derived from names — generic).
            if not names and isinstance(parsed, dict) and "__plan__" in parsed:
                plan = parsed["__plan__"]
                # Show ONLY the workflows being run this pass — reused ones already
                # appear on the previous run's surface, so re-showing them is noise.
                names = [p["name"] for p in plan if p.get("run", True)]
                reused = len(plan) - len(names)
                author_idx = {n: i for i, n in enumerate(names)}
                for msg in stream_initial([title_from_name(n) for n in names], market, volume, reused):
                    yield _sse({"a2ui": msg})
                # The graph mirrors the plan: ALL workflows (run + reused), lit up live.
                yield _sse({"event": "graph", "op": "plan",
                            "nodes": [{"id": p["name"], "label": title_from_name(p["name"]),
                                       "run": p.get("run", True)} for p in plan]})
                continue
            # 2) an agent's report fills its panel (only when valid — has a status).
            author = getattr(event, "author", None)
            if author in author_idx and isinstance(parsed, dict) and parsed.get("status"):
                i = author_idx[author]
                filled.add(i)
                yield _sse({"a2ui": stream_panel(i, await _panel_for(author, parsed))})
                yield _sse({"event": "graph", "op": "status", "id": author, "status": parsed["status"]})
                _leg = _legal_graph_event(author, parsed)
                if _leg:
                    yield _sse(_leg)
            out = getattr(event, "output", None)
            if isinstance(out, dict) and "reports" in out:
                aggregate = out
    except Exception as e:
        yield _sse({"event": "error", "message": f"{type(e).__name__}: {e}"})
        return

    if aggregate is None:
        yield _sse({"event": "error", "message": "Workflow produced no result."})
        return

    reports = aggregate.get("reports") or {}
    if not names:  # plan never arrived — fall back to whatever reports came back
        names = list(reports)
        author_idx = {n: i for i, n in enumerate(names)}
        for msg in stream_initial([title_from_name(n) for n in names], market, volume):
            yield _sse({"a2ui": msg})

    # 3) fill any shown panel that never streamed a valid report (e.g. recovered).
    #    Only dispatched workflows are shown, so there's nothing reused to tag here.
    for i, name in enumerate(names):
        if i not in filled and (reports.get(name) or {}).get("status"):
            filled.add(i)
            yield _sse({"a2ui": stream_panel(i, await _panel_for(name, reports[name]))})
            yield _sse({"event": "graph", "op": "status", "id": name, "status": reports[name]["status"]})
            _leg = _legal_graph_event(name, reports[name])
            if _leg:
                yield _sse(_leg)
    # Safety net: any shown workflow that produced NO valid report (malformed after
    # retries) is resolved to FAILED — so its panel + graph node never hang at "running".
    for i, name in enumerate(names):
        if i not in filled:
            failed = {"agent": name, "status": "failed", "issues": [{
                "element_id": name, "issue_type": "no_report", "severity": "critical",
                "description": "This workflow did not return a valid report (it failed after "
                               "automatic retries). Re-run to try again.",
            }]}
            yield _sse({"a2ui": stream_panel(i, await _panel_for(name, failed))})
            yield _sse({"event": "graph", "op": "status", "id": name, "status": "failed"})

    # 3) sourcing line.
    yield _sse({"a2ui": stream_sourcing(aggregate.get("sourcing") or {})})

    # 3.5) if the operator submitted a note/question, the orchestrator responds to it
    #      (answers from the reports, or acks it as applied context).
    _note = (request.get("note") or "").strip()
    if _note:
        _ans = await _respond_to_note(_note, reports)
        if _ans:
            yield _sse({"event": "note_response", "text": _ans})

    # 4) done, or collect more input. Either way, cache this run + return its token so
    #    the client can thread it on the next submit (incremental re-run).
    token = _cache_audit(aggregate, request)
    pending = _pending_input(aggregate)
    if pending is not None:
        yield _sse({"event": "input_required", "run_token": token,
                    "prompt": pending["prompt"], "fields": pending["fields"]})
    else:
        aggregate["a2ui_payload"] = build_surface(
            panels_fallback(aggregate.get("reports") or {}),
            aggregate.get("sourcing") or {}, market, volume,
        )
        await _persist_audit(user_id, session.id, aggregate)
        yield _sse({"event": "done", "run_token": token})


@app.post("/api/audit/stream")
async def audit_stream(req: AuditRequest):
    """Streaming audit: Server-Sent Events carrying incremental A2UI messages."""
    request = {
        "image_path": req.image_path,
        "image_uri": req.image_uri or "",
        "target_market": req.target_market,
        "volume": req.volume,
        "character": req.character or "",
        "product_category": req.product_category or "",
        "vendor": req.vendor or "",
        "new_vendor": req.new_vendor or "",
        "add_category_approved": req.add_category_approved or "",
        "medium": req.medium or "",
        "note": req.note or "",
        "run_token": req.run_token,
    }
    return StreamingResponse(_stream_audit(request), media_type="text/event-stream")


@app.get("/api/health")
def health():
    return {"message": "ADK 2.0 Agent Mesh Backend is online."}


# The domain agents the orchestrator depends on (label + A2A base-URL env var).
# `critical` components gate readiness — the console locks until they're healthy.
# All agents (including ui_renderer) are critical: a down presenter locks the UI.
# (The rule-based fallback still covers a *transient* presenter failure mid-request.)
_AGENT_SERVICES = [
    {"name": "brand_style", "label": "Brand Style", "env": "BRAND_STYLE_A2A_URL", "critical": True},
    {"name": "vendor_clearance", "label": "Vendor & Licensing", "env": "VENDOR_CLEARANCE_A2A_URL", "critical": True},
    {"name": "storyline", "label": "Storyline Lore", "env": "STORYLINE_A2A_URL", "critical": True},
    {"name": "ui_renderer", "label": "UI Renderer", "env": "UI_RENDERER_A2A_URL", "critical": True},
]


async def _probe_agent(svc: dict) -> dict:
    """Fetch an agent's /healthz (reachability + its MCP handshake results). Logs the
    per-agent outcome + latency so you can see exactly which one is down/slow."""
    comp = {"name": svc["name"], "label": svc["label"], "critical": svc.get("critical", True),
            "reachable": False, "ok": False, "mcp": []}
    base = os.environ.get(svc["env"], "").rstrip("/")
    if not base:
        comp["error"] = f"{svc['env']} not set"
        print(f"[ready] {svc['name']:16} ❌ {comp['error']}", flush=True)
        return comp
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(f"{base}/healthz")
            resp.raise_for_status()
            data = resp.json()
        comp["reachable"] = True
        comp["mcp"] = data.get("mcp", [])
        comp["ok"] = bool(data.get("ok", False))
    except Exception as e:
        comp["error"] = f"{type(e).__name__}: {str(e)[:140]}"
    ms = int((time.monotonic() - t0) * 1000)
    if comp["ok"]:
        mark = "✅ ok"
    elif comp["reachable"]:
        bad_mcp = [m.get("name") for m in comp["mcp"] if not m.get("ok")]
        mark = f"⚠️  reachable but NOT ok (bad MCP: {bad_mcp or '—'})"
    else:
        mark = f"❌ UNREACHABLE ({comp.get('error', '?')})"
    print(f"[ready] {svc['name']:16} {mark}  [{ms}ms] @ {base}", flush=True)
    return comp


@app.get("/api/ready")
async def ready():
    """Layer-2 gate: are the CRITICAL agents reachable AND their MCP tools live?

    The UI polls this and locks the console (showing each component's status)
    until every critical agent + its MCP servers are healthy. All agents —
    including the ui_renderer — are critical, so any one being down locks the UI.
    """
    t0 = time.monotonic()
    components = list(await asyncio.gather(*(_probe_agent(s) for s in _AGENT_SERVICES)))
    critical_ok = all(c["ok"] for c in components if c.get("critical", True))
    down = [c["name"] for c in components if not c["ok"]]
    print(f"[ready] → {'READY' if critical_ok else 'NOT READY'} in {int((time.monotonic()-t0)*1000)}ms"
          + (f" · blocking: {down}" if down else ""), flush=True)
    return {"ready": critical_ok, "components": components}


@app.on_event("startup")
async def _log_mesh_readiness():
    """Non-fatal: probe the mesh (with warmup retries) and log a loud banner."""
    async def _check():
        for _ in range(6):  # ~30s of warmup tolerance
            snapshot = await ready()
            if snapshot["ready"]:
                print("[app] mesh readiness: ✅ all agents + MCP servers healthy", flush=True)
                global _TRADEMARK_OPTIONS
                _TRADEMARK_OPTIONS = await _fetch_trademarks()
                print(f"[app] loaded {len(_TRADEMARK_OPTIONS)} trademark options for the picker", flush=True)
                return
            await asyncio.sleep(5)
        bad = [c for c in snapshot["components"] if not c["ok"]]
        print(f"[app] mesh readiness: ⚠️  NOT READY — {len(bad)} component(s) unhealthy:", flush=True)
        for c in bad:
            print(f"       ❌ {c['label']}: {c.get('error') or [m for m in c['mcp'] if not m['ok']]}", flush=True)

    asyncio.create_task(_check())


@app.post("/api/audit")
async def run_audit(req: AuditRequest):
    """Kick off an audit from the initial form. Returns a completed aggregate or,
    if the run needs more info, an `input_required` with the fields to render."""
    request = {
        "image_path": req.image_path,
        "image_uri": req.image_uri or "",
        "target_market": req.target_market,
        "volume": req.volume,
        "character": req.character or "",
        "product_category": req.product_category or "",
        "vendor": req.vendor or "",
        "new_vendor": req.new_vendor or "",
        "add_category_approved": req.add_category_approved or "",
        "medium": req.medium or "",
    }
    try:
        return await _collect_or_complete(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit/resume")
async def resume_audit(req: ResumeRequest):
    """Answer a dynamic input request: merge the provided values into the
    accumulated request and re-run until nothing is pending."""
    ctx = _SESSIONS.get(req.session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="No audit session to resume.")
    request = dict(ctx["request"])
    for key, value in (req.values or {}).items():
        request[key] = value
    try:
        return await _collect_or_complete(request, token=req.session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_REQUEST_IMAGE_BUCKET = os.environ.get("REQUEST_IMAGE_BUCKET", "vibeflix-request-image")


def _upload_blob(data: bytes, content_type: str, blob_name: str) -> str:
    from google.cloud import storage
    client = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    blob = client.bucket(_REQUEST_IMAGE_BUCKET).blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{_REQUEST_IMAGE_BUCKET}/{blob_name}"


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload a vendor mockup to the request-image bucket; return its gs:// link
    so it can be used as the audit's approved image source."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    safe = os.path.basename(file.filename or "upload.png").replace(" ", "_")
    blob_name = f"{uuid.uuid4().hex[:8]}-{safe}"
    try:
        uri = await asyncio.to_thread(
            _upload_blob, data, file.content_type or "image/png", blob_name
        )
        return {"image_uri": uri}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@app.post("/api/telemetry")
async def log_telemetry(payload: TelemetryPayload):
    # Simulated writing user engagement maps back to governance-telemetry store
    print(f"[Telemetry Ingestion] Received interaction map on {payload.element_id}: Overridden={payload.overridden}")
    return {"status": "telemetry_captured"}


class EscalateRequest(BaseModel):
    """Raise an exception request for flagged findings the operator can't clear by editing
    inputs. MOCK for now — no real escalation workflow exists yet."""
    workflows: list[str] = []
    reason: str = ""
    run_token: str | None = None


@app.post("/api/escalate")
async def escalate(req: EscalateRequest):
    """MOCK exception escalation. A real version would open a ticket, route to a human
    reviewer, or kick off an approval workflow. For now we mint a ticket id and ack so the
    UI can show 'request escalated'."""
    ticket = f"ESC-{uuid.uuid4().hex[:4].upper()}"
    wf = ", ".join(req.workflows) if req.workflows else "the audit"
    print(f"[escalate] MOCK exception request {ticket}: workflows={req.workflows} "
          f"reason={req.reason!r}", flush=True)
    return {
        "status": "escalated",
        "ticket": ticket,
        "workflows": req.workflows,
        "message": (f"Exception request {ticket} raised for {wf} — routed to compliance "
                    f"review. (Mocked: the escalation workflow isn't implemented yet.)"),
    }


# Serve the built React frontend from the same origin as the API (mounted last
# so the /api/* routes above take precedence). Absent in dev → only the API runs.
_FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist"),
)
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("agents.app:app", host="0.0.0.0", port=port, reload=True)

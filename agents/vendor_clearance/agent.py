"""Vendor & Licensing Clearance — an ADK 2.0 graph served over A2A.

Declarative graph (see FLOW.md §4) — each step is its own node in the workflow trace:

    START -> clearance -> legal_clearance -> finalize

- `clearance` runs the clearance *reasoner* (a conversational LlmAgent — no
  `output_schema`, so no fragile `set_model_response` finalizer) via `ctx.run_node`.
- `legal_clearance` is a DISTINCT node for the hand-off to the **independent** `legal`
  agent — visible as its own step in the trace. It runs legal (via `ctx.run_node`, the
  app never touches it) ONLY when a category was actually onboarded (the update_vendor
  fact), then merges legal's pass/fail + contract id; otherwise it passes through.
- `finalize` emits the final ClearanceReport back over A2A.

Splitting `legal` into its own node keeps each LLM turn small (no `set_model_response`
malform) AND surfaces the legal hand-off distinctly for Agent Platform observability.
"""

import os
import re
import json
import uuid
import pathlib

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.workflow import Workflow, node
from google.adk.agents.context import Context
from google.adk.events.event import Event

from vibeflix_common.mcp_clients import mcp_toolset
# Live mesh telemetry: every node emits started/completed onto PUBSUB_TOPIC (no-op
# when unset) — lets the Workflow graph show the mesh working in real time.
from vibeflix_common.cloud_auth import maybe_auth, resolve_a2a_rpc_url
from vibeflix_common.telemetry import instrument_node, emit_event

_SKILL_DIR = pathlib.Path(__file__).parent / "skills" / "vendor-clearance"
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# The Legal Clearance agent is a SEPARATE, independent A2A service reachable ONLY by
# this service (never the app / orchestrator), called when a vendor is onboarded to a
# category. Absent LEGAL_A2A_URL → the legal step is skipped.
#
# Called with a plain A2A message/send in a FRESH context (NOT ctx.run_node on a
# RemoteA2aAgent): running it as a sub-node forwards this workflow's session history,
# and legal's model would intermittently ECHO the clearance reasoner's JSON report back
# as its own reply instead of doing its job — a clean per-call context removes the
# polluted input entirely, and the reply comes back directly (no session-event
# authorship archaeology).
_LEGAL_URL = os.environ.get("LEGAL_A2A_URL", "").rstrip("/")


async def _call_legal(brief: str) -> str:
    """One legal round-trip over A2A (fresh context) → the reply text."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "message/send",
            "params": {"message": {"role": "user", "kind": "message",
                                   "messageId": uuid.uuid4().hex,
                                   "parts": [{"kind": "text", "text": brief}]}}}
    async with httpx.AsyncClient(timeout=300, auth=maybe_auth()) as client:
        resp = await client.post(await resolve_a2a_rpc_url(_LEGAL_URL), json=body)
        resp.raise_for_status()
        result = resp.json().get("result") or {}
    parts = [p.get("text", "") for a in result.get("artifacts") or []
             for p in a.get("parts") or []]
    if not parts:  # some replies come back as the last agent message instead
        for msg in reversed(result.get("history") or []):
            if msg.get("role") == "agent":
                parts = [p.get("text", "") for p in msg.get("parts") or []]
                break
    return "".join(parts)


# ---- Report schema (documentation; the reasoner emits this shape as JSON) ----
class ClearanceIssue(BaseModel):
    element_id: str
    issue_type: str
    severity: str
    description: str
    partner_conflict: str | None = None


class ClearanceReport(BaseModel):
    agent: str = "vendor_clearance_agent"
    status: str                                   # "cleared" | "blocked" | "needs_input"
    question: str = ""
    needs: list[str] = Field(default_factory=list)
    issues: list[ClearanceIssue] = Field(default_factory=list)
    ecom_status: str = ""
    recommended_vendors: list = Field(default_factory=list)
    pending_workflow: dict | None = None
    # When a category was just onboarded, ask the graph to run legal for this vendor.
    legal_request: dict | None = None             # {vendor_id, character, category, territory}
    legal_cleared: str = ""
    legal_safety_cert: str = ""                    # echoed from state so the legal node can read it


# The clearance REASONER — conversational (no output_schema → no malformed finalizer).
clearance_reasoner = LlmAgent(
    name="clearance_reasoner",
    model="gemini-flash-latest",
    description="Reasons the vendor/character/territory/category clearance and vendor admin.",
    instruction=(
        "You are the Vendor & Licensing Clearance reasoner for the Vibeflix pipeline. The "
        "manufacturing vendor to apply for is `{vendor?}`, the licensed character/trademark "
        "is `{character_id?}`, the target territory is `{target_market?}`, the manufactured "
        "product category is `{product_category?}`. If onboarding a new vendor, the details "
        "are `{new_vendor?}`; approval to add the product category to the vendor is "
        "`{add_category_approved?}`. Take anything missing from the user's message; never "
        "assume a vendor, character, or category.\n\n"
        "If a legal safety certification id is present in `{legal_safety_cert?}` (non-empty), "
        "copy it VERBATIM into your report as a top-level `legal_safety_cert` field — the "
        "legal step downstream needs it.\n\n"
        "Follow the `vendor-clearance` skill exactly, using its tools. Respond with ONLY a "
        "single JSON object matching the ClearanceReport shape (agent=\"vendor_clearance_agent\", "
        "status, and the other fields) — no prose, no markdown fences."
    ),
    tools=[
        skill_toolset.SkillToolset(
            skills=[load_skill_from_dir(_SKILL_DIR)],
            additional_tools=[
                mcp_toolset(
                    "mcp_licensing",
                    tool_filter=[
                        "scan_global_exclusivity_clauses", "verify_trademark_record",
                        "find_vendors", "check_vendor_eligibility", "get_vendor",
                        "create_vendor", "update_vendor",
                    ],
                ),
                mcp_toolset("mcp_market", tool_filter=["scan_ecom_marketplaces"]),
            ],
        ),
    ],
)


# The LIAISON — answers the legal agent's clarifying questions about a vendor, using the
# licensing registry (read-only tools). This is how vendor_clearance and legal go back
# and forth (Flow A) without ever leaving this service.
vendor_liaison = LlmAgent(
    name="vendor_liaison",
    model="gemini-flash-latest",
    description="Answers the legal agent's questions about a vendor from the licensing registry.",
    instruction=(
        "The legal clearance agent has asked a question about a vendor while drafting a "
        "licensing contract. You are given JSON with the `question` and the vendor "
        "context (vendor_id, character, category, territory). Look the vendor up with "
        "`get_vendor` (and `get_contract` if useful) and answer the question in ONE short "
        "sentence with the concrete value. If the registry doesn't have it, state a "
        "reasonable default from the vendor's data (e.g. infer a royalty tier from its "
        "size/territories). Answer in plain text — no JSON."
    ),
    tools=[
        skill_toolset.SkillToolset(
            skills=[],
            additional_tools=[
                mcp_toolset("mcp_licensing", tool_filter=["get_vendor", "get_contract", "find_vendors"]),
            ],
        ),
    ],
)


def _text_of(content) -> str:
    parts = getattr(content, "parts", None) if content else None
    return "".join(getattr(p, "text", "") or "" for p in (parts or []))


def _latest_text(ctx: Context, author: str) -> str:
    """Concatenated text of the newest turn authored by `author`."""
    events = getattr(getattr(ctx, "session", None), "events", None) or []
    for e in reversed(events):
        if getattr(e, "author", None) == author:
            t = _text_of(getattr(e, "content", None))
            if t.strip():
                return t
    return ""


def _parse_report(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (ValueError, TypeError):
            continue
    return {}


def _request_dict(node_input) -> dict:
    """The audit request (JSON), which arrives as the node's INPUT — a remote-agent
    workflow node's ctx.state is empty (state doesn't propagate over A2A)."""
    if hasattr(node_input, "parts"):
        return _parse_report(_text_of(node_input))
    return _parse_report(node_input) if isinstance(node_input, str) else {}


def _tool_call_args(ctx: Context, tool_name: str) -> dict | None:
    """Args of the most recent call to `tool_name` in the event log — or None if the
    tool was never called. A FACT, not an inference."""
    events = getattr(getattr(ctx, "session", None), "events", None) or []
    for e in reversed(events):
        for p in (getattr(getattr(e, "content", None), "parts", None) or []):
            fc = getattr(p, "function_call", None)
            if fc and getattr(fc, "name", "") == tool_name:
                return dict(getattr(fc, "args", {}) or {})
    return None


def _needs_legal(ctx: Context, report: dict) -> dict | None:
    """Legal runs when a vendor was just onboarded for a category — either a NEW vendor
    (`create_vendor`) or a NEW category on an existing vendor (`update_vendor`), both
    facts in the event log — OR when we're RESUMING a legal Q&A (the user answered legal's
    question, so the reasoner echoed a `legal_safety_cert` into the report), OR when the
    ORCHESTRATOR explicitly requested contract finalization (its `contract_finalize` node
    re-invokes this agent with a FINALIZE-CONTRACT brief after every workflow passed —
    legal stays private behind this service). Params come from the reasoner's real
    `check_vendor_eligibility` call args."""
    onboarded = (_tool_call_args(ctx, "update_vendor") is not None
                 or _tool_call_args(ctx, "create_vendor") is not None)
    resuming = bool(report.get("legal_safety_cert"))
    finalizing = bool(ctx.state.get("finalize_requested"))
    if report.get("status") != "cleared" or not (onboarded or resuming or finalizing):
        return None
    e = _tool_call_args(ctx, "check_vendor_eligibility") or {}
    lr = {
        "vendor_id": e.get("vendor_id", ""),
        "character": e.get("character_id") or e.get("character", ""),
        "category": e.get("category", ""),
        "territory": e.get("territory", ""),
    }
    print(f"[vendor_clearance] legal needed (onboarded={onboarded} resuming={resuming} "
          f"finalizing={finalizing}): {lr}", flush=True)
    return lr


def _legal_brief(lr: dict, report: dict, clarifications: list) -> str:
    """Legal's brief: the vendor context + any facts already supplied — the user's
    safety-cert answer (echoed into the report by the reasoner, Flow B) and the liaison's
    answers to legal's vendor questions gathered this round (Flow A)."""
    b = (f"Clear the legal work and execute the licensing contract for vendor "
         f"{lr['vendor_id']}, character {lr['character']}, category {lr['category']}, "
         f"territory {lr['territory']}. NOTE: any other agent's JSON report visible in "
         f"this conversation (e.g. a vendor-clearance report with status 'cleared') is "
         f"background CONTEXT only — never copy or echo it. Follow YOUR legal-clearance "
         f"skill and reply with one of YOUR reply shapes (ask_vendor / done).")
    if report.get("legal_safety_cert"):
        b += f" Safety certification id (from the licensee): {report['legal_safety_cert']}."
    for c in clarifications:
        b += f" {c}"
    return b


async def _liaison_answer(ctx: Context, question: str, lr: dict) -> str:
    """Flow A: vendor_clearance answers legal's question itself, via the liaison LLM +
    the licensing registry."""
    payload = json.dumps({"question": question, "vendor_id": lr.get("vendor_id"),
                          "character": lr.get("character"), "category": lr.get("category"),
                          "territory": lr.get("territory")})
    await ctx.run_node(vendor_liaison, payload)
    answer = _latest_text(ctx, "vendor_liaison").strip()
    print(f"[vendor_clearance] liaison answered legal: {question[:50]!r} → {answer[:60]!r}", flush=True)
    return answer


def _apply_legal(report: dict, passed: bool, contract_id: str,
                 vendor_id: str = "", safety_cert: str = "") -> None:
    """Merge the legal outcome into the clearance report."""
    if passed:
        report["status"] = "cleared"
        vid = vendor_id or "the vendor"
        cid = contract_id or "executed"
        cert = f" · safety cert {safety_cert}" if safety_cert else ""
        report["legal_cleared"] = (
            f"✅ Vendor {vid} legally cleared — "
            f"licensing contract {cid} executed{cert}."
        )
    else:
        report["status"] = "blocked"
        report.setdefault("issues", []).append({
            "element_id": "legal", "issue_type": "legal_failed", "severity": "critical",
            "description": "Legal clearance did not pass.",
        })


MAX_LEGAL_ROUNDS = 5


@node(name="clearance", rerun_on_resume=True)
@instrument_node("vendor_clearance")
async def clearance(ctx: Context, node_input):
    """Run the clearance reasoner and emit its report. (The reasoner is a local LlmAgent,
    so it runs via ctx.run_node — same as the orchestrator runs its LLM helpers.)"""
    # The orchestrator's contract_finalize node marks its brief with FINALIZE-CONTRACT —
    # a deterministic marker (not an LLM signal) the legal node triggers on.
    text = _text_of(node_input) if hasattr(node_input, "parts") else (node_input if isinstance(node_input, str) else "")
    finalize_requested = "FINALIZE-CONTRACT" in (text or "")
    await ctx.run_node(clearance_reasoner, node_input)
    report = _parse_report(_latest_text(ctx, "clearance_reasoner")) or {"status": "blocked", "issues": []}
    report.pop("legal_request", None)   # the legal trigger is the update_vendor fact
    report["agent"] = "vendor_clearance_agent"
    yield Event(output=report, state={"finalize_requested": finalize_requested})


@node(name="legal_clearance", rerun_on_resume=True)
@instrument_node("vendor_clearance")
async def legal_clearance(ctx: Context, node_input):
    """DISTINCT node for the legal hand-off (visible in the trace). Goes back and forth
    with the independent legal agent (the app never touches it):
      - legal `ask_vendor` → the liaison answers it here and we re-brief legal (Flow A);
      - legal `needs_user`  → we propagate it up as `needs_input` (Flow B); the audit
        re-runs with the user's answer, which re-enters this node and resumes legal;
      - legal `done`        → merge the contract into the report.
    Runs only when a category was onboarded, or when resuming a legal Q&A."""
    report = node_input if isinstance(node_input, dict) else {}
    lr = _needs_legal(ctx, report)
    if not lr or not _LEGAL_URL:
        yield Event(output=report)
        return

    # The legal hand-off is REALLY happening (this node also runs as a no-op
    # pass-through on audits with no legal work, so its own started/completed events
    # can't mean "legal is working"). This dedicated `node: legal` event makes the
    # Legal node appear in the Workflow graph the moment the hand-off starts.
    emit_event("vendor_clearance", "started", node="legal",
               detail=f"hand-off: {lr.get('vendor_id')} × {lr.get('category')}")

    clarifications: list = []
    for _ in range(MAX_LEGAL_ROUNDS):
        try:
            raw = await _call_legal(_legal_brief(lr, report, clarifications))
        except Exception as e:
            print(f"[vendor_clearance] legal call failed: {type(e).__name__}: {e}", flush=True)
            raw = ""
        result = _parse_report(raw)
        status = str(result.get("status", "")).lower()
        print(f"[vendor_clearance] legal replied status={status!r}: {raw[:160]!r}", flush=True)

        if status == "ask_vendor":                       # Flow A — answer it ourselves
            answer = await _liaison_answer(ctx, result.get("question", ""), lr)
            clarifications.append(f"{result.get('question', '')} Answer: {answer}")
            continue

        if status == "needs_user":                       # Flow B — propagate up to the user
            report["status"] = "needs_input"
            report["question"] = result.get("question", "")
            report["needs"] = result.get("needs") or ["legal_safety_cert"]
            print(f"[vendor_clearance] legal → USER: {report['question'][:70]!r}", flush=True)
            emit_event("vendor_clearance", "needs_input", node="legal",
                       detail=report["question"][:120])
            yield Event(output=report)
            return

        # Terminal — but ONLY an actual executed contract id (LC-####) counts as done.
        # A bare `{"status":"done"}` (no upsert_contract happened), an `answer` shape,
        # or a malformed reply gets a re-brief demanding the real execution, instead of
        # silently counting as success.
        m = re.search(r"LC-\w+", json.dumps(result) + raw)
        cid = result.get("contract_id") or (m.group(0) if m else "")
        if not cid:
            clarifications.append(
                "Your last reply was not a valid outcome — a `done` reply is only valid "
                "AFTER you have actually run the legal steps and called upsert_contract, "
                "and it must carry the real contract_id (LC-####) plus the safety_cert "
                "you used. Execute the process now and reply with exactly ONE JSON "
                "object in the `done` shape, or `ask_vendor` if a fact is genuinely "
                "missing."
            )
            continue
        _apply_legal(report, True, cid,
                     vendor_id=lr.get("vendor_id", ""), safety_cert=result.get("safety_cert", ""))
        emit_event("vendor_clearance", "completed", node="legal", status="cleared",
                   detail=f"contract {cid} executed")
        break
    else:
        # Loop exhausted without an executed contract — legal did NOT clear it.
        print("[vendor_clearance] legal never reached `done` — reporting blocked", flush=True)
        _apply_legal(report, False, "", vendor_id=lr.get("vendor_id", ""))
        emit_event("vendor_clearance", "failed", node="legal", status="blocked",
                   detail="legal never reached done")
    yield Event(output=report)


@instrument_node("vendor_clearance")
def finalize(node_input):
    """Emit the final ClearanceReport — content is what A2A surfaces to the orchestrator."""
    report = node_input if isinstance(node_input, dict) else {}
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(report))]))
    yield Event(output=report)


# A declarative graph, so each step is its own node in the workflow trace:
#   START → clearance → legal_clearance → finalize
root_agent = Workflow(
    name="vendor_clearance",
    edges=[
        ("START", clearance),
        (clearance, legal_clearance),
        (legal_clearance, finalize),
    ],
)

"""A drop-in RemoteA2aAgent that hides this mesh's A2A transport specifics.

Construct `VibeflixRemoteA2aAgent` EXACTLY like ADK's `RemoteA2aAgent` — it is a subclass, so
it plugs into `sub_agents=[...]`, `ctx.run_node(...)`, and native `input_required` HITL
tunneling like any ADK agent. What it hides:

  * AUTH — injects `cloud_auth.GoogleAuth` (via `maybe_auth()`), which emits the right header
    shape everywhere: inside an engine to an mtls host it sets Authorization AND
    Proxy-Authorization to the cert-bound access token (fuse-safe via `_MINTER`); off-engine a
    direct bearer; locally None (matches the upstream A2A sample). No caller ever wires auth.
  * ENGINE DISCOVERY — Agent Runtime engines serve the card at `{base}/a2a/v1/card` (needs
    `supports_authenticated_extended_card=True` on the deployed card — done fleet-wide
    2026-07-30, see memory `engine-a2a-card-flag`) but ADVERTISE the plain aiplatform host in
    it. Engine egress is gateway-registered for the `.mtls` host only, so we repoint the RPC at
    the mtls `/a2a` base after fetching the card.

A caller writes the SAME thing as the upstream sample, just with our env URL:

    from vibeflix_common.remote_agent import VibeflixRemoteA2aAgent

    legal_agent = VibeflixRemoteA2aAgent(
        name="legal",
        description="Legal clearance over A2A.",
        agent_card=os.environ["LEGAL_A2A_URL"],   # engine base, full card URL, or Cloud Run URL
    )

HOW TO DRIVE IT — prefer the caller's OWN invocation, don't spin up a second Runner:

    * Inside a Workflow node (vendor_clearance, orchestrator, deal_pricing) you already have a
      `ctx` with a live Runner behind it. Drive the remote through it — the reply is the return
      value, and, crucially, run_node PROPAGATES a HITL interrupt (input_required) up into the
      current invocation, which a nested Runner cannot do:

          report = await ctx.run_node(legal_agent, brief)   # -> the remote's output

      or make it a real `sub_agent` on the Workflow for the same reason. This is the idiomatic
      path and the one that unlocks native park/resume.

    Every A2A caller in this mesh is inside a Workflow node, so `ctx.run_node` covers them all.
    The one ctx-less caller — the app (a FastAPI handler) — already owns a long-lived Runner
    (`_run_orchestrator`) for this, so there is intentionally no ctx-less `send()` helper here.

PROVEN 2026-07-30 (real infra): card served fleet-wide; this client resolves it and drives a
full on_message_send round-trip both from a laptop and from INSIDE an engine (dual-auth through
the gateway).

NOT handled here (transport-independent, Phase 4/5): HITL wants to HOLD one task across a pause,
whereas a plain re-invoke gets a fresh task. Also: calling the SAME remote-agent instance more
than once within one session reuses the COMPLETED A2A task (the documented reason
vendor_clearance historically used a fresh-context sender, agent.py:50) — the dispatch-loop /
self-heal re-run case. Resolving both needs a LongRunningFunctionTool on the leaf +
invocation_id/task_id threading + app-side resume-with-function-response.
"""
from __future__ import annotations

import httpx
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.events.event import Event
from google.genai import types as _genai_types

from .cloud_auth import is_engine_url, maybe_auth

_DEFAULT_TIMEOUT = 300.0
_CARD_SUFFIX = "/a2a/v1/card"


class VibeflixRemoteA2aAgent(RemoteA2aAgent):
    """RemoteA2aAgent with this mesh's auth + Agent Runtime card handling baked in.

    `agent_card` accepts, in addition to everything ADK's RemoteA2aAgent takes:
      * an engine A2A BASE url (e.g. the `LEGAL_A2A_URL` env var) — normalized to its card route;
      * a full engine card url (`.../a2a/v1/card`) — used as-is;
    Non-engine URLs, file paths, and AgentCard objects pass through unchanged.
    """

    def __init__(self, name: str, agent_card, *, timeout: float = _DEFAULT_TIMEOUT,
                 long_running: bool = False, **kwargs):
        """
        long_running: this hop can outlive Agent Runtime's ~180s blocking-request ceiling, so
          send non-blocking and poll instead of holding one request open. See _run_async_impl.
          Everything else — construction, ctx.run_node, HITL, the overrides below — is identical,
          so call sites stay uniform whichever transport a hop needs.
        """
        engine_base = None
        if isinstance(agent_card, str) and is_engine_url(agent_card):
            base = agent_card.rstrip("/")
            for suffix in (_CARD_SUFFIX, "/a2a"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            engine_base = base
            agent_card = f"{base}{_CARD_SUFFIX}"   # the discovery-card route super() will fetch
        super().__init__(name=name, agent_card=agent_card, timeout=timeout, **kwargs)
        # set AFTER super() — RemoteA2aAgent is a pydantic model and rejects unknown attrs before
        # its own __init__ has run.
        object.__setattr__(self, "_long_running", long_running)
        object.__setattr__(self, "_engine_base", engine_base)

    async def _run_async_impl(self, ctx):
        """Stock ADK transport, except on hops that can run long.

        WHY THE BRANCH EXISTS (measured in-engine, 2026-08-02):
        the stock path sends `blocking: true` — ONE long HTTP request. Agent Runtime kills that
        at ~180s with `400 FAILED_PRECONDITION` ("Reasoning Engine Execution failed", Error
        Details EMPTY) *while the callee keeps working normally*, so the caller gets nothing and
        no reason. Same A2A protocol, different pacing: `message:send` WITHOUT blocking returns
        in <1s with a task id, then poll `tasks/{id}` — no single request is ever long, so the
        ceiling is never met. That is the only difference; the card handling, auth and brief
        override above apply identically.

        Fast hops keep the stock path deliberately: this is a demo, and the prebuilt client is
        what it is meant to show.
        """
        if not self._long_running or not self._engine_base:
            async for event in super()._run_async_impl(ctx):
                yield event
            return

        from google.genai import types as _t
        from .a2a_engine import a2a_engine_send

        # Same brief extraction the override below uses, so both transports send the same thing.
        text = ""
        uc = getattr(ctx, "user_content", None)
        if uc and getattr(uc, "parts", None):
            text = "".join(getattr(p, "text", "") or "" for p in uc.parts)
        if not text:
            for ev in reversed(ctx.session.events):
                c = getattr(ev, "content", None)
                if c and getattr(c, "parts", None):
                    t = "".join(getattr(p, "text", "") or "" for p in c.parts)
                    if t and "__plan__" not in t:
                        text = t
                        break
        reply = await a2a_engine_send(self._engine_base, text, timeout=1800.0)
        yield Event(author=self.name,
                    content=_t.Content(role="model", parts=[_t.Part(text=reply)]))

    async def _ensure_httpx_client(self) -> httpx.AsyncClient:
        # Inject our auth lazily so the parent still owns cleanup (it only closes clients it
        # believes it created; we mark this one for cleanup and let super() do the rest).
        if not self._httpx_client:
            self._httpx_client = httpx.AsyncClient(
                auth=maybe_auth(), timeout=httpx.Timeout(timeout=self._timeout))
            self._httpx_client_needs_cleanup = True
        # NOTE (tested 2026-07-31): streaming=True is NOT a fix here. Against these Agent Runtime
        # engines the a2a message:stream path returns a SINGLE event echoing the request (no
        # report), even direct from a laptop (no gateway) — the card advertises streaming:True but
        # the A2aAgent template's stream doesn't line up with the http_json client stream. So we
        # leave super()'s default (streaming=False, blocking message:send). The consequence — long
        # jobs time out to a 'working' task native reads as a pause — is why native is used ONLY on
        # the HITL hop (where pause-on-working is desired), not for request/response hops.
        return await super()._ensure_httpx_client()

    async def _resolve_agent_card(self):
        card = await super()._resolve_agent_card()
        # Engines advertise the PLAIN host in the card, but egress is gateway-registered for the
        # mtls host — repoint the RPC at the mtls /a2a base we actually fetched the card from.
        src = self._agent_card_source
        if isinstance(src, str) and is_engine_url(src) and src.endswith(_CARD_SUFFIX):
            card.url = src[: -len("/v1/card")]   # -> {mtls}/a2a
        return card

    def _construct_message_parts_from_session(self, ctx):
        """Send the EXPLICIT brief, not session-history-derived content.

        Stock RemoteA2aAgent rebuilds its outgoing message by scanning session events, which
        DROPS the specific brief passed to `ctx.run_node` — verified in cloud: contract_finalize's
        "FINALIZE-CONTRACT" brief was lost and no contract executed (raw a2a_engine_send, which
        sends the explicit brief, produced LC-215400 on identical input). This mirrors
        direct_engine_agent's extraction (ctx.user_content, else the last real user text) so each
        hop receives exactly the brief the caller intended. We still return super()'s recovered
        `context_id` so HITL continuity is preserved; only the message PARTS change. The
        function-response resume path (`_create_a2a_request_for_user_function_response`) is
        separate and unaffected.
        """
        _, context_id = super()._construct_message_parts_from_session(ctx)
        text = ""
        uc = getattr(ctx, "user_content", None)
        if uc and getattr(uc, "parts", None):
            text = "".join(getattr(p, "text", "") or "" for p in uc.parts)
        if not text:
            for ev in reversed(ctx.session.events):
                c = getattr(ev, "content", None)
                if c and getattr(c, "parts", None):
                    t = "".join(getattr(p, "text", "") or "" for p in c.parts)
                    if t and "__plan__" not in t:
                        text = t
                        break
        parts: list = []
        if text:
            converted = self._genai_part_converter(_genai_types.Part(text=text))
            parts = converted if isinstance(converted, list) else ([converted] if converted else [])
        return parts, context_id


# ── STATUS 2026-08-02: WIRED IN for the two fast dispatch hops ────────────────────────────
#
# `orchestrator/agent.py::_NATIVE_A2A = {"brand_style_compliance_agent", "deal_pricing_agent"}`
# now builds these two through this class instead of the poll-based sender. This is a DEMO, so
# the prebuilt ADK client is the thing worth showing — the two overrides below are the minimum
# needed to make it work on Agent Runtime, and each is there for a measured reason:
#
#   _resolve_agent_card  — the A2aAgent template hardcodes the PLAIN aiplatform host into the
#     card it serves (templates/a2a.py:328, overwriting whatever the deployer set; no flag
#     exists). The gateway authorizes only the .mtls host: measured in-engine against three
#     peers, plain → 403 `Egress request is not authorized`, mtls → 200. Standard A2A clients
#     follow card.url (a2a/client/transports/rest.py:57), so without this repoint every
#     agent-to-agent call from a gateway-attached engine is refused.
#
#   _construct_message_parts_from_session — stock builds the outgoing message from
#     ctx.session.events and never sees the brief handed to ctx.run_node (ADK's run_node passes
#     node_input to the scheduler, NOT into the session — confirmed in source). Without this,
#     each hop silently receives session history instead of the brief the caller intended.
#
# WHY ONLY THESE TWO. The native client sends `blocking: true`, holding ONE long HTTP request.
# Measured in-engine 2026-08-02: that dies at ~180s with `400 FAILED_PRECONDITION` ("Reasoning
# Engine Execution failed", Error Details EMPTY) while the callee is still working normally.
# brand_style (~18s) and deal_pricing (~9-20s) finish well inside it. Anything that can run long
# — vendor_clearance (it fans into legal), contract_finalize, app → orchestrator — MUST stay on
# a2a_engine_send, which never makes a long request: it sends non-blocking and polls.
# Full evidence: eng-report/UPSTREAM-FR-a2a-client-gaps.md + a2a-migration-plan.md.
#
# ── Adoption sketch for the REMAINING hops (blocked on the 180s ceiling above) ──
#
# Every A2A caller in this mesh is INSIDE a Workflow node — so every one has a `ctx` and drives
# the remote through it. There is deliberately NO ctx-less `send()` helper here: it would only
# manufacture a throwaway Runner, which can't tunnel HITL, and nothing in the mesh needs it.
#
# vendor_clearance/agent.py :: the legal node calls `_call_legal(brief)` -> a2a_engine_send.
# The idiomatic swap keeps the caller's ctx (module-level agent, driven per call):
#
#     from vibeflix_common.remote_agent import VibeflixRemoteA2aAgent
#     _legal_agent = VibeflixRemoteA2aAgent(name="legal", agent_card=_LEGAL_URL,
#                                           description="Legal clearance over A2A.")
#     ...
#     raw = await ctx.run_node(_legal_agent, brief)   # was: await _call_legal(brief)
#
# This reuses the live invocation, returns legal's reply, and lets a legal input_required
# tunnel up. Same shape for orchestrator -> workflows / contract_finalize -> vendor_clearance.
# (Watch the same-instance-per-session completed-task-reuse caveat above — the dispatch-loop /
# self-heal re-run is where it bites; that's the Phase-4 lifecycle work.)
#
# The ONLY ctx-less A2A caller is the APP (agents/app.py, a FastAPI handler) — and it already
# owns a long-lived Runner for exactly this (`_run_orchestrator` / `_orchestrator_agent`). If it
# ever moves to this subclass, it reuses THAT runner; it does not need a per-call helper either.
#
# Adopt one hop at a time; keep a2a_engine_send on the rest until proven equivalent under the
# mesh's long-poll / 404-replica / token-expiry-mid-poll conditions those senders were hardened
# for.

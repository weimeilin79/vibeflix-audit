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

    def __init__(self, name: str, agent_card, *, timeout: float = _DEFAULT_TIMEOUT, **kwargs):
        if isinstance(agent_card, str) and is_engine_url(agent_card):
            base = agent_card.rstrip("/")
            for suffix in (_CARD_SUFFIX, "/a2a"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            agent_card = f"{base}{_CARD_SUFFIX}"   # the discovery-card route super() will fetch
        super().__init__(name=name, agent_card=agent_card, timeout=timeout, **kwargs)

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


# ── Adoption sketch (needs the Phase 4/5 HITL work + load re-validation before wiring in) ──
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

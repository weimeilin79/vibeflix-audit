"""Build an A2A AgentCard ourselves, instead of fetching the one the platform serves.

WHY THIS EXISTS
---------------
`vertexai/agent_engines/templates/a2a.py` (~line 328) OVERWRITES the card's url at engine
start-up with a hardcoded value:

    https://{location}-aiplatform.googleapis.com/{version}/projects/…/reasoningEngines/…/a2a

— always the **plain** aiplatform host, whatever the deployer set, with no flag to change it
(the A2A template reads no mtls env var at all; its sibling `adk.py` does). Standard A2A clients
then follow that url: `a2a/client/transports/rest.py` does `self.url = agent_card.url`.

That is fine for a caller that is NOT behind the Agent Gateway (the app on Cloud Run). It is
fatal for a caller that IS: the gateway authorizes only the `.mtls` host and answers the plain
one with `403 Egress request is not authorized` — measured in-engine against three peer agents.

So: build the card, point it at the host the CALLER may use, and hand it to `RemoteA2aAgent`.
`RemoteA2aAgent` accepts an `AgentCard` object, so nothing is fetched and nothing is overwritten.

MEASURED (2026-08-02, inside a gateway-attached engine, control passing in the same run):
  platform-served card (plain host)  → 403 Egress request is not authorized
  self-built card (mtls host)        → 200, real payload

⚠️ ONLY FOR HOPS THAT FINISH QUICKLY. The stock client sends `blocking: true`, holding one long
HTTP request; that hits a ~180s ceiling and returns `400 FAILED_PRECONDITION` ("Reasoning Engine
Execution failed", `Error Details:` empty) while the target engine is still working normally.
`a2a_engine.py` avoids this by never making a long request — it sends non-blocking and polls.
Long hops (legal, contract_finalize, orchestrator) must stay on that sender.

⚠️ ALSO: `RemoteA2aAgent` builds its outgoing message from `ctx.session.events`
(`_construct_message_parts_from_session`) and IGNORES a brief passed to `ctx.run_node(agent,
brief)`. Only use it where the brief IS the session's message (e.g. a Runner turn), not for the
orchestrator's dispatch, which passes an explicit brief.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from a2a.types import AgentCard


def engine_card(engine_a2a_base: str, name: str, description: str = "") -> "AgentCard":
    """An AgentCard for an Agent-Runtime engine, on the host the caller supplies.

    Args:
      engine_a2a_base: the engine's A2A base, e.g.
        https://us-central1-aiplatform.googleapis.com/v1beta1/projects/…/reasoningEngines/ID
        Use the `.mtls` host when the CALLER is a gateway-attached engine; the plain host is
        fine from Cloud Run. (This is exactly the value already in BRAND_STYLE_A2A_URL etc.)
      name: the ADK agent name — the orchestrator's graph references agents by name.
      description: shown to the model when it reasons about which agent to use.

    Returns:
      An AgentCard whose `url` is `{engine_a2a_base}/a2a` — the RPC base the a2a client calls.
    """
    from a2a.types import AgentCapabilities, AgentCard

    return AgentCard(
        name=name,
        description=description or f"{name} over A2A",
        url=f"{engine_a2a_base.rstrip('/')}/a2a",
        version="1.0.0",
        # streaming=False on purpose: Agent Runtime's managed layer forwards only the opening
        # `submitted` SSE event and then drops the stream (see eng-report/UPSTREAM-BUG-agent-
        # engine-a2a-sse.md), so advertising streaming buys nothing and makes some clients
        # choose a transport that cannot deliver a result.
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        preferred_transport="HTTP+JSON",
        skills=[],
    )

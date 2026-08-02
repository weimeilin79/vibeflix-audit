"""A2A — how one agent talks to another.

Everything about the agent-to-agent wire lives here: building the call, making it,
serving it, and storing the task it creates.

    card.py          build an AgentCard ourselves (the platform's card names a host
                     the Agent Gateway refuses)
    compat.py        bridge the a2a.types names google-adk 2.3 and vertexai disagree on
    engine.py        the POLL-based client for Agent-Runtime engines — send non-blocking,
                     poll tasks/{id}. The only transport that survives a hop over ~180s.
    remote_agent.py  VibeflixRemoteA2aAgent — ADK's stock RemoteA2aAgent with this mesh's
                     card handling, auth and brief-override folded in
    serve.py         the other direction: serve one domain agent AS an A2A service
                     (the Dockerfile.agent entrypoint)
    task_store.py    one task store shared by the whole engine fleet, because replicas
                     have no session affinity

Imported by: agents/, deploy/, tests/.
"""

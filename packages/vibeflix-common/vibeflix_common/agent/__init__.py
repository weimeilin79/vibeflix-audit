"""Agent — what you build an ADK agent out of.

The pieces an agent author reaches for. Nothing here knows about transport or deploy.

    models.py        one Gemini factory for the whole mesh, with the 429 retry policy
    mcp_clients.py   connect an agent to the decoupled MCP servers over the network
    memory.py        env-gated session / memory / artifact services
    image_input.py   put a mockup image into the message the model reads
    schema_guard.py  keep an output_schema agent alive when the model replies in prose
    tool_guard.py    fail CLOSED when an agent's MCP toolset didn't load
    a2ui_format.py   the A2UI contract, wrapping the official a2ui-agent-sdk

Imported by: agents/ only.
"""

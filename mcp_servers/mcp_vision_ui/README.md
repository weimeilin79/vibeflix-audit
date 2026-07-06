# mcp_vision_ui — Vision & UI Services

A FastMCP server with the mockup **parse** and the **A2UI canvas helpers**. Fully
deterministic — no LLM. The branding compliance checks live in the separate
`mcp_brand_style` server.

Runs over **stdio** (agent-spawned) or **streamable-HTTP** at `/mcp` when
`MCP_TRANSPORT=streamable-http` (default port `9001`).

## Tools

| Tool | Purpose |
|------|---------|
| `parse_design_elements(image_path)` | Canned structural parse → `{extracted_text[], printed_medium, detected_logos, primary_colors}`. The `brand_style` agent uses it as an **extraction fallback** when it has no real image pixels. |
| `deploy_audit_canvas(json_schema)` | Registers an A2UI layout schema (counts its `components`). *Stub — does not push to a live browser yet.* |
| `flash_threat_vector(element_id, severity, text)` | Marks/highlights a component on the canvas (e.g. red border + error bubble). *Stub.* |

> `deploy_audit_canvas` / `flash_threat_vector` are the A2UI "painting" helpers.
> They currently return canned confirmations and are **not** wired to the React
> frontend — build a render workflow + frontend consumer to make them real.

## Run / test locally

```bash
MCP_TRANSPORT=streamable-http HOST=127.0.0.1 PORT=9001 \
  python mcp_servers/mcp_vision_ui/server.py
# or all MCP servers at once:
./run_local.sh mcp
```

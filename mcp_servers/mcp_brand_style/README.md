# mcp_brand_style — Brand Style Compliance Registry

A FastMCP server hosting the **brand-compliance pipeline** as a single function.
**Fully deterministic — no LLM.** The agent extracts the inputs and calls the one
tool; it does **not** orchestrate the individual checks. (The vision/UI helpers
live separately in `mcp_vision_ui`.)

```
brand_style agent (LLM)                    mcp_brand_style (deterministic)
  extract {text, medium, image_uri} ──▶    run_brand_audit(text, medium, image_uri)
                                             ├─ _check_typos(text)
                                             ├─ _check_printed_medium(medium)
                                             └─ _check_asset_source(image_uri)
  report ◀──────────────────────────────────  {status, checks, checks_run, findings}
```

Runs over **stdio** (agent-spawned) or **streamable-HTTP** at `/mcp` when
`MCP_TRANSPORT=streamable-http` (default port `9004`).

## Tool

**`run_brand_audit(text, medium, image_uri) -> JSON`** — runs the fixed pipeline
in one call and returns the merged result:

```json
{ "audit": "brand_compliance", "status": "flagged"|"compliant",
  "checks": {"typo": "...", "printed_medium": "...", "asset_source": "..."},
  "checks_run": ["typo","printed_medium","asset_source"], "findings": [ ... ] }
```

Internal steps (not exposed as tools):

| Step | Checks | Statuses |
|------|--------|----------|
| `_check_typos(text)` | spellcheck (pyspellchecker); brand terms allow-listed | `flagged` / `clean` |
| `_check_printed_medium(medium)` | contains-match vs `_ALLOWED_PRINTED_MEDIA` | `approved` / `flagged` / `unknown` |
| `_check_asset_source(image_uri)` | image link vs `_APPROVED_ASSET_SOURCES` (gs:// / https) | `approved` / `flagged` / `unknown` |

The **agent** decides whether it has enough to run: with no image link it returns
`needs_input` and asks the user (a `gs://` Cloud Storage URI) before calling
`run_brand_audit`.

## Design notes

- **One function = the whole deterministic workflow.** The pipeline order and merge
  live in code, not in the LLM's tool-calling. The agent only extracts + calls it.
- **No LLM, no image processing.** Extraction is the agent's job; this server runs
  the checks on the extracted fields + the image link.
- **Self-contained allowlists** (`_BRAND_ALLOWLIST`, `_ALLOWED_PRINTED_MEDIA`,
  `_APPROVED_ASSET_SOURCES`); swap them for a real registry / bucket policy to make
  the checks "real".

## Run / test locally

```bash
MCP_TRANSPORT=streamable-http HOST=127.0.0.1 PORT=9004 \
  python mcp_servers/mcp_brand_style/server.py
# or all MCP servers at once:
./run_local.sh mcp
```

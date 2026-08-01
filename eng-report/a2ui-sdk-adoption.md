# A2UI SDK Adoption — Recipe + Plan (spike-verified)

**Date:** 2026-08-01 · **Status:** spike passed; implementing.

## Spike verdict (all gates passed)
- `a2ui-agent-sdk==0.5.0` (+ a2ui-core, antlr4) **installs on py3.14 via uv** — pure-python, no fragility.
- Ships **v0.8 assets** (`a2ui/assets/0.8/`): `server_to_client.json` → message names
  `surfaceUpdate`/`beginRendering`/`dataModelUpdate` (match `@a2ui/react@0.10`), and
  `standard_catalog_definition.json` → catalog **Text/Card/Column/Divider + Row/List/Button/…**
  (superset of our 4).
- **Proven with Gemini:** SDK's v0.8 prompt drove the model to emit valid v0.8 A2UI
  (`<a2ui-json>[{"messageType":"beginRendering"…},{"messageType":"surfaceUpdate"…}]`).

## Integration recipe (copy-paste)
```python
import a2ui, os
from a2ui.schema.catalog_provider import FileSystemCatalogProvider
from a2ui.schema.catalog import CatalogConfig
from a2ui.inference_formats.direct_json import DirectJsonFormat
from a2ui.schema.validator import A2uiValidator

_cat = os.path.join(a2ui.__path__[0], "assets", "0.8", "standard_catalog_definition.json")
fmt = DirectJsonFormat(version="0.8",
        catalogs=[CatalogConfig(name="standard", provider=FileSystemCatalogProvider(_cat))])
catalog = fmt.get_selected_catalog()
prompt  = fmt.prompt_generator.generate(role_description="…", allowed_components=["Text","Card","Column","Divider"])
# parse+heal the agent's <a2ui-json> output with fmt.parser / DirectJsonStreamParser(catalog)
A2uiValidator(catalog).validate(messages)   # raises on invalid
```

## The envelope question — RESOLVED by architecture
The SDK emits `{"messageType":"surfaceUpdate",…}` wrapped in `<a2ui-json>` tags; our frontend
renders `{"surfaceUpdate":{…}}` today. We DON'T need @a2ui/react to accept the SDK envelope: the
**app stays the wire authority**. Flow:
- ui_renderer agent: instruction = SDK-generated prompt → emits SDK-format A2UI.
- app `_present`: SDK parser strips `<a2ui-json>` + heals → component objects; `A2uiValidator` validates.
- `a2ui_surface.stream_panel`: serialize those components into our proven `{surfaceUpdate:{…}}` wire +
  namespace into `card{i}` (mechanical, no layout decisions).

So the SDK replaces the **catalog + prompt + validation + healing** (agent side); the app keeps
owning the wire envelope. Deletes: hand-rolled `A2UINode`, `_valid_a2ui_panel`, the hand-written
catalog rules in `render-a2ui/SKILL.md`.

## Implementation steps
1. `agents/ui_renderer/requirements.txt` + `agents/requirements.txt`: add `a2ui-agent-sdk`.
2. `ui_renderer/agent.py`: build the format once; instruction = SDK prompt (report task); drop `A2UINode`/`output_schema` for the report task. Keep the form-design task.
3. `agents/app.py` `_present`: parse via SDK (heal) + `A2uiValidator`; return the panel's components. Drop `_valid_a2ui_panel`.
4. `agents/a2ui_surface.py` `stream_panel`: serialize SDK components → wire + namespace; adapt `panels_fallback` to the same shape.
5. Deploy ui_renderer (Agent Engine) + app (Cloud Run) — **verify the dep builds in both**.
6. Validate on cloud (blank-check + valid render), then delete the hand-rolled code.

## Integration friction found (2026-08-01 push-through attempt) — resolve these first
The spike gates all passed, but the END-TO-END (Gemini → SDK parse → validate) hit real rough
edges. NOT a clean swap; needs a dedicated pass. Concrete blockers:
1. **`DirectJsonParser.parse_response(out)` rejected the model output** — `A2uiCompilationError:
   Additional properties are not allowed ('messages' was unexpected)`. The model wrapped its
   output as `{"messages":[…]}`; the parser expects a different envelope. → Use the STREAMING
   parser (`DirectJsonStreamParser.process_chunk` + `yield_reachable`) which is the intended
   resilient path, and/or pin the prompt so the emitted envelope matches the parser.
2. **Model output format is non-deterministic** across runs: `{"messageType":"surfaceUpdate"}` vs
   `{"type":"surfaceUpdate"}` vs `{"messages":[…]}`. The hand-tweaked `role_description` wasn't
   enough — use the SDK's generated prompt more faithfully (don't over-edit it) so the format is pinned.
3. **Bundled 0.8 catalog lacks `catalogId`** → `A2uiCatalogError: Catalog 'standard' missing
   catalogId` when `include_examples=True` (and example loading). Loading
   `assets/0.8/standard_catalog_definition.json` via `FileSystemCatalogProvider` yields a catalog
   with no id. → Provide a proper catalog object WITH an id (wrap the def, or find the right
   catalog asset/loader), or avoid `include_examples`.

**Decision (2026-08-01):** did NOT deploy the SDK version — the working hand-rolled Tier-2 (app
rev 00057) stays live. The SDK adoption is viable but requires a dedicated pass to resolve the
above (catalog id + streaming parser + prompt pinning). `a2ui-agent-sdk==0.5.0` is installed in
`.venv` but wired into NO repo code yet — nothing to clean up; repo is on the working version.

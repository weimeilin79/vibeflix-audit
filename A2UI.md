# A2UI in Vibeflix

How the audit console's UI gets drawn: **the agent decides what the panel looks like, the
browser renders it, and the app is the plumbing in between.** Nothing here is hand-rolled
protocol any more — the contract comes from the A2UI spec via the official
`a2ui-agent-sdk`.

**Status:** implemented and verified locally. **Not deployed** — the cloud is still running the
previous hand-rolled version (app rev 00057).

---

## 1. The idea

A2UI is a wire protocol for *agent-drawn UI*. The agent sends a **flat list of components**
(`Text`, `Card`, `Column`, `Divider`) that reference each other by `id`; the client keeps a
**catalog** of those components and paints them. Flat-with-id-references is deliberate: it is
easy for an LLM to emit, and it streams — the renderer can patch each component in as it
arrives, instead of waiting for a whole nested tree.

Three parties, three jobs:

| | who | job |
|---|---|---|
| **Agent** | `ui_renderer` (:8004, its own A2A service) | decides the panel's *layout and words* → emits A2UI |
| **App** | `agents/app.py` + `agents/a2ui_surface.py` | validates it, slots it into the surface, streams it |
| **Client** | `frontend/src/ChatAudit.jsx` + `@a2ui/react` | renders it |

---

## 2. End-to-end flow

```
  operator runs an audit
        ▼
  ORCHESTRATOR (engine) runs the mesh → raw domain reports
        ▼
  APP  /api/audit/stream   (agents/app.py :: _stream_audit)   ── decides WHEN ──
        │  each time a workflow finishes:  _panel_for(agent, report)
        │        ▼
        │   UI_RENDERER agent  ← THE A2UI AUTHOR
        │     emits <a2ui-json> beginRendering + surfaceUpdate  (the real v0.8 wire)
        │     instruction = SDK-generated schema + skills/render-a2ui/SKILL.md
        │        ▼
        │   parse_panel()   (vibeflix_common/a2ui_format.py → a2ui-agent-sdk)
        │     unwrap the blocks · heal the JSON · VALIDATE against the spec
        │        │ invalid / blank ──► panels_fallback ("<name> — <status>")
        │        ▼
        │   stream_panel(i, panel)   ── MECHANICAL only ──
        │     the panel's Card → card{i} (its slot) · every other id → p{i}_…
        ▼        ▼
  SSE:  {"a2ui": {"surfaceUpdate": {surfaceId, components:[…]}}}
        ▼
  BROWSER  @a2ui/react patches components into the live surface by id → panels fill in
```

The surface is built **once, up front** (`stream_initial`: header, one pending card per
workflow, divider, closing report line, a reserved `final` slot) and then *patched*. Every later
message is a `surfaceUpdate` that redefines only the ids it carries — which is why each one must
be self-contained, and why the root component is never re-sent.

---

## 3. Files

| File | Role |
|---|---|
| `packages/vibeflix-common/vibeflix_common/a2ui_format.py` | **the A2UI contract**, wrapping `a2ui-agent-sdk`: `render_instruction` (build the agent's prompt), `parse_panel` (heal + validate), `rewrite_ids` (catalog-driven id namespacing), `text_of` |
| `agents/ui_renderer/agent.py` | the **author** — an `LlmAgent` with no tools and no `output_schema` |
| `agents/ui_renderer/skills/render-a2ui/SKILL.md` | the **layout procedure** (what to build) + the second, non-A2UI task |
| `agents/a2ui_surface.py` | the **surface** — scaffold, panel slotting, closing line, final clearance report, `panels_fallback` |
| `agents/app.py` (`_present`, `_panel_for`, `_stream_audit`) | **orchestration** — when each panel is rendered and streamed |
| `frontend/src/ChatAudit.jsx` + `@a2ui/react` | the **renderer** |

---

## 4. The agent side

The agent's instruction is assembled in `ui_renderer/agent.py` from two sources:

```
render_instruction(role_description=<SKILL.md intro>, ui_description=<SKILL.md "## The layout">)
   → our role + our layout procedure
   + the SDK's response rules (the <a2ui-json> block contract)
   + the FULL v0.8 component + message JSON schema, pruned to Text/Card/Column/Divider
+ "\n\n" + <SKILL.md "# Design the input form">        ← the second task, deliberately outside
                                                        the A2UI contract (it emits plain JSON)
```

`SKILL.md` is split on its headings, and the split **asserts** the headings exist — editing the
skill in a way that drops one fails loudly at import rather than silently shipping a presenter
with no layout procedure.

Two things worth knowing:

- **`include_schema=True` is the whole trick.** Without the schema block the model has no
  contract and invents an envelope — `{"messageType": …}` one run, `{"messages": […]}` the
  next. That non-determinism was the blocker that stalled the first adoption attempt. With the
  schema in the prompt, the emitted envelope is stable.
- **There is no `output_schema`.** A2UI blocks are a *text* format, so structured output can't
  coexist with them. The presenter's other task (`design_input_form`, which designs the
  console's dynamic form) now returns plain JSON instead. Reliability no longer comes from
  structured output — it comes from **validate-then-fallback**.

The presenter is also deliberately **tool-free**: the SDK ships a `SendA2uiToClientToolset`
(agent-sends-UI-via-tool-calls), but tool-using agents here hit Gemini's `set_model_response`
"malformed function call" flakiness, so we don't use it.

---

## 5. The wire — and why v0.8

```json
{"beginRendering": {"surfaceId": "audit", "root": "root"}}
{"surfaceUpdate": {"surfaceId": "audit", "components": [
   {"id": "card0", "component": {"Card": {"child": "p0_col"}}},
   {"id": "p0_col", "component": {"Column": {"children": {"explicitList": ["p0_t"]}}}},
   {"id": "p0_t",  "component": {"Text": {"text": {"literalString": "🎨 Brand Style — **PASS**"},
                                          "usageHint": "h5"}}}]}}
```

`@a2ui/react@0.10` speaks exactly this, and so does the SDK's **0.8** asset set
(`assets/0.8/server_to_client.json`). That alignment is the reason the pipeline has **no
envelope translation anywhere**: the agent emits the real wire format, and the app only
renames ids. Text supports simple Markdown, which is where the bold statuses come from.

0.9+ renamed the messages to `updateComponents`/`createSurface` and moved to a
`{"messageType": …}` envelope — moving there means upgrading the frontend renderer in the same
change. Two consequences of being on 0.8: validation runs through `LegacyA2uiValidatorV08`, and
the bundled 0.8 catalog has **no `catalogId`** (harmless — the id is only read for
`examples_path` and the 0.9+ validator; don't add few-shot examples without giving the catalog
an id first).

---

## 6. The app side — validate, then slot

The app authors no layout. It does exactly three things to a panel:

**Validate** (`parse_panel`). The SDK checks it against the real spec: unknown components, bad
`usageHint` enum values and dangling id references all raise. Anything that raises → the panel
falls back. This replaced a hand-written id-graph check that only approximated those rules.

**Heal, before validating.** Two LLM slips were measured at roughly 1 run in 10 each, and both
would otherwise throw away a whole good panel:

1. *Missing wrapper key* — the model emits the surfaceUpdate **body** (`{surfaceId,
   components}`) with no message name. `_unwrap_message` re-wraps it; unambiguous, because
   `components` belongs to exactly one message type.
2. *A block closed one brace short* (`…}}}]}`) — a strict JSON parse loses everything over one
   byte. The SDK's `DirectJsonStreamParser`, fed the finished response as a single chunk, closes
   what's open and yields every component. It exists to render a UI that is still arriving,
   which turns out to be the same problem. **It is the recovery path, not the primary one.**

Healed output still goes through full validation — nothing skips the spec check.

**Slot it** (`stream_panel`). The agent's ids are local to its own panel, so two panels would
collide on `card`/`col`/`t1`. Every id is namespaced `p{i}_…`, and the references *between* them
are remapped too — using the catalog's own ref-field map, so this stays correct if the allowed
component set ever changes.

The slot is always a **Card, exactly one deep** — the surface's own decision, made when the
pending placeholder was drawn. What arrives varies: the panel may be rooted in its Card (take
the slot id), in a Column wrapping that Card (descend, drop the wrapper), or in a bare Column
with no Card at all (wrap it). All three then look like every other panel — no bare panel, no
card-inside-a-card.

---

## 7. The safety net

Nothing an LLM produces reaches the browser unchecked. `panels_fallback` is a deterministic,
report-agnostic renderer that emits the **same wire shape** the agent does, so it slots
identically. It takes over when:

- the ui_renderer is unconfigured or unreachable;
- its output fails A2UI validation (after healing);
- the panel is **content-empty** — structurally valid but every `Text` blank. The spec has no
  opinion on this; it's ours, because such a panel renders as an invisible card. (That was a
  real bug once: blank panels, non-deterministic as to which workflow.)

The result is always at least `"<name> — <STATUS>"`. The console never shows a broken surface.

---

## 8. What the SDK replaced

Deleted when it came in: `A2UINode` (a pydantic mirror of the catalog), the hand-written catalog
description in `SKILL.md`, `_valid_a2ui_panel` (hand-rolled id-graph check), and `_node_to_wire`
(hand-rolled serializer). Each was a re-implementation of something the A2UI project already
ships, and each could drift from the spec without anyone noticing.

Dependency: `a2ui-agent-sdk>=0.5.0` — pure Python (`a2ui-core`, `antlr4-python3-runtime`), no
native build. It is in `agents/requirements.txt` (app), `agents/ui_renderer/requirements.txt`
(engine), and the `agents` extra of `packages/vibeflix-common/pyproject.toml`.

---

## 9. Verified

Locally, against Vertex (`pokedemo-test`):

- 22 renders across four report shapes (clean / sparse / issues / unknown workflow) — all
  parsed, validated, slotted; every id reference resolved after namespacing.
- `design_input_form` still correct without `output_schema` — tokens verbatim, `select` control
  with options, prompt present.
- Negative cases — dangling ref, unknown component, bad `usageHint`, junk text → all rejected,
  fallback taken.
- Slot normalization unit-tested across all panel shapes, including a reference cycle.
- Both Docker images build with the new dependency and import `a2ui`.
- A full happy-path audit through the local stack and the real console: three agent-emitted
  panels, the closing report line, and the final clearance report with an executed contract;
  zero dangling references across the accumulated surface.

**Remaining:** deploy `ui_renderer` (Agent Engine) and the app (Cloud Run), confirm the
dependency resolves in both cloud builds, then re-check a render in the cloud console.

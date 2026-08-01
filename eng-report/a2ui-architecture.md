# How A2UI Works in vibeflix

**Date:** 2026-08-01 · **Status:** live (Tier 1 + Tier 2 deployed; app rev 00057)

## The idea

A2UI = the **agent draws the UI, the client renders it**. The agent sends a *flat list of
components* (Text, Card, Column, Divider) that reference each other by `id`; the frontend keeps a
**catalog** of those components and paints them. After Tier 2, that's genuinely what happens here —
the `ui_renderer` agent emits the component list itself.

## End-to-end flow

```
  operator runs an audit
        ▼
  ORCHESTRATOR (engine) runs the mesh → raw domain reports
        ▼
  APP  /api/audit/stream  (agents/app.py :: _stream_audit)   ── orchestrates WHEN ──
        │  as each workflow finishes:  _panel_for(agent, report)
        │        ▼
        │   UI_RENDERER agent (:8004 A2A)  ← THE A2UI AUTHOR
        │     emits that panel's A2UI: flat components + root id
        │     (output_schema = A2UINode; catalog in skills/render-a2ui/SKILL.md)
        │        ▼
        │   _valid_a2ui_panel(panel)? ── no ──► panels_fallback (deterministic "<name> — <status>")
        │        │ yes
        │        ▼
        │   stream_panel(i, panel)  ── MECHANICAL only ──
        │     root id → card{i} (slot it) · other ids → p{i}_… · A2UINode → wire JSON
        ▼        ▼
  SSE:  {"a2ui": {"surfaceUpdate": {surfaceId, components:[…]}}}  /  {"beginRendering": {root}}
        ▼
  FRONTEND  ChatAudit.jsx + @a2ui/react  ← THE RENDERER (catalog); patches by id → panels fill live
```

## Pieces

| File | Role |
|---|---|
| `agents/ui_renderer/agent.py` | A2UI **author** — `LlmAgent`, `output_schema` = flat `A2UINode` list + `root` |
| `agents/ui_renderer/skills/render-a2ui/SKILL.md` | the **catalog + rules** the agent follows |
| `agents/a2ui_surface.py` | app-side **serialize/transport** — `stream_panel` (namespace + A2UINode→wire), `panels_fallback` (deterministic net), `stream_initial`/`stream_report_line`/`stream_final_report` |
| `agents/app.py` `_stream_audit` | **orchestration** — pending cards, per-workflow fill, `_valid_a2ui_panel`, SSE `a2ui` messages |
| `frontend/src/ChatAudit.jsx` + `@a2ui/react` | the **renderer** (component catalog) |

## Wire format

`surfaceUpdate` (batch of `{id, component}`, patched by id) + `beginRendering` (sets root). These
are the **legacy v0.8** A2UI message names — still accepted by `@a2ui/react@0.10`; the current
protocol renamed them to `updateComponents`/`createSurface`. Components are a **flat list with id
cross-references** (A2UI's design, LLM-friendly, streams incrementally).

## Safety net

The agent authors the UI, but the app **validates** each panel (`_valid_a2ui_panel`: resolvable
ids + ≥1 non-empty Text) and falls back to the deterministic `panels_fallback` when the LLM emits
something malformed or blank. (The blank-panel bug was this guard missing the "all-empty" case —
fixed in rev 00057.)

## Known follow-up — adopt the official SDK

This pipeline **hand-rolls** what the official **`a2ui-agent-sdk`** (PyPI) provides:
`A2uiSchemaManager` (catalog + LLM system prompt) → replaces `A2UINode` + the hand-written catalog;
`A2uiValidator` → replaces `_valid_a2ui_panel`; `a2ui.parser.streaming` + `payload_fixer`
(resilient parse + JSON healing) → replaces `stream_panel`/`panels_fallback`/the empty guard;
`SendA2uiToClientToolset` (agent-sends-UI-via-tool-calls) is a fuller architecture. Adopting it
(light path: schema manager + validator) would delete the custom pydantic. Blocked on spiking the
dependency on Python 3.14 (known pip fragility — use `uv`).

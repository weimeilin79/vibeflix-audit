"""UI-Render Agent — the presentation LLM, its own A2A service (like the domain
agents), decoupled from the orchestrator.

The orchestrator is a deterministic coordinator that returns raw domain reports.
This agent turns those (varied, non-deterministic) reports into user-friendly
panels. It's served over A2A (serve_a2a, :8004); app.py calls it after the
orchestrator and assembles the A2UI surface deterministically (agents/a2ui_surface).

Design notes:
- The rendering PROCEDURE lives in a versioned skill (skills/render-a2ui/SKILL.md),
  loaded here as the agent's instruction — consistent with the domain agents, but
  without a SkillToolset because the presenter needs NO tools.
- The A2UI CONTRACT (catalog, message schema, response rules) is NOT ours: the official
  `a2ui-agent-sdk` renders it into the instruction from the spec assets — see
  vibeflix_common/agent/a2ui_format.py. The skill says what to build; the SDK says what's legal.
- No tools, so we avoid the `set_model_response` "malformed function call" flakiness the
  tool-using agents hit. There is no `output_schema` either: the report task emits A2UI as
  `<a2ui-json>` blocks (a text format — structured output would forbid it), so BOTH tasks
  are plain text the app parses. If a response is unparseable or fails A2UI validation,
  app.py falls back to a rule-based summary.
"""

import pathlib

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from vibeflix_common.agent.a2ui_format import render_instruction
from vibeflix_common.agent.models import gemini
# Live mesh telemetry: emit agent-level started/completed so the console's Workflow graph
# shows the UI-render agent as its own box — lit when the app calls it, terminal when it
# finishes. No-op when PUBSUB_TOPIC is unset (local/dev).
from vibeflix_common.platform.telemetry import emit_event

_SKILL = load_skill_from_dir(pathlib.Path(__file__).parent / "skills" / "render-a2ui")


def _emit_render(event: str):
    """ADK before/after_agent_callback → one agent-level mesh event (node defaults to the
    source, so the console treats it as the box's own start/stop, not a sub-step)."""
    def _cb(callback_context):
        try:
            emit_event("ui_renderer", event)
        except Exception:  # noqa: BLE001 — telemetry is best-effort, never break rendering
            pass
        return None
    return _cb


# The skill covers TWO tasks, and only the first one is A2UI. Split it so the SDK's A2UI
# rules + schema wrap the RENDER task only: the form-design task must emit a plain JSON
# object, and sitting it inside the A2UI contract invites the model to wrap that in
# `<a2ui-json>` too. Headings are asserted, not assumed — an edit to SKILL.md that drops
# one would otherwise silently ship a presenter with no layout procedure.
_LAYOUT_HEADING = "## The layout"
_FORM_HEADING = "# Design the input form"


def _sections(text: str) -> tuple[str, str, str]:
    """SKILL.md → (who you are, the A2UI layout procedure, the form-design task)."""
    for heading in (_LAYOUT_HEADING, _FORM_HEADING):
        if heading not in text:
            raise ValueError(f"render-a2ui SKILL.md is missing its '{heading}' section")
    render, form = text.split(_FORM_HEADING, 1)
    role, layout = render.split(_LAYOUT_HEADING, 1)
    return role.strip(), (_LAYOUT_HEADING + layout).strip(), (_FORM_HEADING + form).strip()


_ROLE, _LAYOUT, _FORM_TASK = _sections(_SKILL.instructions)

# instruction = OUR procedure + THE SPEC's contract (response rules + component/message
# schema, straight from the a2ui-agent-sdk assets), then the non-A2UI second task.
INSTRUCTION = f"{render_instruction(role_description=_ROLE, ui_description=_LAYOUT)}\n\n{_FORM_TASK}"


presenter_agent = LlmAgent(
    name="a2ui_presenter",
    model=gemini(),   # retries 429 with backoff — see vibeflix_common/agent/models.py
    description="Renders any set of compliance-workflow reports into A2UI panels.",
    instruction=INSTRUCTION,
    output_key="presentation",
    before_agent_callback=_emit_render("started"),
    after_agent_callback=_emit_render("completed"),
)

# ADK entrypoint convention.
root_agent = presenter_agent

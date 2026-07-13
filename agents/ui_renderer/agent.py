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
- No tools + `output_schema` → the model uses native structured output, which
  avoids the `set_model_response` "malformed function call" flakiness we see on the
  tool-using agents. If it ever does fail, app.py falls back to a rule-based summary.
"""

import pathlib

from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir

_SKILL = load_skill_from_dir(pathlib.Path(__file__).parent / "skills" / "render-a2ui")


class Line(BaseModel):
    text: str          # a clear explanation of one issue/finding (⛔ critical, ⚠️ warning)
    resolve: str = ""  # a concrete "how to resolve" suggestion


class Panel(BaseModel):
    title: str         # workflow name incl. emoji, e.g. "🎨 Brand Style"
    status: str        # the report's status, verbatim
    headline: str      # one-sentence outcome summary
    lines: list[Line] = Field(default_factory=list)


class Option(BaseModel):
    value: str
    label: str


class FieldSpec(BaseModel):
    """One input control for the console's dynamic form (task: design_input_form)."""

    name: str                # MUST equal the requested token verbatim (merged by name)
    label: str               # human-friendly title for the control
    type: str = "text"       # text | textarea | number | select
    placeholder: str = ""    # hint text incl. expected format / required sub-fields
    value: str = ""          # prefill, when a sensible value is already known
    required: bool = True
    options: list[Option] = Field(default_factory=list)   # for type=select


class Presentation(BaseModel):
    # Report-rendering task → panels; input-form design task → prompt + fields.
    panels: list[Panel] = Field(default_factory=list)
    prompt: str = ""
    fields: list[FieldSpec] = Field(default_factory=list)


presenter_agent = LlmAgent(
    name="a2ui_presenter",
    model="gemini-2.5-flash",
    description="Renders any set of compliance-workflow reports into A2UI panels.",
    instruction=_SKILL.instructions,
    output_schema=Presentation,
    output_key="presentation",
)

# ADK entrypoint convention.
root_agent = presenter_agent

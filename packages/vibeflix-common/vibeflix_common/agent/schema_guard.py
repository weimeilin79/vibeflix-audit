"""Keep an ``output_schema`` agent from crashing when the model replies in prose.

An ``LlmAgent`` with ``output_schema`` requires EVERY final model turn to be valid
JSON for that schema. If the model instead answers conversationally — e.g. you
greet it in ``adk web`` — ADK raises a ``ValidationError`` that aborts the whole
run. This ``after_model_callback`` detects a non-JSON text response and rewrites
it into a minimal valid instance of the schema (surfacing the model's text where
the schema can hold it), so the run completes instead of 500-ing.

⚠️  This is a stopgap that only makes sense WHILE the agent has ``output_schema``.
If you evolve an agent to be conversational — asking follow-up questions, routing
between workflows, collecting more input — DROP ``output_schema`` (so it can speak
freely) and capture structured output another way (a ``submit_*`` tool, or split a
conversational router from the structured workers). Once ``output_schema`` is gone
the crash this guards against can't happen, and this guard would wrongly swallow
the agent's questions — so remove it then.
"""

import json
from typing import Callable

from google.genai import types
from google.adk.models import LlmResponse


def _final_text(content) -> str | None:
    """Return the plain text of a final model turn, or None if it's a tool call."""
    if not content or not getattr(content, "parts", None):
        return None
    # A function/tool call (incl. ADK's set_model_response) is not prose — pass it.
    if any(getattr(p, "function_call", None) for p in content.parts):
        return None
    text = "".join(getattr(p, "text", "") or "" for p in content.parts).strip()
    return text or None


def _is_json(text: str) -> bool:
    cleaned = text.strip()
    for fence in ("```json", "```"):
        if cleaned.startswith(fence):
            cleaned = cleaned[len(fence):]
    cleaned = cleaned.removesuffix("```").strip()
    try:
        json.loads(cleaned)
        return True
    except ValueError:
        return False


def make_schema_guard(fallback: Callable[[str], dict]):
    """Build an ``after_model_callback`` that coerces stray prose into ``fallback(text)``.

    Args:
        fallback: maps the model's prose into a dict valid for the agent's schema.
    """
    def guard(callback_context, llm_response):
        text = _final_text(getattr(llm_response, "content", None))
        if text is None or _is_json(text):
            return None  # tool call, empty, or already valid JSON → leave untouched
        payload = json.dumps(fallback(text))
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part.from_text(text=payload)])
        )

    return guard

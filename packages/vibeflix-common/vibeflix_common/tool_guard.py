"""Fail CLOSED when an agent's MCP toolset didn't load.

When a toolset fails to initialize (MCP session refused, 401, backend down), ADK
logs `Failed to get tools from toolset …` and then runs the agent ANYWAY — with
no tools. A compliance agent in that state does the worst possible thing: it
answers from the model alone and emits a confident, clean verdict. We watched
brand_style return `status: "success"`, `findings: []` and a plausible
`checks_run` list while the MCP had, in fact, never been called once (zero
CallToolRequest in the server log; the check names even changed between runs
because the model was inventing them).

An audit that cannot run its checks must SAY SO, not pass.

Guard on the MCP TOOLSET, not on the LLM-visible tool names. When the MCP tool is
wrapped in a `SkillToolset`, the model only ever sees the skill machinery
(`list_skills`, `load_skill`, `run_skill_script`, …) — the underlying MCP tool is
NOT in `llm_request.tools_dict`, so a name check there is a false positive in
every environment, healthy or not. Ask the toolset itself whether it can reach
its server.
"""

import json
from typing import Callable

from google.adk.models import LlmResponse
from google.genai import types


def make_toolset_health_guard(
    toolset,
    *required: str,
    on_missing: Callable[[list[str]], dict],
):
    """Build a ``before_model_callback`` that refuses to run when ``toolset`` is down.

    Args:
        toolset: the ``McpToolset`` the agent's answer actually depends on (pass the
            SAME object handed to the agent, e.g. via ``SkillToolset(additional_tools=…)``).
        required: tool names that must be present on that toolset.
        on_missing: maps the missing/unreachable tool names to a dict valid for the
            agent's output_schema — the honest "I could not run" answer.
    """
    healthy = False  # once we've seen it up, don't re-probe on every model turn

    async def guard(callback_context, llm_request):
        nonlocal healthy
        if healthy:
            return None
        try:
            names = {t.name for t in await toolset.get_tools()}
            missing = [r for r in required if r not in names]
        except Exception:
            missing = list(required)
        if not missing:
            healthy = True
            return None
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json.dumps(on_missing(missing)))],
            )
        )

    return guard

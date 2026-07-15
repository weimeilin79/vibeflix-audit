"""One Gemini model factory for the whole mesh — with a retry policy that survives 429.

WHY THIS EXISTS
---------------
Every agent used to declare `model="gemini-2.5-flash"` as a plain STRING. That takes ADK's
default `Gemini(retry_options=None)`, i.e. the genai library's minimal built-in retry — which
gives up almost immediately on `429 RESOURCE_EXHAUSTED` and raises:

    google.adk.models.google_llm._ResourceExhaustedError:
    429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Resource exhausted...'}}

…which kills the agent mid-run, so the orchestrator gets no report and the audit fails.

429 is a **rate limit, not an error in our code**. It is transient by definition: Vertex's
per-minute quota refills. The only correct response is to WAIT AND RETRY — which is exactly what
the model layer is for. Measured: 11 × 429 in two hours, **all of them in `deal_pricing`** —
its evaluate→validate→iterate loop (`pricing_reasoner`) fires the most model calls in the
tightest burst, so it hits the ceiling first while the other agents sail past.

THE POLICY
----------
`HttpRetryOptions(initial_delay=1, attempts=5)` — the ADK-recommended shape:
https://adk.dev/agents/models/google-gemini/#error-code-429-resource_exhausted

Retries alone do not raise the ceiling. If 429s persist, the other half of the ADK guidance is
the real fix: **request a higher quota** for the model. Retrying buys time; it does not create
capacity.

This is a complement to, not a replacement for, the orchestrator's `recovery` node: recovery
re-runs an agent whose *report* is missing; this stops the agent dying in the first place.
"""

from google.adk.models.google_llm import Gemini
from google.genai import types

DEFAULT_MODEL = "gemini-2.5-flash"

# Per the ADK guidance for 429 RESOURCE_EXHAUSTED:
#   https://adk.dev/agents/models/google-gemini/#error-code-429-resource_exhausted
# "Enable client-side retries … Retries allow the client to automatically retry the request
#  after a delay, which can help if the quota issue is temporary."
_RETRY = types.HttpRetryOptions(initial_delay=1, attempts=5)


def gemini(model: str = DEFAULT_MODEL) -> Gemini:
    """The mesh's Gemini model: identical everywhere, and it rides out a 429."""
    return Gemini(model=model, retry_options=_RETRY)

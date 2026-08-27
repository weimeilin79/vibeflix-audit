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

# gemini-2.5-flash is the newest flash model that actually SERVES in us-central1, which is where
# the engines resolve publisher models regardless of GOOGLE_CLOUD_LOCATION=global.
#
# Do not switch to a Gemini 3.x model by reading `publishers/google/models` — that endpoint LISTS
# models (gemini-3.5-flash, 3.6, 3.7 all appear) that are not actually servable in the region, and
# a call from a `location="global"` client succeeds while the engines get:
#   404 NOT_FOUND: Publisher model `projects/<p>/locations/us-central1/.../gemini-3.5-flash`
#                  was not found or your project does not have access to it
# Verify by CALLING the model with location="us-central1" before changing this line. Measured
# 2026-08-26: 2.5-flash ✓; 3.5-flash, 3-flash-preview, 3.1-flash-lite, 3.7-flash all 404.
DEFAULT_MODEL = "gemini-2.5-flash"

# Per the ADK guidance for 429 RESOURCE_EXHAUSTED:
#   https://adk.dev/agents/models/google-gemini/#error-code-429-resource_exhausted
# "Enable client-side retries … Retries allow the client to automatically retry the request
#  after a delay, which can help if the quota issue is temporary."
# 503 UNAVAILABLE is already covered — the SDK's default retried set is
# (408, 429, 500, 502, 503, 504), listed explicitly here so the coverage is visible rather
# than inherited. What was too small is the WINDOW: attempts=5 with exponential backoff from
# 1s covers roughly 1+2+4+8 ≈ 15s, so a Vertex blip lasting longer than that exhausted the
# retries and killed the agent mid-run. Observed 2026-08-26: `503 UNAVAILABLE. The service is
# currently unavailable` surfaced through `Error handling A2A request`, ending that agent's
# branch while the rest of the audit carried on.
#
# attempts=8 with max_delay=30 gives ~1+2+4+8+16+30+30 ≈ 90s of cover, which rides out a
# minute-long blip. The cost is that a genuinely dead model call now takes ~90s to give up
# instead of ~15s; audits already run 60-200s and the app timeout is 1800s, so that is
# affordable. The orchestrator's `recovery` node remains the backstop beyond this.
_RETRY = types.HttpRetryOptions(
    initial_delay=1,
    attempts=8,
    max_delay=30,
    http_status_codes=[408, 429, 500, 502, 503, 504],
)


def gemini(model: str = DEFAULT_MODEL) -> Gemini:
    """The mesh's Gemini model: identical everywhere, and it rides out a 429."""
    return Gemini(model=model, retry_options=_RETRY)

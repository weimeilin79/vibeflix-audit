"""Layer 1 probe: every MCP-using agent → its MCP server, run N rounds.

Pass/fail is deliberately NOT the agent's self-report: an agent whose toolset is
down will still emit a confident clean verdict. The caller checks CallToolRequest
in the MCP's Cloud Run log; this script only reports what each agent returned.

    .venv/bin/python tests/a2a/layer1_probe.py [rounds]
"""

import asyncio
import sys

sys.path.insert(0, "packages/vibeflix-common")
from vibeflix_common.a2a_engine import a2a_engine_send  # noqa: E402

BASE = ("https://us-central1-aiplatform.googleapis.com/v1beta1/projects/789872749985"
        "/locations/us-central1/reasoningEngines/")

AGENTS = [
    ("brand_style", "3483603031247814656",
     "Run the brand compliance audit. image: "
     "gs://vibeflix-request-image/0aa7dd74-vendor_request_refine.png ; "
     "character: grogu ; medium: vinyl figures"),
    ("vendor_clr", "8004091157220950016",
     "Clear vendor VND-1001 for character grogu, territory Asia-Pacific, "
     "product category Vinyl Figures, volume 50000."),
    ("deal_price", "4405152104998502400",
     "Price check for grogu, Vinyl Figures, volume 50000, net unit price 12.5, "
     "royalty 0.12, advance 50000."),
]

# The fail-closed guard's text — if we see this, the MCP was NOT reachable.
GUARD = "could not be reached"


async def probe(name: str, engine: str, brief: str) -> bool:
    try:
        reply = await a2a_engine_send(BASE + engine, brief, timeout=250)
    except Exception as exc:
        print(f"  [{name:11}] FAIL  exception: {type(exc).__name__}", flush=True)
        return False
    if not reply:
        print(f"  [{name:11}] FAIL  (empty reply)", flush=True)
        return False
    if GUARD in reply:
        print(f"  [{name:11}] FAIL  guard tripped — MCP unreachable", flush=True)
        return False
    print(f"  [{name:11}] ok    {reply[:90].replace(chr(10), ' ')}", flush=True)
    return True


async def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    ok = total = 0
    for r in range(1, rounds + 1):
        print(f"── round {r}", flush=True)
        results = await asyncio.gather(*(probe(*a) for a in AGENTS))
        ok += sum(results)
        total += len(results)
    print(f"\nLAYER 1: {ok}/{total} passed", flush=True)
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    asyncio.run(main())

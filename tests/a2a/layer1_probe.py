"""Layer 1 probe: every MCP-using agent → its MCP server, run N rounds.

Pass/fail is deliberately NOT the agent's self-report: an agent whose toolset is
down will still emit a confident clean verdict. The caller checks CallToolRequest
in the MCP's Cloud Run log; this script only reports what each agent returned.

    .venv/bin/python tests/a2a/layer1_probe.py [rounds]
"""

import asyncio
import os
import sys

sys.path.insert(0, "packages/vibeflix-common")
from vibeflix_common.a2a_engine import a2a_engine_send  # noqa: E402

# Engine ids + the project number are READ FROM deploy/agent_identities.json — never
# hardcoded. They used to be literals from the original project, which meant this probe
# silently tested SOMEONE ELSE'S engines when run in a fresh project.
import json as _json
import pathlib as _pathlib

_REGION = os.environ.get("REGION", "us-central1")
_IDS_PATH = _pathlib.Path(__file__).resolve().parents[2] / "deploy" / "agent_identities.json"
if not _IDS_PATH.exists():
    raise SystemExit(
        f"✗ {_IDS_PATH} not found. Deploy the engines, then run:\n"
        f"    PROJECT=$PROJECT REGION=$REGION python deploy/collect_agent_identities.py")
_IDS = _json.loads(_IDS_PATH.read_text())

# The app is a plain SA (no client cert) → it must use the PLAIN aiplatform host.
BASE = f"https://{_REGION}-aiplatform.googleapis.com/v1beta1/"


def _engine(display_name: str) -> str:
    """`projects/<num>/locations/<region>/reasoningEngines/<id>` for one agent."""
    try:
        return _IDS[display_name]["engine"]
    except KeyError:
        raise SystemExit(f"✗ {display_name!r} missing from {_IDS_PATH.name} "
                         f"(have: {', '.join(sorted(_IDS))})")


AGENTS = [
    ("brand_style", _engine("vibeflix-brand-style"),
     "Run the brand compliance audit. image: "
     "gs://vibeflix-request-image/0aa7dd74-vendor_request_refine.png ; "
     "character: grogu ; medium: vinyl figures"),
    ("vendor_clr", _engine("vibeflix-vendor-clearance"),
     "Clear vendor VND-1001 for character grogu, territory Asia-Pacific, "
     "product category Vinyl Figures, volume 50000."),
    ("deal_price", _engine("vibeflix-deal-pricing"),
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

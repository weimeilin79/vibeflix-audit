"""Run a single domain agent in isolation against locally-running MCP servers.

Useful for iterating on one agent without bringing up the whole A2A mesh.
Start the MCP servers first (``./run_local.sh mcp``), then:

    python -m agents.test_agent brand_style
    python -m agents.test_agent vendor_clearance --market "North America"
    python -m agents.test_agent deal_pricing --volume 40000

It defaults the ``MCP_*_URL`` vars to the local servers, seeds the session state
the agents read (image_path / target_market / volume), runs the agent once via
an in-memory Runner, and prints the tool calls + the structured report.
Vertex AI auth comes from each agent's ``.env`` + your ADC.
"""

import argparse
import asyncio
import importlib
import json
import os

# Point the agents' remote-MCP toolsets at the locally-running servers unless
# the caller already configured them. Must happen before importing the agent.
os.environ.setdefault("MCP_VISION_UI_URL", "http://127.0.0.1:9001/mcp")
os.environ.setdefault("MCP_LICENSING_URL", "http://127.0.0.1:9002/mcp")
os.environ.setdefault("MCP_MARKET_URL", "http://127.0.0.1:9003/mcp")
os.environ.setdefault("MCP_BRAND_STYLE_URL", "http://127.0.0.1:9004/mcp")

from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

AGENTS = ("brand_style", "vendor_clearance", "deal_pricing")


async def run(agent_name: str, image: str, market: str, volume: int, image_uri: str) -> None:
    module = importlib.import_module(f"agents.{agent_name}.agent")
    agent = module.root_agent
    from vibeflix_common.image_input import content_with_image

    app = App(name=f"test_{agent_name}", root_agent=agent)
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(
        app_name=app.name,
        user_id="tester",
        # Mirror the orchestrator's ingest seeds (image_uri / character_id) so
        # agents that need them (e.g. brand_style) don't stop to ask.
        state={
            "image_path": image,
            "image_uri": image_uri,
            "target_market": market,
            "volume": volume,
            "character_id": "grogu",
        },
    )

    brief = f"Audit mockup at {image_uri} for the {market} market at a volume of {volume} units."
    print(f"\n=== {agent.name} | image_uri={image_uri} market={market} ===\n")

    # Pass the image by LINK (file_data URI) — not as blob bytes.
    async for event in runner.run_async(
        user_id="tester",
        session_id=session.id,
        new_message=content_with_image(brief, image_uri),
    ):
        for call in event.get_function_calls() or []:
            print(f"  → tool call: {call.name}({json.dumps(call.args or {})})")
        for resp in event.get_function_responses() or []:
            print(f"  ← tool result: {resp.name}")
        content = getattr(event, "content", None)
        if content and getattr(content, "parts", None):
            text = "".join(getattr(p, "text", "") or "" for p in content.parts)
            if text.strip():
                print("  model:", text.strip())

    # Agents with an output_schema store their structured report under output_key.
    # Router/conversational agents (no output_key) return it as the final message
    # printed above, so there is nothing extra to fetch from state.
    if agent.output_key:
        final = await runner.session_service.get_session(
            app_name=app.name, user_id="tester", session_id=session.id
        )
        report = (final.state or {}).get(agent.output_key)
        print("\n--- structured report (state['%s']) ---" % agent.output_key)
        print(json.dumps(report, indent=2, default=str))


def main() -> None:
    p = argparse.ArgumentParser(description="Test one Vibeflix agent in isolation.")
    p.add_argument("agent", choices=AGENTS)
    p.add_argument("--image", default="grogu_mockup_box.png", help="image name (for state/labels)")
    p.add_argument("--image-uri", default=None,
                   help="image LINK passed to the agent (gs://… loads on Vertex; "
                        "default derives a gs:// URI from --image)")
    p.add_argument("--market", default="North America")
    p.add_argument("--volume", type=int, default=15000)
    args = p.parse_args()
    # No fake default: without a real --image-uri there is no image, and
    # brand_style must ask for one rather than run on a non-existent link.
    asyncio.run(run(args.agent, args.image, args.market, args.volume, args.image_uri or ""))


if __name__ == "__main__":
    main()

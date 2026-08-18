"""Ask a DEPLOYED agent one question and print its reply.

    PROJECT=… REGION=… python deploy/ask_agent.py brand-style "Audit gs://…/mock.png for grogu"

Why this exists rather than `agents-cli run --url … --mode adk|a2a`:

Our engines are deployed with the **A2A template** (deploy_agents_a2a.py → A2aAgent), which
serves the A2A protocol at

    <base>/a2a/v1/message:send      <base>/a2a/v1/tasks/{id}      <base>/a2a/v1/card
    base = https://<region>-aiplatform.googleapis.com/v1beta1/<engine resource>

agents-cli assumes engines deployed the ADK way, and addresses them at
`…/reasoningEngines/v1/<resource>/api/a2a/<agent-dir>/…` (a2a mode) or `:streamQuery`
(adk mode). Neither route exists on our engines — both return 404 — and no combination of
`--mode` / `--app-name` reaches the paths above, so the CLI cannot talk to them at all.

Rather than shell out to a client that speaks a different dialect, this uses the mesh's own
A2A client, `vibeflix_common.a2a.engine.a2a_engine_send` — the same code path the agents use
to call each other. It handles the auth headers, sends non-blocking, and polls the task to
completion (A2A is send-then-poll, so a raw curl would be two calls and a task-id dance).
"""

import asyncio
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENTS = ["brand-style", "deal-pricing", "legal", "vendor-clearance", "ui-renderer", "orchestrator"]


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(f"usage: python deploy/ask_agent.py <agent> \"<message>\"\n"
                 f"  agent: {' | '.join(AGENTS)}")
    agent, message = sys.argv[1], " ".join(sys.argv[2:])

    region = os.environ.get("REGION", "us-central1")
    if not (os.environ.get("PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")):
        sys.exit("✗ PROJECT is not set — run `source ./env.sh` first.")

    ids_path = ROOT / "deploy" / "agent_identities.json"
    if not ids_path.exists():
        sys.exit(f"✗ {ids_path} not found — deploy the agent, then run:\n"
                 f"    python deploy/collect_agent_identities.py")

    ids = json.loads(ids_path.read_text())
    key = f"vibeflix-{agent}"
    engine = (ids.get(key) or {}).get("engine")
    if not engine:
        known = ", ".join(sorted(k.removeprefix("vibeflix-") for k in ids)) or "(none)"
        sys.exit(f"✗ no engine for '{agent}' in agent_identities.json.\n"
                 f"  Deployed agents: {known}\n"
                 f"  If you just deployed it: python deploy/collect_agent_identities.py")

    # The A2A base documented in vibeflix_common/a2a/engine.py — plain aiplatform host, v1beta1.
    base = f"https://{region}-aiplatform.googleapis.com/v1beta1/{engine}"
    print(f"→ {key}  (…/{engine.rsplit('/', 1)[-1]})\n")

    from vibeflix_common.a2a.engine import a2a_engine_send

    reply = asyncio.run(a2a_engine_send(base, message, timeout=900.0))

    # Agents reply with a JSON report; pretty-print it when it is one, else print as-is.
    try:
        print(json.dumps(json.loads(reply), indent=2))
    except (ValueError, TypeError):
        print(reply)


if __name__ == "__main__":
    main()

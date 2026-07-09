"""Deploy the vibeflix agents to Agent Runtime as REAL platform-A2A agents.

WHY THIS EXISTS: `adk deploy agent_engine` builds a container that only serves
the session/query engine contract — the platform's `/a2a/v1/*` surface routes
into it and 404s ("does not have A2A methods defined" → after spec patches →
"Not Found"). Platform A2A requires the SDK's **A2aAgent template**, which this
script uses: each ADK root_agent is wrapped in ADK's A2aAgentExecutor and the
vertexai A2aAgent (agent card + request handlers), then deployed source-based.
The engine then genuinely serves:

    GET  …/v1beta1/<engine>/a2a/v1/card          (agent card)
    POST …/v1beta1/<engine>/a2a/v1/…             (message/send etc.)

Also sets service_account + AGENT_IDENTITY at create time (both are valid
AgentEngineConfig keys) — no post-deploy patching.

Usage (config from deploy/.env; MCP_*_URL + RAG_CORPUS must be exported/present):
    python deploy/deploy_agents_a2a.py               # all (vendor_clearance last)
    python deploy/deploy_agents_a2a.py brand_style   # one

NOTE: first-run territory (v1beta1 + preview surfaces) — expect to iterate.
Engines deployed by the old CLI path under the same display names are NOT
updated in place; this creates fresh engines. Delete the old ones afterwards.
"""

import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

_ENV = {**dotenv_values(ROOT / "deploy" / ".env"), **os.environ}
PROJECT = _ENV.get("PROJECT") or _ENV.get("GOOGLE_CLOUD_PROJECT")
REGION = _ENV.get("REGION", "us-central1")
ONLY = sys.argv[1] if len(sys.argv) > 1 else None
assert PROJECT, "set PROJECT in deploy/.env"

STAGING = f"gs://{PROJECT}-vibeflix-agent-staging"

# Env shipped to every engine. No custom Dockerfile here, so we control
# GOOGLE_CLOUD_LOCATION ourselves → Gemini keeps `global` like local.
COMMON_ENV = {
    "RUN_LOCAL": "false",
    "GOOGLE_GENAI_USE_VERTEXAI": "true",
    "GOOGLE_CLOUD_LOCATION": "global",
    "PUBSUB_TOPIC": _ENV.get("PUBSUB_TOPIC", "vibeflix-mesh-events"),
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "true",
}

AGENTS = {
    "brand_style": {"env": ["MCP_BRAND_STYLE_URL"],
                    "desc": "Brand style compliance — vision + deterministic brand checks."},
    "deal_pricing": {"env": ["MCP_LICENSING_URL"],
                     "desc": "Deal pricing — reconciles agreed consideration vs rate card."},
    "ui_renderer": {"env": [],
                    "desc": "A2UI presenter — renders reports and designs input forms."},
    "legal": {"env": ["MCP_LICENSING_URL", "RAG_CORPUS", "RAG_LOCATION"],
              "desc": "Legal clearance — RAG-discovers the process, executes contracts."},
    "vendor_clearance": {"env": ["MCP_LICENSING_URL", "MCP_MARKET_URL", "LEGAL_A2A_URL"],
                         "desc": "Vendor & licensing clearance — exclusivity, trademarks, vendors."},
}


def make_runner_builder(agent_name: str):
    """Returns a cloudpickle-able zero-arg Runner factory (imports at call time,
    inside the engine, where extra_packages puts `agents/` on the path)."""
    def build_runner():
        import importlib
        from google.adk.apps import App
        from google.adk.runners import InMemoryRunner
        mod = importlib.import_module(f"agents.{agent_name}.agent")
        return InMemoryRunner(app=App(name=agent_name, root_agent=mod.root_agent))
    return build_runner


def make_executor_builder(agent_name: str):
    def build_executor():
        from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
        return A2aAgentExecutor(runner=make_runner_builder(agent_name))
    return build_executor


def agent_card(name: str, desc: str):
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill
    return AgentCard(
        name=f"vibeflix-{name.replace('_', '-')}",
        description=desc,
        # The platform serves the card from the engine's /a2a/v1/card; the url
        # here is informational until the engine id exists.
        url=f"https://{REGION}-aiplatform.googleapis.com/v1beta1/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        preferred_transport="HTTP+JSON",
        skills=[AgentSkill(id=name, name=name.replace("_", " "),
                           description=desc, tags=["vibeflix"])],
    )


def requirements(name: str) -> list[str]:
    """The agent's requirements minus the Dockerfile-specific vendored path —
    the SDK tarball carries packages/vibeflix-common via extra_packages, and
    pip resolves it relative to the tarball root."""
    lines = []
    for line in (ROOT / "agents" / name / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("/app/"):
            continue
        lines.append(line)
    lines.append("packages/vibeflix-common")
    return lines


def main():
    import vertexai
    from vertexai import types

    client = vertexai.Client(project=PROJECT, location=REGION,
                             http_options=dict(api_version="v1beta1"))
    from vertexai.agent_engines.templates.a2a import A2aAgent

    existing = {(e.api_resource.display_name or ""): e.api_resource.name
                for e in client.agent_engines.list()}

    for name, spec in AGENTS.items():
        if ONLY and name != ONLY:
            continue
        missing = [k for k in spec["env"] if not _ENV.get(k)]
        if missing:
            print(f"── skipping {name}: export {', '.join(missing)} first")
            continue
        display = f"vibeflix-{name.replace('_', '-')}-a2a"
        env = {**COMMON_ENV, **{k: _ENV[k] for k in spec["env"]}}
        app = A2aAgent(agent_card=agent_card(name, spec["desc"]),
                       agent_executor_builder=make_executor_builder(name))
        config = {
            "display_name": display,
            "description": spec["desc"],
            "service_account": f"vibeflix-agents@{PROJECT}.iam.gserviceaccount.com",
            "identity_type": types.IdentityType.AGENT_IDENTITY,
            "staging_bucket": STAGING,
            "env_vars": env,
            "requirements": requirements(name),
            "extra_packages": ["agents", "packages/vibeflix-common"],
        }
        if display in existing:
            print(f"── updating {display} ({existing[display]})…")
            engine = client.agent_engines.update(name=existing[display], agent=app, config=config)
        else:
            print(f"── creating {display}…")
            engine = client.agent_engines.create(agent=app, config=config)
        res = engine.api_resource
        print(f"   engine:    {res.name}")
        print(f"   card:      https://{REGION}-aiplatform.googleapis.com/v1beta1/{res.name}/a2a/v1/card")
        ident = getattr(getattr(res, "spec", None), "effective_identity", None)
        print(f"   identity:  {ident}")


if __name__ == "__main__":
    main()

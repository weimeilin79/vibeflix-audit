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
Create-or-update by display name (vibeflix-<name>); deploy ONE agent at a
time in dependency order: brand_style, deal_pricing, ui_renderer, legal,
then vendor_clearance (needs LEGAL_A2A_URL), then orchestrator (needs the 3
domain engines' A2A URLs).
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

def get_run_url(service_name: str) -> str:
    import subprocess
    cmd = ["gcloud", "run", "services", "describe", service_name,
           "--platform", "managed", "--region", REGION, "--project", PROJECT,
           "--format", "value(status.url)"]
    try:
        url = subprocess.check_output(cmd).decode().strip()
        return f"{url}/mcp" if url else ""
    except Exception as e:
        print(f"Error getting URL for {service_name}: {e}")
        return ""

import json
identities_path = ROOT / "deploy" / "agent_identities.json"
if identities_path.exists():
    identities = json.loads(identities_path.read_text())
    
    _ENV.setdefault("MCP_BRAND_STYLE_URL", get_run_url("vibeflix-mcp-brand-style"))
    _ENV.setdefault("MCP_LICENSING_URL", get_run_url("vibeflix-mcp-licensing"))
    _ENV.setdefault("MCP_MARKET_URL", get_run_url("vibeflix-mcp-market"))

    # Where the engines keep their A2A tasks (the app, not this replica's memory).
    # get_run_url() appends /mcp for the MCP servers — strip it; we want the app root.
    _ENV.setdefault("TASK_STORE_URL",
                    get_run_url("vibeflix-app").removesuffix("/mcp"))

    # A2A hops use the MTLS aiplatform endpoint — the URL the agent endpoints are
    # REGISTERED with in the Agent Registry. The gateway only authorizes the destination
    # it has registered:
    #   plain URL → 403 `Egress request is not authorized`, even after adding that URL as
    #               an interface on the endpoint AND granting the caller iap.egressor on
    #               it (measured repeatedly — this is NOT a propagation delay).
    #   mtls URL  → gateway allows it through.
    # On the mtls host, Google's endpoint additionally requires the workload's CLIENT
    # CERTIFICATE (available in Agent Runtime — verified) and an `Authorization` header;
    # a2a_engine.py now sends Authorization (for the target) + Proxy-Authorization (for
    # the gateway) + the client cert.
    _A2A = f"https://{REGION}-aiplatform.mtls.googleapis.com/v1beta1"
    _ENV.setdefault("LEGAL_A2A_URL", f"{_A2A}/{identities['vibeflix-legal']['engine']}")
    _ENV.setdefault("BRAND_STYLE_A2A_URL", f"{_A2A}/{identities['vibeflix-brand-style']['engine']}")
    _ENV.setdefault("VENDOR_CLEARANCE_A2A_URL", f"{_A2A}/{identities['vibeflix-vendor-clearance']['engine']}")
    _ENV.setdefault("DEAL_PRICING_A2A_URL", f"{_A2A}/{identities['vibeflix-deal-pricing']['engine']}")

STAGING = f"gs://{PROJECT}-vibeflix-agent-staging"

# Env shipped to every engine.
# WEB_CONCURRENCY=1 forces the engine to run with a single worker process,
# preventing process-isolated task stores from returning 404 on polling.
COMMON_ENV = {
    "RUN_LOCAL": "false",
    "GOOGLE_GENAI_USE_VERTEXAI": "true",
    # KEEP THIS "global" — and register the GLOBAL aiplatform hosts in the Agent Registry.
    #
    # The genai client + VertexAiSessionService egress to a host derived from this value:
    #   global       → https://aiplatform.googleapis.com            (gcp-aiplatform-global)
    #   us-central1  → https://us-central1-aiplatform.googleapis.com (gcp-aiplatform)
    # The gateway is default-deny, so whichever host is used MUST be a registered Service
    # in the Agent Registry with roles/iap.egressor granted to the agent principal.
    #
    # Measured: with location=global + the global hosts registered/granted, the fleet ran
    # clean (layer 1 fully green, zero 401s). Pinning to the REGION — even with the regional
    # hosts registered AND granted, and every other registered endpoint granted too — still
    # 403'd on every engine. So the regional path is NOT a working substitute here; the
    # global host is what Agent Runtime actually egresses to. Do not "helpfully" pin this
    # to the region.
    "GOOGLE_CLOUD_LOCATION": "global",
    "PUBSUB_TOPIC": _ENV.get("PUBSUB_TOPIC", "vibeflix-mesh-events"),
    "GOOGLE_API_USE_CLIENT_CERTIFICATE": "false",
    "GOOGLE_API_USE_MTLS_ENDPOINT": "never",
    "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
    # An AGENT_IDENTITY engine has NO service account behind the metadata server,
    # so fetch_id_token() can't work — yet the Cloud Run MCPs require an
    # audience-bound OIDC ID token. The engine impersonates this SA to mint one
    # (cloud_auth._id_token_via_impersonation). Same mechanism as the Agent Gateway
    # codelab's --mcp-invoker-sa. Needs: agent principal -> tokenCreator on this SA,
    # plus iap.egressor on the gcp-iamcredentials registry endpoints (gateway is
    # default-deny, so even the token-minting call must be allowlisted).
    "MCP_INVOKER_SA": _ENV.get(
        "MCP_INVOKER_SA", f"vibeflix-mcp-invoker@{PROJECT}.iam.gserviceaccount.com"),
    # The shared A2A task store (the app). Reached exactly like an MCP server: registered
    # in the Agent Registry + iap.egressor, with an ID token minted via MCP_INVOKER_SA.
    # TASK_STORE_KEY gates those endpoints — the app is PUBLIC (the browser must load the
    # console), so without the shared secret the task state would be world-writable.
    "TASK_STORE_URL": _ENV.get("TASK_STORE_URL", ""),
    "TASK_STORE_KEY": _ENV.get("TASK_STORE_KEY", ""),
    # Propagate W3C traceparent across every A2A hop, so Cloud Trace stitches the mesh into
    # ONE trace and the console's Agent Platform → Topology page can draw the edges.
    #
    # A previous attempt collapsed the callee's traces (68 spans → 2-span fragments) and was
    # reverted. ROOT CAUSE (found by testing orchestrator→brand_style in isolation): a bare
    # inject() propagates whatever context is current — INCLUDING AN UNSAMPLED ONE
    # (flags=00) — and the callee honours that flag and drops nearly all of its own spans.
    # a2a_engine only injects a context that is BOTH valid AND sampled; otherwise it sends
    # nothing and the callee starts its own fully-sampled trace.
    # MEASURED with the guard: one trace, 63 spans across 5 services, 56 agent spans —
    # RICHER than the 32-agent-span best case before. Nothing collapsed.
    "A2A_TRACE_PROPAGATION": _ENV.get("A2A_TRACE_PROPAGATION", "on"),
    "WEB_CONCURRENCY": "1",
    # Engine OTLP telemetry → Cloud Trace + the console's Observability panel.
    #
    # ⚠️ ON BY DEFAULT, AND IT MUST STAY THAT WAY. The traces ARE the demo: every agent has
    # to be traced, always. This used to be OPT-IN (`TELEMETRY=on`, defaulting to false), and
    # that default is a trap — a redeploy that merely FORGETS the flag turns tracing off
    # across the whole fleet, reports success, and exits 0. That happened: all six engines
    # came back with telemetry=false and every trace vanished, silently. Now you have to ask
    # for the broken state explicitly (`TELEMETRY=off`), and the safe state is the default.
    #
    # (Historic reason it was opt-in: the OTLP *HTTP* exporter crashes on the py3.14 base —
    # pyOpenSSL "Context has already been used" — and 403s through the gateway. That is why
    # this block ALSO forces the gRPC exporter, which is the working path.)
    #
    # STILL VERIFY AFTER EVERY DEPLOY — do not trust the exit code. Read the flag back:
    #   GET …/reasoningEngines/<id> → spec.deploymentSpec.env[] →
    #   GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY == "true"   (for all six)
    **({
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "true",
        # THE switch the console actually reads. Deployed engines default to NO_CONTENT
        # (metadata only: model, tokens, timing) — which is why the trace view says
        # "Prompt-response content collection is not enabled". `true` = capture the full
        # prompt + response text in the spans.
        # ⚠️ This LOGS PROMPTS AND MODEL OUTPUT. Fine for the demo; for a real tenant with
        # customer data, use NO_CONTENT (or `false`) and keep content out of telemetry.
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
        # SILENCE THE A2A SDK's OWN SPANS — they drowned the trace.
        # a2a decorates EventQueue with @trace_class, so EVERY method call gets a span,
        # and EventConsumer.consume_all() polls dequeue_event() on a 0.5s timeout for as
        # long as a task runs. Result: one span per half-second of waiting, per in-flight
        # task. Measured on one fleet-wide sample: dequeue_event = 3,228 spans (44.5%) and
        # on_get_task = 2,246 (31%) — ~75% of ALL spans were A2A plumbing waiting on
        # itself, and the agent spans were invisible underneath. (The 404-heavy on_get_task
        # spans also accounted for the ~1,890 "errors" = 26% of spans.)
        # This kill switch is the SDK's own (a2a/utils/telemetry.py: ENABLED_ENV_VAR) and
        # swaps its tracer for a no-op. It does NOT affect the spans we actually want —
        # invocation / invoke_workflow / invoke_agent / call_llm / execute_tool all come
        # from ADK's instrumentation, not A2A's.
        # The A2A SDK's OWN spans (a2a.server.request_handlers.*, EventQueue.*).
        #
        # These are the ONLY spans that identify an A2A hop — nothing else in the trace says
        # "orchestrator called brand_style" (our client uses `requests`, which is
        # uninstrumented, so there is no client span). With them off, the console's
        # Agent Platform → Topology queries — "agents sending traffic to X", "agents
        # receiving traffic from X", "MCP servers exchanging traffic with X" — all come back
        # EMPTY, even though the trace is correctly linked end-to-end.
        #
        # They were turned OFF because they swamped the trace (dequeue_event = 44.5% of all
        # spans). But that flood was mostly a SYMPTOM of two bugs now fixed: EventConsumer
        # emits one span per 0.5s of WAITING, and on_get_task emitted one per poll — so the
        # 5-minute runs and the 86.8% 404 storm were what made it enormous. With runs at
        # ~1m44s and 0% misses, the span count falls with them.
        # Flip back with A2A_SDK_SPANS=off in deploy/.env if it is still too noisy.
        "OTEL_INSTRUMENTATION_A2A_SDK_ENABLED":
            "false" if _ENV.get("A2A_SDK_SPANS", "on").lower() == "off" else "true",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "grpc",
    # DEFAULT ON. Only an explicit TELEMETRY=off disables it — forgetting the flag can no
    # longer silently untrace the fleet.
    } if _ENV.get("TELEMETRY", "on").lower() != "off" else {
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "false",
    }),
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
    # LAST: needs the three domain engines' A2A URLs.
    "orchestrator": {"env": ["MCP_LICENSING_URL", "BRAND_STYLE_A2A_URL",
                             "VENDOR_CLEARANCE_A2A_URL", "DEAL_PRICING_A2A_URL"],
                     "desc": "Sourcing orchestrator — dispatches the compliance workflows and finalizes contracts."},
}


def make_runner_builder(agent_name: str):
    """Returns a cloudpickle-able zero-arg Runner factory (imports at call time,
    inside the engine, where extra_packages puts `agents/` on the path)."""
    region = REGION      # baked into the pickled closure
    project = PROJECT

    def build_runner():
        import importlib
        import os
        from google.adk.apps import App
        # The agent name comes from THIS engine's own env (VIBEFLIX_AGENT_NAME,
        # set per-engine in config["env_vars"]). Do NOT trust the pickled closure
        # `agent_name`: cloudpickle serialized every engine's executor with the
        # last loop value ("orchestrator"), so all engines imported the wrong
        # module and failed. Reading from env at runtime is immune to that.
        name = os.environ.get("VIBEFLIX_AGENT_NAME") or agent_name
        mod = importlib.import_module(f"agents.{name}.agent")
        app = App(name=name, root_agent=mod.root_agent)
        # ENGINE-LEVEL MEMORY: Agent Runtime sets GOOGLE_CLOUD_AGENT_ENGINE_ID
        # inside every engine — present in the cloud, absent everywhere else, so
        # local runs are untouched by construction. Sessions + Memory Bank are
        # backed by THIS engine itself (regional, not the Gemini `global`).
        eid = os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID", "").rsplit("/", 1)[-1]
        if eid:
            from google.adk.runners import Runner
            from google.adk.sessions import VertexAiSessionService
            from google.adk.memory import VertexAiMemoryBankService
            return Runner(
                app=app,
                session_service=VertexAiSessionService(
                    project=project, location=region, agent_engine_id=eid),
                memory_service=VertexAiMemoryBankService(
                    project=project, location=region, agent_engine_id=eid),
            )
        from google.adk.runners import InMemoryRunner
        return InMemoryRunner(app=app)
    return build_runner


def make_executor_builder(agent_name: str):
    def build_executor():
        from vibeflix_common.a2a_compat import ensure
        ensure()  # engine-side: template imports need the shim too
        from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
        return A2aAgentExecutor(runner=make_runner_builder(agent_name))
    return build_executor


def make_task_store_builder():
    """The engine's A2A tasks live in the APP, not in this replica's memory."""
    def build_task_store():
        from vibeflix_common.task_store import RemoteTaskStore
        return RemoteTaskStore()   # reads TASK_STORE_URL (in COMMON_ENV)
    return build_task_store


def agent_card(name: str, desc: str):
    """a2a-sdk 0.3.x AgentCard — the model vertexai.preview's A2aAgent expects
    (recipe verified from the agents-cli adk_a2a scaffold)."""
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill
    return AgentCard(
        name=f"vibeflix-{name.replace('_', '-')}",
        description=desc,
        url=f"https://{REGION}-aiplatform.googleapis.com/v1beta1/",  # informational
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
    # SDK-required (deploy warns if absent) + our pinned working pair:
    lines += ["a2a-sdk==0.3.26", "cloudpickle==3.1.2",
              "google-cloud-aiplatform[agent_engines]>=1.130.0"]
    return lines


def _check_sdk_compat():
    """This script requires a2a-sdk>=1.0 (the vertexai A2aAgent template's
    models) — but google-adk 2.3 requires a2a-sdk<1. The two cannot coexist:
    resolving this needs a NEWER google-adk built against a2a-sdk 1.x
    (see README: 'Three ways to deploy…' + the agents-cli probe plan)."""
    import importlib.metadata as md
    v = md.version("a2a-sdk")
    if v.startswith("0."):
        raise SystemExit(
            f"a2a-sdk {v} is too old for the A2aAgent template (needs >=1.0).\n"
            "Known deadlock: upgrading breaks google-adk 2.3. Next step is the\n"
            "agents-cli lockfile probe / google-adk upgrade — do NOT pip-juggle."
        )


import threading
_VENDORED_LOCK = threading.Lock()

def _vendored_common() -> str:
    """extra_packages resolves RELATIVE root-level dirs (the scaffold's proven
    pattern: extra_packages=["app"]). Copy vibeflix_common to the repo root for
    the duration of the deploy; cleaned up in main()'s finally.

    ALWAYS re-copy. This used to be `if not os.path.exists(dst)` with a no-op
    cleanup, which meant the root copy was a fossil from the FIRST deploy: every
    later deploy shipped that stale snapshot and silently ignored edits to
    packages/vibeflix-common. That cost us hours — the engines ran a cloud_auth.py
    old enough to predate agent-identity ID-token minting, so every MCP call 401'd
    while the fix sat on disk, deployed-but-not-really.
    """
    import shutil
    with _VENDORED_LOCK:
        dst = ROOT / "vibeflix_common"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(ROOT / "packages" / "vibeflix-common" / "vibeflix_common", dst,
                        ignore=shutil.ignore_patterns("__pycache__"))
    return "vibeflix_common"


def _cleanup_vendored():
    """Deliberately a NO-OP — do NOT rmtree the root copy here.

    Staleness is already prevented by _vendored_common() re-copying on EVERY deploy.
    Deleting on exit adds nothing and creates a footgun: `_VENDORED_LOCK` is a
    threading lock, so it does not guard separate PROCESSES. Running two deploys
    concurrently (`deploy_agents_a2a.py a & deploy_agents_a2a.py b &`) had one
    process rmtree the shared root copy while the other was mid-copytree:

        shutil.Error: [Errno 2] No such file or directory: .../vibeflix_common/a2a_compat.py
        FileNotFoundError: Package specified but not found: package='vibeflix_common'

    …and the deploy silently failed, leaving the engine on its OLD env/code.
    ⚠️ Deploy agents SERIALLY, or in one process (`deploy_agents_a2a.py` with no args,
    which is the normal path and is safe).
    """
    pass


def main():
    os.chdir(ROOT)   # extra_packages/"agents" are root-relative
    import vertexai
    from vertexai import types

    client = vertexai.Client(project=PROJECT, location=REGION,
                             http_options=dict(api_version="v1beta1"))
    from vertexai.preview.reasoning_engines import A2aAgent  # 0.3.x-compatible (per agents-cli scaffold)

    existing = {(e.api_resource.display_name or ""): e.api_resource.name
                for e in client.agent_engines.list()}

    from concurrent.futures import ThreadPoolExecutor

    def deploy_one(name, spec):
        missing = [k for k in spec["env"] if not _ENV.get(k)]
        if missing:
            print(f"── skipping {name}: export {', '.join(missing)} first")
            return
        display = f"vibeflix-{name.replace('_', '-')}"
        # VIBEFLIX_AGENT_NAME: the runtime authority for which agent module this
        # engine loads (see build_runner) — the pickled closure is unreliable.
        env = {**COMMON_ENV, "VIBEFLIX_AGENT_NAME": name,
               **{k: _ENV[k] for k in spec["env"]}}
        # task_store_builder: WITHOUT it the A2aAgent template falls back to
        # InMemoryTaskStore — a dict private to each replica — and `GET /a2a/v1/tasks/{id}`
        # 404s whenever the load balancer picks a replica other than the one that created
        # the task (measured: 86.8% of polls). See vibeflix_common/task_store.py.
        app = A2aAgent(agent_card=agent_card(name, spec["desc"]),
                       agent_executor_builder=make_executor_builder(name),
                       task_store_builder=make_task_store_builder())
        config = {
            "display_name": display,
            "description": spec["desc"],
            # NOTE: service_account may NOT be set with AGENT_IDENTITY —
            # the agent identity IS the workload identity (verified: 400 otherwise).
            "identity_type": types.IdentityType.AGENT_IDENTITY,
            "staging_bucket": STAGING,
            "env_vars": env,
            "requirements": requirements(name),
            "extra_packages": ["agents", _vendored_common()],
            "agent_gateway_config": {
                "agent_to_anywhere_config": {
                    "agent_gateway": f"projects/{PROJECT}/locations/{REGION}/agentGateways/vibeflix-gateway"
                }
            },
        }
        if display in existing:
            print(f"── updating {display} ({existing[display]})…")
            engine = client.agent_engines.update(name=existing[display], agent=app, config=config)
        else:
            print(f"── creating {display}…")
            engine = client.agent_engines.create(agent=app, config=config)
        res = engine.api_resource
        ident = getattr(getattr(res, "spec", None), "effective_identity", None)
        print(f"   engine {display}: {res.name}\n   card {display}: https://{REGION}-aiplatform.googleapis.com/v1beta1/{res.name}/a2a/v1/card\n   identity {display}: {ident}")

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = []
        for name, spec in AGENTS.items():
            if ONLY and name != ONLY:
                continue
            futures.append(executor.submit(deploy_one, name, spec))
        for f in futures:
            f.result()


if __name__ == "__main__":
    try:
        main()
    finally:
        _cleanup_vendored()

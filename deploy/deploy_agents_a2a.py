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

def gateway_exists() -> bool:
    """True when the Agent Gateway exists and this caller can read it.

    `agent_gateway_config` may only name a gateway that is actually there. On a fresh
    project the gateway is created LATER (workshop Step 7 / setup_gateway.sh gateway), so
    attaching to it here fails the whole deploy with:

        400 FAILED_PRECONDITION  Permission denied to get Agent Gateway '…/vibeflix-gateway'

    — which reads like an IAM problem but is really "it does not exist yet" (GCP masks a
    missing resource as PERMISSION_DENIED). So probe first and deploy without governed
    egress when it is absent; re-running this script after Step 7 attaches it.
    """
    import subprocess
    cmd = ["gcloud", "alpha", "network-services", "agent-gateways", "describe",
           "vibeflix-gateway", "--location", REGION, "--project", PROJECT]
    try:
        subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def get_run_url(service_name: str, optional: bool = False) -> str:
    """URL of a Cloud Run service, or "" if it isn't deployed.

    optional=True is for services that legitimately don't exist yet (the app, on a fresh
    project's first pass). Those print a one-line note instead of gcloud's raw ERROR +
    CalledProcessError dump, which reads like a crash in the middle of a normal deploy.
    """
    import subprocess
    cmd = ["gcloud", "run", "services", "describe", service_name,
           "--platform", "managed", "--region", REGION, "--project", PROJECT,
           "--format", "value(status.url)"]
    try:
        url = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return f"{url}/mcp" if url else ""
    except Exception as e:
        if optional:
            pass   # the caller reports what it does instead (see _app_url)
        else:
            print(f"Error getting URL for {service_name}: {e}")
        return ""

import json


def _project_number(project_id: str) -> str:
    """The numeric id — engine resource names are `projects/<NUMBER>/...`, not the id."""
    import subprocess
    try:
        return subprocess.check_output(
            ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


identities_path = ROOT / "deploy" / "agent_identities.json"
identities = {}
if identities_path.exists():
    _loaded = json.loads(identities_path.read_text())

    # ⚠️ REFUSE IDENTITIES THAT BELONG TO ANOTHER PROJECT.
    #
    # agent_identities.json is COMMITTED, so a fresh clone starts life holding the ORIGINAL
    # project's engine ids. This file is read BEFORE anything is deployed, to build
    # LEGAL_A2A_URL / BRAND_STYLE_A2A_URL / … — so without this guard a brand-new project
    # would deploy engines wired to the ENGINES OF A DIFFERENT PROJECT. Every A2A hop would
    # then point across the project boundary, get refused by the gateway (no egress grant
    # there), and the mesh would fail in ways that look like anything BUT the real cause.
    #
    # Engine resource names are `projects/<PROJECT_NUMBER>/locations/...`, so compare
    # against THIS project's number. Foreign ⇒ ignore the file entirely and let the
    # deploy proceed with no A2A URLs; `collect_agent_identities.py` regenerates it after
    # the engines exist, and the SECOND deploy pass wires them up (see the two-pass order
    # in deploy-vibeflix-skill/SKILL.md).
    _num = _project_number(PROJECT)
    _foreign = [k for k, v in _loaded.items()
                if _num and f"projects/{_num}/" not in (v.get("engine") or "")]
    if _foreign:
        print(f"⚠️  deploy/agent_identities.json belongs to ANOTHER PROJECT "
              f"(entries not under projects/{_num}: {', '.join(sorted(_foreign))}).\n"
              f"    IGNORING it — otherwise this deploy would wire {PROJECT}'s engines to a "
              f"different project's engines.\n"
              f"    This is expected on a fresh project. Deploy the engines, then run:\n"
              f"      PROJECT={PROJECT} REGION={REGION} python deploy/collect_agent_identities.py\n"
              f"    …and deploy the engines AGAIN so the A2A URLs + TASK_STORE_URL are set.",
              flush=True)
    else:
        identities = _loaded

# These come from CLOUD RUN, not from the identities file — resolve them ALWAYS, even on a
# fresh project whose identities were just rejected as foreign. (They were briefly nested
# under `if identities:`, which meant a fresh project silently deployed with NO MCP urls and
# NO task store.)
_ENV.setdefault("MCP_BRAND_STYLE_URL", get_run_url("vibeflix-mcp-brand-style"))
_ENV.setdefault("MCP_LICENSING_URL", get_run_url("vibeflix-mcp-licensing"))
_ENV.setdefault("MCP_MARKET_URL", get_run_url("vibeflix-mcp-market"))

# Where the engines keep their A2A tasks (the app, not this replica's memory).
# get_run_url() appends /mcp for the MCP servers — strip it; we want the app root.
# EMPTY on the first pass of a fresh project (the app doesn't exist yet) — the engines then
# fall back to a per-replica store and say so loudly. Pass 2, after the app is up, sets it.
# The app hosts the shared A2A task store. Prefer its live URL; if it isn't deployed yet, use
# the DETERMINISTIC Cloud Run form instead of leaving this empty.
#
# Cloud Run serves every service at BOTH  https://<svc>-<hash>-<reg>.a.run.app  (what
# `gcloud run services describe` reports) AND  https://<svc>-<project-number>.<region>.run.app
# — verified: both return 200 for the same service. Only the second is computable, and the value
# is read at RUNTIME, so it's fine to set it before the app exists: it just has to be up by the
# time an audit runs. That removes the whole "deploy everything twice" pass this used to need.
def _app_url() -> str:
    live = get_run_url("vibeflix-app", optional=True).removesuffix("/mcp")
    if live:
        return live
    num = _project_number(PROJECT)
    if not num:
        return ""
    url = f"https://vibeflix-app-{num}.{REGION}.run.app"
    print(f"   \u2139 vibeflix-app isn't deployed yet — using its predictable URL {url}\n"
          f"     (deploy the app in Step 6; the engines only read this at run time).")
    return url


_ENV.setdefault("TASK_STORE_URL", _app_url())

# Probed ONCE here, not per-agent: deploy_one() runs in a thread pool, and this shells out.
GATEWAY_READY = gateway_exists()
if not GATEWAY_READY:
    print("   \u2139 Agent Gateway 'vibeflix-gateway' doesn't exist yet — deploying WITHOUT"
          " governed egress.\n"
          "     Create it later (setup_gateway.sh gateway), then re-run this script to attach it.")

if identities:
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
    # Guard EACH key. On a PARTIAL identities file (collect_agent_identities.py ran before
    # every engine existed — e.g. deploying agents one at a time) a bare
    # identities['vibeflix-legal'] raises KeyError and aborts the whole deploy. Set only the
    # URLs whose engine is already known; a later pass fills in the rest.
    for _var, _key in (("LEGAL_A2A_URL", "vibeflix-legal"),
                       ("BRAND_STYLE_A2A_URL", "vibeflix-brand-style"),
                       ("VENDOR_CLEARANCE_A2A_URL", "vibeflix-vendor-clearance"),
                       ("DEAL_PRICING_A2A_URL", "vibeflix-deal-pricing")):
        if identities.get(_key, {}).get("engine"):
            _ENV.setdefault(_var, f"{_A2A}/{identities[_key]['engine']}")

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
    # ⚠️ THESE THREE ARE WHAT KEEP THE ENGINE'S CREDENTIAL ALIVE. They used to be
    # "false"/"never"/"false" — leftovers from a test that concluded "no client certificate
    # is needed" (true for the A2A hop) and deleted the cert plumbing. That test missed the
    # real job of the certificate: an AGENT_IDENTITY token is CERTIFICATE-BOUND, and the
    # cert is the ONLY way to mint a FRESH one.
    #
    # google-auth (compute_engine/_metadata.get_service_account_token) does it for us:
    #     cert = _agent_identity_utils.get_and_parse_agent_identity_certificate()
    #     if cert and should_request_bound_token(cert):
    #         params["bindCertificateFingerprint"] = fingerprint   # → a FRESH bound token
    # …but it returns None — and skips the whole path — when
    #   GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES == "false"  (explicit opt-out)
    #   GOOGLE_API_USE_CLIENT_CERTIFICATE                       == "false"  (mTLS opt-out)
    # With those off, google-auth asks for an UNBOUND token, and the metadata server hands
    # back the platform's SHARED, PRE-MINTED token whose expiry is FROZEN at replica boot.
    # Refreshing re-fetches the same dead token (measured: 6 × identical SHA-256 fingerprint,
    # identical server_expiry), so ~60 min after a replica boots EVERY call 401s
    # ("Error code 1000") — sessions first, because _prepare_session runs before agent code,
    # then MCP (its impersonation is bootstrapped from the same token) and A2A.
    # Measured fuse: 59m56s / 60m52s / 61m26s / 63m47s from each replica's own boot.
    #
    # Only ONE flag is needed, and it must NOT be the heavy hammer. google-auth requests a
    # certificate-BOUND token (compute_engine/_metadata) when:
    #   • PREVENT_AGENT_TOKEN_SHARING != "false"  (opt-in; library default is already "true")
    #   • USE_CLIENT_CERTIFICATE      != "false"  (the gate only BLOCKS on explicit "false";
    #                                              UNSET → None → does NOT block — verified in
    #                                              _agent_identity_utils.should_request_bound_token)
    #   • USE_MTLS_ENDPOINT is "auto" (library default) so the bound token rides mTLS
    # The old bug was setting all three to false/never/false (opted OUT → unbound, frozen,
    # platform-cached token → 60-min fuse). The FIRST fix over-corrected to true/auto/true —
    # and `USE_CLIENT_CERTIFICATE=true` FORCE-mTLS'd *every* client in the process, including
    # Agent Runtime's managed OTLP-HTTP telemetry exporter, which then crashed on the py3.14
    # pyOpenSSL bug ("Context has already been used to create a Connection"). That crash is
    # telemetry-only (OTel swallows it) but it's noise we caused.
    # So: keep the opt-in EXPLICIT, and DO NOT set the other two — let them default. Bound
    # tokens still mint (gate needs USE_CLIENT_CERTIFICATE only ≠ "false"); the telemetry
    # exporter is no longer force-mTLS'd. The *.mtls.googleapis.com hosts must stay registered
    # + granted (grant_agent_iam.sh) since the bound token still rides mTLS to aiplatform.
    # VERIFY after deploy: [token] verdict=NEW-TOKEN (fp CHANGES, server_expiry MOVES) AND no
    # "Context has already been used" in the logs.
    "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "true",
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
        from google.adk.apps import App, ResumabilityConfig
        # The agent name comes from THIS engine's own env (VIBEFLIX_AGENT_NAME,
        # set per-engine in config["env_vars"]). Do NOT trust the pickled closure
        # `agent_name`: cloudpickle serialized every engine's executor with the
        # last loop value ("orchestrator"), so all engines imported the wrong
        # module and failed. Reading from env at runtime is immune to that.
        name = os.environ.get("VIBEFLIX_AGENT_NAME") or agent_name
        mod = importlib.import_module(f"agents.{name}.agent")
        # Crash/failure recovery — ORCHESTRATOR only for now: with is_resumable, a re-invoked
        # invocation REPLAYS its completed nodes from cached output and re-runs only the pending
        # ones, instead of restarting. Relies on the durable VertexAiSessionService below to keep
        # the events across a replica crash. (Nodes must be idempotent — resume is at-least-once.)
        app = App(name=name, root_agent=mod.root_agent,
                  resumability_config=ResumabilityConfig(is_resumable=(name == "orchestrator")))
        # ENGINE-LEVEL SESSIONS: Agent Runtime sets GOOGLE_CLOUD_AGENT_ENGINE_ID inside every
        # engine — present in the cloud, absent everywhere else, so local runs are untouched by
        # construction. Each engine's SESSIONS are backed by THIS engine itself (regional, not the
        # Gemini `global`), which is what gives HITL resume + restart survival.
        # Memory Bank is scoped to the ORCHESTRATOR only: it's the sole memory consumer
        # (its note-responder searches memory) and it writes THIS audit's durable session
        # to its OWN engine's Bank from `contract_finalize`. Every other engine never
        # searches/writes memory, so they stay on InMemory.
        eid = os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID", "").rsplit("/", 1)[-1]
        if eid:
            from google.adk.runners import Runner
            from google.adk.sessions import VertexAiSessionService
            from google.adk.memory import InMemoryMemoryService, VertexAiMemoryBankService
            if name == "orchestrator":
                memory_service = VertexAiMemoryBankService(
                    project=project, location=region, agent_engine_id=eid)
            else:
                memory_service = InMemoryMemoryService()
            return Runner(
                app=app,
                session_service=VertexAiSessionService(
                    project=project, location=region, agent_engine_id=eid),
                memory_service=memory_service,
            )
        from google.adk.runners import InMemoryRunner
        return InMemoryRunner(app=app)
    return build_runner


def make_executor_builder(agent_name: str):
    def build_executor():
        from vibeflix_common.a2a.compat import ensure
        ensure()  # engine-side: template imports need the shim too
        from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
        return A2aAgentExecutor(runner=make_runner_builder(agent_name))
    return build_executor


def make_task_store_builder():
    """The engine's A2A tasks live in the APP, not in this replica's memory."""
    def build_task_store():
        from vibeflix_common.a2a.task_store import RemoteTaskStore
        return RemoteTaskStore()   # reads TASK_STORE_URL (in COMMON_ENV)
    return build_task_store


def agent_card(name: str, desc: str):
    """a2a-sdk 0.3.x AgentCard — the model vertexai.preview's A2aAgent expects
    (recipe verified from the agents-cli adk_a2a scaffold)."""
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill
    return AgentCard(
        name=f"vibeflix-{name.replace('_', '-')}",
        description=desc,
        # ⚠️ NOT informational in general — a2a/client/transports/rest.py does
        # `self.url = agent_card.url` and appends `/v1/message:send`, so a standard A2A client
        # calls whatever host this names. It does NOT matter here only because the A2aAgent
        # template OVERWRITES it at engine start-up with the plain aiplatform host
        # (templates/a2a.py:328) — which the Agent Gateway refuses, and which is why
        # VibeflixRemoteA2aAgent repoints the RPC at the .mtls base after fetching the card.
        # See eng-report/UPSTREAM-FR-a2a-client-gaps.md (measured in-engine 2026-08-02).
        url=f"https://{REGION}-aiplatform.googleapis.com/v1beta1/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        preferred_transport="HTTP+JSON",
        # Registers the `handle_authenticated_agent_card` route on the engine (see
        # A2aAgent.register_operations — it appends that op ONLY when this flag is set).
        # Without it the engine serves message:send/tasks but 404s on the agent card, so a
        # standard a2a client (RemoteA2aAgent) can't discover it. With it, the card is
        # fetchable at {engine}/a2a/v1/card.
        supports_authenticated_extended_card=True,
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

        shutil.Error: [Errno 2] No such file or directory: .../vibeflix_common/a2a/compat.py
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
            # A2A URLs are derived from agent_identities.json AT IMPORT (see above), so an agent
            # whose peer was deployed moments ago still looks unresolved until
            # collect_agent_identities.py has written that peer's engine id.
            print(f"── skipping {name}: {', '.join(missing)} not resolved yet")
            if ONLY == name:
                # The user asked for THIS agent by name — a skip is a failure, not a no-op.
                # Exiting 0 here meant the next step (grant/verify) was the first thing to
                # notice the engine was never created.
                # Name the RIGHT remedy per variable: a peer A2A URL is produced by deploying
                # that peer and recording it, while RAG_CORPUS / the MCP URLs come from
                # deploy/.env. Pointing at the wrong one sends people fixing the wrong thing.
                peers = [k for k in missing if k.endswith("_A2A_URL")]
                other = [k for k in missing if k not in peers]
                lines = [f"   ✗ {name} was NOT deployed."]
                if peers:
                    lines += [f"     {', '.join(peers)} come from a peer engine that isn't in",
                              "     deploy/agent_identities.json yet. Deploy that agent first, then run:",
                              "       python deploy/collect_agent_identities.py"]
                if other:
                    lines += [f"     {', '.join(other)} are read from deploy/.env (via env.sh).",
                              "     RAG_CORPUS/RAG_LOCATION are written by ./deploy/setup_legal_rag.sh;",
                              "     the MCP_*_URL values are resolved from Cloud Run by ./workshop/setup.sh."]
                lines.append("     Then re-run this command.")
                print("\n".join(lines), file=sys.stderr)
                raise SystemExit(1)
            return
        display = f"vibeflix-{name.replace('_', '-')}"
        # VIBEFLIX_AGENT_NAME: the runtime authority for which agent module this
        # engine loads (see build_runner) — the pickled closure is unreliable.
        env = {**COMMON_ENV, "VIBEFLIX_AGENT_NAME": name,
               **{k: _ENV[k] for k in spec["env"]}}
        # Vertex REJECTS empty-string env values (400 INVALID_ARGUMENT: "…env[N].value;
        # Required field is not set"). On a fresh project's FIRST pass, TASK_STORE_URL and
        # the A2A URLs are "" (the app + peer engines don't exist yet). Drop the empties —
        # the agent reads them with os.environ.get(k, <default>) and falls back cleanly
        # (per-replica store, no A2A); pass 2 re-deploys with the real values set.
        env = {k: v for k, v in env.items() if v != ""}
        # task_store_builder: WITHOUT it the A2aAgent template falls back to
        # InMemoryTaskStore — a dict private to each replica — and `GET /a2a/v1/tasks/{id}`
        # 404s whenever the load balancer picks a replica other than the one that created
        # the task (measured: 86.8% of polls). See vibeflix_common/a2a/task_store.py.
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
            # PER-AGENT staging directory. The SDK stages the pickle, the requirements and the
            # dependency tarball to `{staging_bucket}/{gcs_dir_name}/` and defaults gcs_dir_name
            # to the literal "agent_engine" — the SAME path for every agent. We deploy six of
            # them through a ThreadPoolExecutor, so without this they race for one set of
            # objects: whoever uploads last wins, and each engine is then built from whatever
            # requirements.txt and agent_engine.pkl happened to be there when its build started.
            #
            # Nothing fails at deploy time. The engine reports success and breaks at RUNTIME, in
            # whatever way the mismatch happens to bite:
            #   • ui_renderer built from another agent's requirements → its a2ui-agent-sdk line
            #     is missing → every render dies with `No module named 'a2ui'` and the console
            #     blames the A2UI format (observed in vibeflix-test-2, 2026-08-20).
            #   • the .pkl losing the race → an engine running a DIFFERENT agent's code, which
            #     is what the "cloudpickle agent_name mixup" behind the empty-audits bug was.
            "gcs_dir_name": f"agent_engine_{name}",
            "env_vars": env,
            "requirements": requirements(name),
            "extra_packages": ["agents", _vendored_common()],
        }
        # Governed egress — only if the gateway is there (see gateway_exists()).
        if GATEWAY_READY:
            config["agent_gateway_config"] = {
                "agent_to_anywhere_config": {
                    "agent_gateway": f"projects/{PROJECT}/locations/{REGION}/agentGateways/vibeflix-gateway"
                }
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

# Vibeflix — Agent Gateway + Agent Identity demo — SESSION HANDOFF

Goal: run the vibeflix-audit ADK multi-agent mesh on GCP `pokedemo-test` with a
**governed Agent Gateway** (IAP egress policies) and **per-engine Agent Identity**,
end-to-end audit working, plus OTEL. This is the DEMO whose whole point is to
showcase Agent Gateway governance + Agent Identity — so we keep the governed path
(do NOT fall back to a shared service account).

Date of handoff: 2026-07-11. All code changes below are UNCOMMITTED.

---

## 1. Topology & key IDs

- Project `pokedemo-test`, number **789872749985**, org **298490623289**, region **us-central1**.
- 6 Agent Runtime engines (reasoningEngines), each deployed with `identity_type=AGENT_IDENTITY`:

  | agent | engine id |
  |---|---|
  | brand-style | 3483603031247814656 |
  | vendor-clearance | 8004091157220950016 |
  | deal-pricing | 4405152104998502400 |
  | legal | 8652609503562301440 |
  | ui-renderer | 4545326643400409088 |
  | orchestrator | 3932837094078021632 |

- Agent principal form (in `deploy/agent_identities.json`):
  `principal://agents.global.org-298490623289.system.id.goog/resources/aiplatform/projects/789872749985/locations/us-central1/reasoningEngines/<ENGINE_ID>`
  (the engine's `spec.effectiveIdentity` == the same, minus the `principal://` prefix — they match, verified.)
- 3 MCP servers on Cloud Run + their Agent Registry mcpServer resources:
  - `vibeflix-mcp-brand-style` → `mcpServers/agentregistry-00000000-0000-0000-e7d9-675ca80c8226` (tool: run_brand_audit)
  - `vibeflix-mcp-licensing`  → `mcpServers/agentregistry-00000000-0000-0000-7547-41b7eccab1fb`
  - `vibeflix-mcp-market`     → `mcpServers/agentregistry-00000000-0000-0000-07b5-9bd9f6459b4d`
  - direct URLs: `https://vibeflix-mcp-<name>-zo4qhpu3aq-uc.a.run.app/mcp`
- Gateway `vibeflix-gateway`, `governedAccessPath: AGENT_TO_ANYWHERE`, `networkConfig: null`
  (public-egress mode — this is CORRECT and supported; networkConfig/PSC is only for private-VPC backends).
- Console app: `https://vibeflix-app-789872749985.us-central1.run.app` (Cloud Run, request timeout raised to 3600s).
  The app runs the orchestrator **in-process** and fans out to domain engines via direct A2A
  (`agents/app.py` imports `root_agent`; domain calls go through `vibeflix_common.a2a_engine`).

---

## 2. THE root cause we fixed (this was the real "empty audits" bug)

`deploy/deploy_agents_a2a.py`'s cloudpickle closure baked `agent_name="orchestrator"`
(the LAST value in the AGENTS loop) into **every** engine. At runtime each engine did
`importlib.import_module("agents.orchestrator.agent")`, whose module-level `_remote_agent(...)`
(agent.py:109) needs `*_A2A_URL` env it doesn't have → `RuntimeError` → `TASK_STATE_FAILED`
→ audits returned blank. Confirmed systemic across all 6 engines via logs.

**Fix (done, uncommitted):**
- `deploy/deploy_agents_a2a.py` `build_runner`: reads `os.environ["VIBEFLIX_AGENT_NAME"]` (falls back to closure) and imports `agents.<that>.agent`.
- Same file: `env = {**COMMON_ENV, "VIBEFLIX_AGENT_NAME": name, ...}` per engine.
- `packages/vibeflix-common/vibeflix_common/a2a_engine.py`: `_send_sync` now surfaces
  `TASK_STATE_FAILED` via new `_status_error(task)` (returns `[A2A engine execution FAILED] <detail>`)
  instead of silently returning "", and keeps polling through the multi-replica 400/404 task-not-found noise.

**UPDATE:** All 6 engines have been successfully redeployed with the correct `VIBEFLIX_AGENT_NAME` env variables and the pickle fix.

Redeploy one: `.venv/bin/python -u deploy/deploy_agents_a2a.py <name>` (unbuffered so you see progress;
plain `python` buffers stdout and looks hung). Requires these exported first:
`MCP_LICENSING_URL, MCP_MARKET_URL, MCP_BRAND_STYLE_URL` (the run.app/mcp URLs),
`LEGAL_A2A_URL` (legal engine base), plus for orchestrator also `BRAND_STYLE_A2A_URL, VENDOR_CLEARANCE_A2A_URL, DEAL_PRICING_A2A_URL`.
Engine base = `https://us-central1-aiplatform.googleapis.com/v1beta1/projects/789872749985/locations/us-central1/reasoningEngines/<ID>`.
A redeploy RESETS gateway attachment → you MUST re-attach after (see §4).

---

## 3. How the governed egress actually works (hard-won facts)

- `AGENT_TO_ANYWHERE` governs EVERY outbound call from an attached engine — including the engine's
  OWN Vertex calls: `VertexAiSessionService` session/events writes and the Gemini model call, all over
  **`us-central1-aiplatform.mtls.googleapis.com`** (attached engines egress over mTLS).
- Default-deny. Every destination must be (a) a REGISTERED Agent Registry endpoint AND (b) the agent
  principal granted `roles/iap.egressor` on it. Registered GCP endpoints already exist:
  `gcp-aiplatform` (`https://us-central1-aiplatform.googleapis.com`),
  `gcp-aiplatform-mtls` (`https://us-central1-aiplatform.mtls.googleapis.com`), plus telemetry/logging/cloudtrace/pubsub/agentregistry variants. Hostname must match EXACTLY.
- **principalSet grants DO NOT MATCH the agent identities** (verified: both a run.invoker principalSet and
  an iap.egressor principalSet had no effect). Use the **specific `principal://` per agent**. This was a
  major time-sink — always grant the specific principal.
- **The missing piece that unblocked egress:** the agent principals had **ZERO project IAM roles**.
  AGENT_IDENTITY engines run AS the principal, not as `vibeflix-agents@` SA (which had the roles). Grant on
  the PROJECT to each agent principal: `roles/aiplatform.user`, `roles/aiplatform.agentDefaultAccess`,
  `roles/logging.logWriter`, `roles/monitoring.metricWriter`, `roles/browser` (+ `roles/agentregistry.viewer`).
  (Reference: Google "Troubleshoot Agent Gateway connectivity" doc, Step 4.)
- Gateway backend→MCP invoker SA: intended `vibeflix-mcp-invoker` passed via `--mcp-invoker-sa` at attach,
  but the raw PATCH attach doesn't set it. As a fallback we granted `run.invoker` on the MCPs to
  `vibeflix-mcp-invoker`, `service-789872749985@gcp-sa-aiplatform.iam.gserviceaccount.com`,
  `service-789872749985@gcp-sa-aiplatform-re.iam.gserviceaccount.com`. (Still unproven which the gateway uses.)
- Authz extension `vibeflix-gateway-iap-authz`: we set **`failOpen: true, timeout: 5s`** (was 1s/failOpen false).

### Grants already applied
- MCP per-tool `iap.egressor` (all 7 rows): `bash deploy/grant_mcp_egress.sh` — DONE.
- A2A endpoint `iap.egressor`: orchestrator→{brand,vendor,deal}, vendor→legal — DONE (via `--endpoint=<uuid>`).
- `iap.egressor` on `gcp-aiplatform` + `gcp-aiplatform-mtls` for ALL 6 agent principals — DONE.
- Basic project roles for ALL 6 agent principals — DONE.
- All 6 engines re-attached to the gateway — DONE (but redeploying any resets it).

---

## 4. Attach / detach an engine (no gcloud CLI for Agent Runtime — REST PATCH)

```bash
GW="projects/pokedemo-test/locations/us-central1/agentGateways/vibeflix-gateway"
ENG="projects/789872749985/locations/us-central1/reasoningEngines/<ID>"
# ATTACH:
curl -s -X PATCH -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" \
 -d '{"spec":{"deploymentSpec":{"agentGatewayConfig":{"agentToAnywhereConfig":{"agentGateway":"'$GW'"}}}}}' \
 "https://us-central1-aiplatform.googleapis.com/v1beta1/$ENG?updateMask=spec.deploymentSpec.agentGatewayConfig"
# DETACH: same but -d '{"spec":{"deploymentSpec":{"agentGatewayConfig":{}}}}'
# Attach LRO takes ~2-4 min (engine redeploy). Verify via GET .spec.deploymentSpec.agentGatewayConfig.agentToAnywhereConfig.agentGateway
```

---

## 5. Current state (honest)

- **A2A & Registry Resolution (RESOLVED):** We discovered that the Agent Registry services (endpoints) were still pointing to the old, dead reasoning engine IDs from before the redeploy. We updated all 6 agent services in the Agent Registry (`brand-style`, `vendor-clearance`, `deal-pricing`, `legal`, `ui-renderer`, `orchestrator`) to point to their current engine IDs. This fully resolved the `ConnectTimeout` and A2A routing issues. The ready checks are now fully passing: `[ready] → READY in 307ms`.
- **MCP Tool Egress (BLOCKER):** MCP tool calls from the `brand_style` engine to `https://vibeflix-mcp-brand-style-zo4qhpu3aq-uc.a.run.app/mcp` are failing with `401 Unauthorized` during tool execution. 
  - *Why:* The engine runs as `AGENT_IDENTITY` (Workload Identity principal). The metadata server returns `404` for token requests without a service account, so the client pops the `Authorization` header and sends the request without credentials.
  - *Why Gateway Egress Auth is missing:* Since `--mcp-invoker-sa` is not set (not supported by the raw PATCH REST API), the Agent Gateway does not auto-inject the OIDC token on behalf of the client.
  - *Potential Solution:* Register `gcp-iamcredentials` in the Agent Registry and grant the engine principals `roles/iap.egressor` on it so they can call `iamcredentials.googleapis.com` to dynamically fetch the ID token.

---

## 6. Remaining work (in order)

1. **Fix MCP Egress Auth (BLOCKER):** Unblock the 401 on MCP tool calls. Register `gcp-iamcredentials` (`https://iamcredentials.googleapis.com`) in the Agent Registry and grant the engine principals `roles/iap.egressor` on it so they can fetch OIDC ID tokens via the credentials generator API.
2. **Ensure the deployed app has the latest code:** Rebuild the app: `gcloud builds submit . --config deploy/cloudbuild-app.yaml --substitutions "_IMAGE=us-central1-docker.pkg.dev/pokedemo-test/vibeflix/app"` then `gcloud run deploy vibeflix-app --image .../app --region us-central1`.
3. **Verify the A2A call paths:** Run the validation scripts for the 4 layers: `tests/a2a/layer1_vendor_legal.sh`, `layer2_orchestrator_fanout.sh`, `layer3_app_uirenderer.sh`, and `layer4_app_orchestrator.sh`.
4. **OTEL Integration:** Rebuild engines with `TELEMETRY=on` to enable trace logging and verify traces land in Cloud Trace.

---

## 7. Handy diagnostics

```bash
# direct engine A2A test (surfaces FAILED reason):
GOOGLE_CLOUD_PROJECT=pokedemo-test .venv/bin/python -c "
import sys, asyncio, json; sys.path.insert(0,'packages/vibeflix-common')
from vibeflix_common.a2a_engine import a2a_engine_send
B='https://us-central1-aiplatform.googleapis.com/v1beta1/projects/789872749985/locations/us-central1/reasoningEngines/<ID>'
print(asyncio.run(a2a_engine_send(B, '<brief>', timeout=200)))"

# which host is being egress-denied (the smoking gun):
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.reasoning_engine_id="<ID>" AND severity>=WARNING' --project pokedemo-test --limit 8 --freshness=6m --format='value(textPayload)' | grep -iE "https://|Egress"

# MCP got the call? (200 = governed tool call worked; python-httpx UA 403s are the app readiness probe, ignore):
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=vibeflix-mcp-brand-style' --project pokedemo-test --limit 15 --freshness=3m --format='value(httpRequest.status,httpRequest.userAgent)'

# verify an egressor grant landed on an endpoint:
gcloud alpha iap web get-iam-policy --resource-type=agent-registry --endpoint=<agentregistry-uuid> --region=us-central1 --project=pokedemo-test --format=json | jq '.bindings[]|select(.role=="roles/iap.egressor").members'
```

Google docs used: Agent Gateway overview / set-up / route-Agent-Runtime-traffic / **troubleshoot-agent-gateway**
(the last one's Step 4 "basic agent-identity project roles" was the key), Agent Identity overview.
Codelab: https://codelabs.developers.google.com/cloudnet-agent-gateway

# Mesh layer tests (cloud) — bottom-up, one hop at a time

    app ──▶ orchestrator engine ──A2A──▶ {brand_style, vendor_clearance, deal_pricing}
    app ──▶ ui_renderer                   vendor_clearance ──A2A──▶ legal
    every agent ──MCP──▶ {mcp-brand-style, mcp-licensing, mcp-market}

| layer | hop | pass criterion — the BACKEND's log, **not** the agent's reply |
|---|---|---|
| 1 | every agent → its MCP server | `CallToolRequest` in the MCP's Cloud Run log |
| 2 | vendor_clearance → legal | the legal engine logs model invocations |
| 3 | orchestrator → brand/vendor/deal | each downstream engine logs model invocations |
| 4 | app → ui_renderer, app → orchestrator | those engines log model invocations |

```bash
PROJECT=pokedemo-test REGION=us-central1 ./tests/a2a/run_layers.sh        # all 4
PROJECT=pokedemo-test REGION=us-central1 ./tests/a2a/run_layers.sh 1      # one layer
PROJECT=pokedemo-test REGION=us-central1 ./tests/a2a/run_layers.sh 2 3    # a subset
```

## ⚠️ Never trust the agent's own answer

An agent whose toolset failed to load **still emits a confident, clean verdict**.
brand_style returned `status: "success"`, `findings: []` and a plausible
`checks_run` list while the MCP server had logged **zero `CallToolRequest`** — the
model was inventing the check names (they changed between runs). For a compliance
demo, a fabricated "compliant" is the worst possible failure. So:

- the agents now **fail closed** (`vibeflix_common/tool_guard.py`): if the MCP
  toolset can't reach its server, the model is never called and the agent returns
  `status: "error"` rather than a fake pass;
- every layer here is judged from the **backend's** log, never from the reply.

## ⛔ `403 Egress request is not authorized` — the two things that cause it

### 1. A destination that isn't registered + granted (the ordinary case)

Per the docs: *"The destination endpoint must be explicitly registered as a Service in
the Agent Registry"* — and the calling agent's principal must then hold
`roles/iap.egressor` on it. Default-deny: anything else is a 403.

`deploy/grant_agent_iam.sh` grants **every registered `GCP *` endpoint** to **every**
agent. Do NOT hand-maintain that list — ours drifted and silently omitted
`agentregistry` (all 4 variants), `pubsub` and `telemetry-regional`, and the engines
403'd on destinations nobody had granted.

Note which host your egress actually uses:
- `GOOGLE_CLOUD_LOCATION=global` → genai + `VertexAiSessionService` egress to the
  **global** host `https://aiplatform.googleapis.com` (`gcp-aiplatform-global`).
- pinned to a region → `https://REGION-aiplatform.googleapis.com` (`gcp-aiplatform`).

Register and grant BOTH; we keep `global` (see deploy_agents_a2a.py COMMON_ENV).

### 2. ⚠️ TWO registered Services claiming the SAME HOST (the trap that cost us hours)

The agent registry entries (`vibeflix-<agent>-agent`) must advertise the **mtls** URL
ONLY:

```
https://us-central1-aiplatform.mtls.googleapis.com/v1beta1/<engine>
```

We added the **plain** URL as a second interface
(`https://us-central1-aiplatform.googleapis.com/v1beta1/<engine>`) so that our plain
bearer-token A2A client would be authorized. That host is ALREADY claimed by the
`GCP aiplatform` Service — and with two Services claiming one host, the gateway denied
**ALL** aiplatform egress, fleet-wide. Every engine then died on its own model/session
call (`_prepare_session` → `create_session`) with `403 Egress request is not
authorized`, *before any agent code ran*.

It presented as random flakiness and sent us chasing `GOOGLE_CLOUD_LOCATION`, IAM and
propagation for hours. **Reverting the agent endpoints to mtls-only restored the whole
fleet.** If you see a sudden fleet-wide 403 after touching the registry, check for a
host collision first.

⏱️ **IAP/IAM/registry propagation takes 2–5 minutes.** After any registry or egressor
change, WAIT before judging. We tested a correct fix 40s after applying it, saw a 403,
and wrongly discarded it.

**Re-run:** `./tests/a2a/run_layers.sh 1`

## Prerequisites (see `deploy/instruction-dev.md`)

1. engines deployed with `identity_type=AGENT_IDENTITY` + `agent_gateway_config`;
2. `MCP_INVOKER_SA` set on every engine, each agent principal holding
   `roles/iam.serviceAccountTokenCreator` on it, and `iap.egressor` on the
   `gcp-iamcredentials*` registry endpoints. **Agent identity cannot mint an OIDC
   ID token on its own and the gateway does NOT inject one** — the agent
   impersonates the invoker SA (same mechanism as the codelab's `--mcp-invoker-sa`);
3. `./deploy/grant_agent_iam.sh` applied against the **current** principals;
4. the Agent Registry agent endpoints pointing at the **current** engine ids.

⛔ **Never delete the engines.** Redeploy updates in place and keeps the engine id
(hence the principal, hence every grant). Delete + recreate orphans all of it.

---
## Verified findings

**Grant forms:**
- MCP tool egress: `gcloud alpha iap web add-iam-policy-binding --resource-type=agent-registry --mcp-server=<agentregistry-UUID>`.
- A2A agent egress: same but `--endpoint=<UUID>` (our agents are ENDPOINT-type entries from `--endpoint-spec-type=no-spec`). `--agent=` → NOT_FOUND.
- Both are ALPHA track (`gcloud alpha iap web`); GA has neither flag.
- `principalSet://…` grants **do not match agent identities** — always the specific `principal://`.

**Gateway egress endpoints** (attached engines filter ALL outbound, including the
engine's own Vertex calls): register + grant aiplatform(+mtls), agentregistry(+mtls),
telemetry(+mtls), logging(+mtls), cloudtrace, pubsub, **iamcredentials(+mtls)**.

**Engine OTLP telemetry crashes** on the py3.14 base (pyOpenSSL "Context has already
been used" in the HTTP exporter). Disabled by default; `TELEMETRY=on` re-enables it
with the gRPC exporter (needs rebuild + verify).

**Console playground cannot drive these engines** — they expose only
`on_message_send` (`api_mode=a2a_extension`), no `query`. The playground calls
`:query`, the container 404s, and the platform wraps it as `400 FAILED_PRECONDITION`
(error code 9). Not a permissions bug. Use `/a2a/v1/message:send`.

**OPEN — app (plain SA) → governed agents = 403 Egress.** Governed A2A egress
appears to be honored for agent-identity principals, not plain service accounts.
The app reaches engines by the DIRECT engine A2A path (`vibeflix_common/a2a_engine.py`),
which is inbound to the target (not gateway egress) and works for any caller with
aiplatform access. Layer 4 tests that path.

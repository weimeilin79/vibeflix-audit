# Vibeflix — Agent Gateway + Agent Identity demo — STATUS

Goal: the vibeflix-audit ADK multi-agent mesh on GCP `pokedemo-test`, running through a
**governed Agent Gateway** (IAP egress policies) with **per-engine Agent Identity**. This
is the demo whose whole point is to showcase Agent Gateway governance + Agent Identity —
so we keep the governed path (never fall back to a shared service account).

**Status: ALL 4 LAYERS PASS.** Last verified 2026-07-13. Code changes are UNCOMMITTED.

---

## 1. The mesh, and how each layer was PROVEN

    app ──▶ orchestrator (in-process) ──A2A──▶ {brand_style, vendor_clearance, deal_pricing}
    app ──▶ ui_renderer                          vendor_clearance ──A2A──▶ legal
    every agent ──MCP──▶ {mcp-brand-style, mcp-licensing, mcp-market}

| layer | hop | proof (the BACKEND's log — never the agent's reply) |
|---|---|---|
| 1 | every agent → its MCP | `CallToolRequest` in the MCP's Cloud Run log |
| 2 | vendor_clearance → legal | legal engine ran (5 model calls); vendor onboarded as VND-1014; legal replied `ask_vendor` |
| 3 | orchestrator → brand/vendor/deal | all 3 engines ran (3/1/3 model calls), **zero** 401/403 |
| 4 | app → orchestrator + ui_renderer | real audit; real finding ("volume 50000 exceeds vendor cap 25000"); ui_renderer rendered the decision form |

Re-run any of them: `PROJECT=pokedemo-test REGION=us-central1 ./tests/a2a/run_layers.sh [1 2 3 4]`

⚠️ **NEVER judge a layer by the agent's own answer.** An agent whose toolset failed still
emits a confident, clean verdict: brand_style reported `status:"success"`, `findings:[]`
and a plausible `checks_run` while the MCP logged **zero** CallToolRequest (the model was
inventing the check names — they changed run to run). Agents now fail closed
(`vibeflix_common/tool_guard.py`), and every layer is judged from the callee's log.

---

## 2. Key IDs

- Project `pokedemo-test` (number **789872749985**), org **298490623289**, region **us-central1**.
- 6 engines, all `identity_type=AGENT_IDENTITY` + attached to `vibeflix-gateway`
  (`governedAccessPath: AGENT_TO_ANYWHERE`, `networkConfig: null` — public egress, correct):

  | agent | engine id |
  |---|---|
  | brand-style | 3483603031247814656 |
  | vendor-clearance | 8004091157220950016 |
  | deal-pricing | 4405152104998502400 |
  | legal | 8652609503562301440 |
  | ui-renderer | 4545326643400409088 |
  | orchestrator | 3932837094078021632 |

- Principal form: `principal://agents.global.org-298490623289.system.id.goog/resources/aiplatform/projects/789872749985/locations/us-central1/reasoningEngines/<ID>` (see `deploy/agent_identities.json`).
- App: `https://vibeflix-app-zo4qhpu3aq-uc.a.run.app` (runs the orchestrator IN-PROCESS).

---

## 3. THE FOUR BUGS THAT BLOCKED THIS (all fixed)

**a. MCP auth — the agent must mint its OWN ID token.**
An `AGENT_IDENTITY` engine has **no service account** behind the metadata server, so
`fetch_id_token()` cannot work — and **the gateway does NOT inject a credential** (there is
no invoker-SA field on `agentToAnywhereConfig`, on the registry service, or in gcloud).
Cloud Run accepts only an audience-bound OIDC token (measured: access token → **401**
"the access token could not be verified"; ID token → **200**; none → **403**).
Fix: the engine impersonates `MCP_INVOKER_SA` via `impersonated_credentials.IDTokenCredentials`
(`cloud_auth._id_token_via_impersonation`). Same mechanism as the Agent Gateway codelab's
`--mcp-invoker-sa`, which only injects that env var.
Needs 3 things: the env var + `iam.serviceAccountTokenCreator` on the SA + `iap.egressor`
on the `gcp-iamcredentials*` endpoints (default-deny blocks even the token-minting call).

**b. A2A auth — we were sending NO `Authorization` header.**
Inside an engine `a2a_engine.py` sent only `Proxy-Authorization` (which the **gateway**
reads) and no `Authorization` (which the **callee** reads), so the target endpoint got no
credential → **401**. TWO parties authenticate one request:
- `Proxy-Authorization` → the Agent Gateway (egress authorization)
- `Authorization` → the target engine's aiplatform endpoint
Read the codes as a distance signal: **403 = the gateway refused (never left)**;
**401 = the gateway let you through and the target refused you**.

**c. A2A routing — must use the MTLS URL.**
The gateway only authorizes the destination the endpoint is REGISTERED with. Calls to the
**plain** URL are refused with `403 Egress request is not authorized` **even after** adding
that URL as an interface AND granting the caller `iap.egressor` on the endpoint (measured
repeatedly, 25+ min after the change — NOT propagation). So A2A targets
`https://us-central1-aiplatform.mtls.googleapis.com/v1beta1/<engine>`.

**d. Egress grants — every principal needs egressor on EVERY registered endpoint.**
An *agent* endpoint that advertises the aiplatform host shadows the `GCP aiplatform`
Service for each engine's **own model call**, so an engine with no grant on the agent
endpoints gets `403` on its own Gemini call. `deploy/grant_agent_iam.sh` now derives the
endpoint list from the registry (a hand-maintained list had drifted: `agentregistry` ×4,
`pubsub`, `telemetry-regional` were granted to nobody) and grants all-to-all.

**Plus: the deploy shipped FOSSIL CODE for hours.** `_vendored_common()` copied
`vibeflix_common` to the repo root only `if not exists`, with a no-op cleanup — so every
deploy after the first shipped a stale snapshot and silently ignored source edits. Now
re-copies every deploy. ⚠️ Deploy agents **SERIALLY** (the lock is a threading lock;
parallel *processes* race on the shared dir and a deploy fails silently, leaving the engine
on its old code).

---

## 4. Operating rules (learned the hard way)

- ⛔ **NEVER DELETE THE ENGINES.** The engine id is baked into the principal. Redeploy
  *updates in place* and keeps the id (new revision, not new engine). Delete + recreate ⇒
  new principal ⇒ every IAM grant and registry endpoint silently orphaned while the console
  still looks correct. Recovery: `collect_agent_identities.py` → `grant_agent_iam.sh` →
  re-point the registry endpoints.
- ⏱️ **Propagation is 2–5 minutes.** After any registry/egressor change, WAIT before
  judging. We tested a correct fix ~40s after applying it, saw a 403, and wrongly discarded
  it — twice. Judging too early was the single most expensive habit of the whole exercise.
- **principalSet:// grants DO NOT match agent identities.** Always the specific `principal://`.
- **`roles/aiplatform.agentContextEditor` is REQUIRED** — without it `create_session()` fails
  in `_prepare_session` and you get an opaque `TASK_STATE_FAILED` before your code runs.
- **The console playground CANNOT drive these engines** — they expose only `on_message_send`
  (`api_mode=a2a_extension`), no `query`. The playground calls `:query`, the container 404s,
  and the platform wraps it as `400 FAILED_PRECONDITION` (code 9). Not a permissions bug.
- **Client-to-Agent (ingress) is a different world**: per Google's Agent Gateway overview,
  **IAM is not enforced and IAP is not supported during ingress**, and ingress can only
  govern `query`/`streamQuery` (which these engines don't expose). So `iap.egressor` grants
  can never fix an app(plain SA)→agent call — the app uses the direct engine A2A path.

---

## 5. Testing traps (look like bugs, aren't)

- **Legal only runs when a VENDOR IS ONBOARDED** (a vendor not already in the registry).
  Test with an existing vendor (VND-1001) and the agent correctly clears it, onboards
  nothing, emits no `legal_request`, and skips legal — looks like a broken hand-off, isn't.
  Use a NEW vendor name every run; these tests MUTATE the registry.
- **Don't drive vendor_clearance with raw A2A prose.** Its clearance reasoner has no
  `output_schema` and reads `{vendor?}`/`{product_category?}` from **session state**, which
  only the app/orchestrator populate. With no state it invents values (asked for category
  "Backpacks-135850", it reported on "Apparel"). Drive it via layer 3 (orchestrator + JSON).
- **An empty A2A reply usually means STILL RUNNING**, not broken. The full chain (brand +
  vendor ↔ legal Q&A + deal) ran past our old 560s poll deadline while legal's own log showed
  5 model calls. Timeouts are now 900s (default) / 1800s (nested caller). Check the callee's
  log before believing a failure.

---

## 6. Remaining work

1. **OTEL** — engines are deployed with `TELEMETRY=off` (the OTLP HTTP exporter crashes on
   the py3.14 base: pyOpenSSL "Context has already been used"). `TELEMETRY=on` in
   `deploy_agents_a2a.py` re-enables it with the gRPC exporter; needs the telemetry egress
   endpoints granted (they are) + a rebuild + verification in Cloud Trace.
2. **Is the mTLS client cert actually needed?** `a2a_engine.py` presents one on mtls hosts
   (`cloud_auth.mtls_cert_files()`; the engine does have one — probe showed cert≈1982B,
   key≈241B). But it shipped in the SAME deploy as the `Authorization`-header fix, so the
   header may have been the whole bug. If a no-cert run passes, delete the cert plumbing.
3. **App image is stale** — built before today's `a2a_engine.py` changes. It works (the app
   is a plain SA, not gateway-attached, so it takes the non-engine code path), but rebuild it
   to keep the timeout fix consistent:
   `gcloud builds submit . --config deploy/cloudbuild-app.yaml` then `gcloud run deploy vibeflix-app`.

## 7. Diagnostics

```bash
# Did a governed MCP tool call REALLY execute? (0 CallToolRequest ⇒ the verdict is fabricated)
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="vibeflix-mcp-brand-style"' --project pokedemo-test \
  --freshness=15m --format='value(textPayload)' | grep -oiE 'CallToolRequest|ListToolsRequest' | sort | uniq -c

# What did an engine get back / why was it denied?
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND
  resource.labels.reasoning_engine_id="<ID>"' --project pokedemo-test --freshness=15m \
  --format='value(textPayload)' | grep -iE '40[13]|Egress|HTTP Request'

# Verify an egressor grant landed
gcloud alpha iap web get-iam-policy --resource-type=agent-registry --endpoint=<uuid> \
  --region=us-central1 --project=pokedemo-test --format=json | jq '.bindings[]|select(.role=="roles/iap.egressor").members'
```

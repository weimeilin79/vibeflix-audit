# GOTCHAS.md — the hard-won rules. **This is the single source of truth.**

Every rule below cost us hours, and **every one of them fails SILENTLY** — the deploy exits 0,
the console looks correct, and the mesh misbehaves in a way that points at something else
entirely. That is what makes them expensive.

Other docs **link here**. Do not restate a rule in another file: we tried that, and the copies
drifted until they contradicted each other and, in one case, actively lied (a handoff doc still
claiming `TELEMETRY=off` long after tracing was mandatory).

Referenced by: [`README.md`](../README.md) · [`topology.md`](../topology.md) ·
[`deploy/README.md`](README.md) · [`instruction-sre.md`](instruction-sre.md) ·
[`instruction-dev.md`](instruction-dev.md) · [`tests/a2a/README.md`](../tests/a2a/README.md) ·
[`deploy-vibeflix-skill/SKILL.md`](../deploy-vibeflix-skill/SKILL.md)

---

## G1 · ⛔ NEVER DELETE AN ENGINE

The engine id is baked into its identity: `principal://…/reasoningEngines/<ID>`. Redeploying the
same display name **updates in place** and keeps the id (Agent Runtime makes a new immutable
*revision*, not a new engine).

**Delete + recreate ⇒ new id ⇒ new principal ⇒ every IAM grant and registry endpoint silently
points at a dead principal — while the console still looks correct.**

Recovery: `collect_agent_identities.py` → `grant_agent_iam.sh` → re-point the registry endpoints.

## G2 · Deploy the engines SERIALLY

`deploy_agents_a2a.py` with no args (one process) is safe. **Several processes in parallel race on
the vendored `vibeflix_common/` dir and a deploy fails *silently*, leaving that engine on its OLD
code** — so you debug behaviour that isn't in the source you're reading.

## G3 · The engines are deployed TWICE, with the app in between

The dependency is circular:
- `deploy_agents_a2a.py` reads **`TASK_STORE_URL` from the APP's Cloud Run URL**;
- the **app** needs the **engines'** A2A URLs (`agent_identities.json`);
- `grant_agent_iam.sh` needs the **app's URL** to register it as an egress destination, or the
  engines aren't *allowed* to reach the task store.

```
engines PASS 1 → collect_agent_identities.py → THE APP → gateway + grants → engines PASS 2
```

**Skip pass 2 and it all still "works"** — every engine silently falls back to a **per-replica**
in-memory task store and ~87% of task polls 404.
**Tell:** `[task-store] … FAILED … falling back to the per-replica store` in the engine logs, and
`[taskstore] CREATE …` never appearing in the app's. Check: `verify_deployment.sh 3b`.

## G4 · ⏱️ Wait 2–5 minutes after ANY registry/IAM change

Propagation is not instant. **We discarded a *correct* fix twice** by testing ~40s in, seeing a
403, and concluding it hadn't worked. Judging too early was the single most expensive habit in
this project.

## G5 · The app must be `--min-instances=1 --max-instances=1`

Correctness, **not** cost control. Two ways it breaks:
1. The **task store is a dict in the app process** — a second instance splits it, and every task
   poll landing on the wrong one 404s (the exact bug the store exists to kill).
2. The **Pub/Sub mesh subscription is a COMPETING-CONSUMER queue** — each event goes to exactly
   ONE subscriber. With 2+ app instances the telemetry is split, and the console's workflow graph
   renders only a fraction of its nodes. *(Measured with 3 revisions alive: 10 / 10 / 5 events —
   the browser saw a third of the graph.)*

## G6 · Tracing must be ON for every agent — and it used to default OFF

The traces **are** the demo. `TELEMETRY` now defaults to `on`; only an explicit `TELEMETRY=off`
disables it.

It used to be opt-in, and **a redeploy that merely FORGOT the flag untraced all six engines,
reported success, and exited 0.** Every trace vanished with no error anywhere.

**Never trust the exit code — read the flag back** from all six engines
(`verify_deployment.sh 3b`).

## G7 · Verify from the BACKEND's log, never the agent's reply

An agent whose toolset failed to load still emits a **confident, clean verdict**. brand_style once
reported `status:"success"`, `findings:[]` and a plausible `checks_run` while the MCP server had
logged **zero `CallToolRequest`** — the model invented the check names, and they changed run to run.

Proof of a tool call is `CallToolRequest` in the MCP server's own log. Nothing else counts.

## G8 · The Agent Gateway governs **HTTP egress only**

It **cannot match a gRPC channel or a raw TCP socket** to a registered endpoint. Consequences:
- The Pub/Sub **gRPC** publisher is refused (`403 Egress request is not authorized`) **no matter
  how you register or grant it** — and the failure lands on an unread future, so it fails
  **silently**: agents run fine, the telemetry just never leaves. Mesh telemetry therefore
  publishes over **Pub/Sub REST**.
- **Cloud SQL / Postgres and Redis are unusable** as an A2A task store (raw TCP). That is why the
  store lives behind the app over plain HTTPS.
- The MCP servers are plain Cloud Run and are **not** gateway-governed — which is why their tool
  LEDs kept working while the agents' graph stayed dark, making it look like a frontend bug for a
  very long time. It wasn't.

## G9 · An AGENT_IDENTITY engine has **no service account**

There is no SA behind the metadata server, so `fetch_id_token()` cannot work — **and the gateway
does not inject a credential for you** (no invoker-SA field exists on `agentToAnywhereConfig`, on
the registry Service, or in gcloud). Cloud Run accepts **only** an audience-bound OIDC **ID token**
(measured: access token → **401**; ID token → **200**; none → **403**).

The engine mints one by **impersonating `MCP_INVOKER_SA`**. That needs **three** things:
1. the `MCP_INVOKER_SA` env var,
2. `roles/iam.serviceAccountTokenCreator` for each agent principal on that SA,
3. `roles/iap.egressor` on `gcp-iamcredentials*` — the gateway is default-deny, so **even the
   token-minting call must be allowlisted**.

Miss any one and every MCP call 401s.

## G10 · `principalSet://` grants do NOT match agent identities

They bind without error and **match nothing**. Always the specific `principal://`.

## G11 · Two A2A hosts — the app and the engines do NOT use the same one

| caller | host | why |
|---|---|---|
| **engines** (gateway-attached) | `REGION-aiplatform.**mtls**.googleapis.com` | egress goes through the gateway, which only authorizes the destination it **registered** (the mtls url) |
| **the app** (plain SA, no client cert) | `REGION-aiplatform.googleapis.com` | direct — an mtls host demands a client cert the app doesn't have → **401** |

Get it wrong and `message:send` appears to work while every `GET /a2a/v1/tasks/{id}` 401s: the fast
agent finishes, the slow ones **hang forever**, and the tool LEDs never light.

⚠️ A bearer `GET` of the engine *resource* returns 200 on **both** hosts — so that check will
mislead you. It's the A2A *method* calls that mtls rejects.

## G12 · `roles/aiplatform.agentContextEditor` is required — and easy to forget

The agent **writes its own sessions**. Without it, `create_session()` fails inside
`_prepare_session` → an opaque `TASK_STATE_FAILED` **before any of your code runs**.

Needed by the **agent principals** *and* by the **app's SA** (the app polls
`GET /a2a/v1/tasks/{id}`; without it every poll 401s, `/api/audit` 500s, and vendor_clearance /
deal_pricing hang forever while brand_style appears to finish).

## G13 · `GOOGLE_CLOUD_LOCATION=global` for the engines — keep it

The genai client + `VertexAiSessionService` egress to a host derived from this value. With
`global` + the **global** aiplatform hosts registered and granted, the fleet runs clean. **Pinning
it to the region does NOT work** — even with the regional hosts registered *and* granted, every
engine still 403s. Do not "helpfully" change it.

## G14 · A 404 on a task poll means "wrong replica", NOT "task gone"

The A2A task store used to be **in-memory per replica** while the `GET` is load-balanced
independently — and the replica that *owns* the task is the one **busy executing it**, so the
balancer routes away from precisely the one you need. Misses are not independent coin flips.

An earlier "optimisation" concluded *task gone* after 60s of misses and **abandoned healthy runs**
(and made `recovery` re-run agents that had never failed). The rule: **once a task has been read
successfully even once, it exists — never declare it gone.** Fixed properly by G3's shared store.

## G15 · The token EXPIRES mid-poll — refresh it, don't mint it once

On Cloud Run the metadata server hands back a **cached** token carrying only its *remaining*
lifetime — which can be **minutes, not an hour**. A long A2A poll (a legal escalation runs many
minutes) therefore **outlives a credential minted once at the start**, and the endpoint answers
`401`.

If the poll loop treats that 401 as fatal, it kills the whole audit and the console shows:

```
HTTPError: 401 Client Error: Unauthorized for url: …/a2a/v1/tasks/{id}
```

**It looks exactly like an IAM problem, and it is not.** We chased it as one for hours. The long
paths — a legal run, or a 7-minute `ui_renderer` poll — are simply the ones that outlive their
token. `a2a_engine._send_sync` now re-mints the credential per request and treats `401/403` as
**refresh-and-retry**, not fatal.

## G16 · Local vs cloud is AUTO-DETECTED — `RUN_LOCAL` is only an override

| `RUN_LOCAL` | behaviour |
|---|---|
| **unset (normal)** | **auto-detect** — on GCP (`K_SERVICE`, or the metadata server, which only resolves inside GCP) → credentials **ON**; anywhere else → plain HTTP |
| `true` / `1` / `yes` | force local (no auth) **even on GCP** |
| `false` / `0` / `no` | force cloud auth **even off GCP** (laptop → cloud MCPs) |

Deployed code needs no `RUN_LOCAL` at all: **being on GCP is what turns auth on.** (An older doc
claimed a "local-safe default" — wrong, and it's the kind of claim that sends you looking in the
wrong place.)

---

## How a single hop authenticates — TWO headers, TWO parties

Inside a gateway-attached engine, one call carries **two** credentials:

| header | read by | contains |
|---|---|---|
| `Proxy-Authorization` | **the Agent Gateway** — authorizes the *egress* | the engine's access token (its agent identity) |
| `Authorization` | **the destination** — authenticates you *to it* | Cloud Run / the app → an audience-bound **ID token** ([G9](#g9--an-agent_identity-engine-has-no-service-account)); a Google API → the access token |

> ⚠️ **The gateway authorizes egress. It never signs your request to the backend.** Believing
> otherwise cost days. It also gives you a distance signal:
> **403** = the gateway refused (the call never left) · **401** = the gateway allowed it and the
> **target** refused you.

Sending only `Proxy-Authorization` was a real bug: Google's endpoint saw no credential and
answered 401 — which we long mistook for a missing client certificate. (There is none: a
controlled test with `cert=None` produced zero 401/403. The cert plumbing was deleted.)

---

## Verify, don't assume

`deploy/verify_deployment.sh` is read-only, prints ✅/❌ per check, and **exits non-zero** so it can
gate the next step:

```bash
./deploy/verify_deployment.sh 1    # foundations
./deploy/verify_deployment.sh 2    # MCP servers
./deploy/verify_deployment.sh 3    # engines pass 1 — agent identity on
./deploy/verify_deployment.sh 5    # the app — pinned 1/1, task-store gate 403/200
./deploy/verify_deployment.sh 4    # gateway, registry, egress
./deploy/verify_deployment.sh 4s   # EVERY principal + service account + role
./deploy/verify_deployment.sh 4e   # all 6 engines attached to the gateway
./deploy/verify_deployment.sh 3b   # engines pass 2 — TELEMETRY, TASK_STORE_URL, trace propagation
./deploy/verify_deployment.sh      # everything (79 checks)
```

`3b` and `4s` are the two that catch what a green deploy hides.

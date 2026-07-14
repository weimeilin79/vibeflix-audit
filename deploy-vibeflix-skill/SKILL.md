---
name: deploy-vibeflix
description: >-
  Deploy the vibeflix-audit multi-agent mesh (10 services) to a Google Cloud project:
  foundations (Firestore/Pub-Sub/RAG), 3 MCP servers on Cloud Run, 6 agent engines on
  Vertex Agent Runtime with per-engine Agent Identity, the console app, the governed
  Agent Gateway + all IAM/egress grants, then verify all 4 layers. Use this for a FRESH
  project, a rebuild, or a full redeploy. ALWAYS asks the user for the target project and
  region first — never guess them.
---

# Deploy the vibeflix-audit mesh

You are deploying a **demo whose entire point is Agent Gateway governance + per-engine
Agent Identity**. Never "fix" a problem by falling back to a shared service account or by
opening up access — that deletes the thing being demonstrated.

## STEP 0 — ASK THE USER. Do not guess.

**Before touching anything**, use `AskUserQuestion` to get:

1. **GCP project id** — the deploy target. There is no safe default; deploying to the wrong
   project creates real, billable resources under real identities.
2. **Region** — e.g. `us-central1`. Note two constraints:
   - **Vertex RAG Engine and Memory Bank are REGIONAL** and cannot use `global`.
   - The engines themselves run with `GOOGLE_CLOUD_LOCATION=global` (see gotchas) — that is
     deliberate and separate from this choice.

Then write them into `deploy/.env` (gitignored — every script and Terraform module reads it):

```bash
PROJECT=<their project>
GOOGLE_CLOUD_PROJECT=<their project>
REGION=<their region>
RAG_LOCATION=<their region>      # RAG is regional — never "global"
TELEMETRY=on                     # traces ARE the demo (on by default; do not set to off)
TASK_STORE_KEY=$(openssl rand -hex 24)   # gates the app's public task-store endpoints
```

Confirm the project back to the user before the first `gcloud` command that creates anything.

## The deploy order is CIRCULAR — this is the part people get wrong

- `deploy_agents_a2a.py` resolves **`TASK_STORE_URL` from the APP's Cloud Run URL** (the app
  hosts the shared A2A task store).
- The **app** needs the **engines'** A2A URLs (from `deploy/agent_identities.json`).
- `grant_agent_iam.sh` needs the **app's URL** to register it as an egress destination
  (`gcp-vibeflix-app`) so the engines are *allowed* to reach the task store at all.

So the engines must be deployed **twice**. That is not a mistake — it is the shape of the
dependency. Follow this order exactly:

| # | do | why |
|---|---|---|
| 1 | foundations: Firestore (+seed), Pub/Sub, RAG corpus | everything below reads them |
| 2 | 3 MCP servers → Cloud Run | agents need their URLs |
| 3 | **engines, pass 1** (`deploy_agents_a2a.py`, no args) | creates the engines + their **agent identities** |
| 3e | `collect_agent_identities.py` | writes `agent_identities.json` (the principals every grant keys off) |
| 4 | **app** → Cloud Run | now it has the engines' A2A URLs |
| 5 | `setup_gateway.sh` → ends by calling `grant_agent_iam.sh` | registry + gateway + **all** grants, incl. registering the app for task-store egress |
| 6 | **engines, pass 2** (`deploy_agents_a2a.py`, no args) | NOW `TASK_STORE_URL` resolves → the **shared task store** activates |
| 7 | `tests/a2a/run_layers.sh` | verify all 4 layers from the BACKEND's logs |

If you skip pass 2, everything still "works" — but each engine silently falls back to a
**per-replica** in-memory task store and ~87% of task polls 404. You will see
`[task-store] … FAILED … falling back to the per-replica store` in the engine logs.

## Non-negotiable rules (each of these cost hours)

1. **⛔ NEVER DELETE AN ENGINE.** The engine id is baked into its
   `principal://…/reasoningEngines/<ID>`. Redeploying the same display name **updates in
   place** and keeps the id. Delete + recreate ⇒ new principal ⇒ **every IAM grant and
   registry endpoint silently points at a dead principal**, while the console still looks
   correct. If it happens: re-run `collect_agent_identities.py`, then `grant_agent_iam.sh`,
   then re-point the registry endpoints.

2. **Deploy engines SERIALLY.** One process (`deploy_agents_a2a.py` with no args). Parallel
   processes race on the vendored `vibeflix_common/` dir and a deploy fails **silently**,
   leaving that engine on its OLD code.

3. **The app MUST be `--min-instances=1 --max-instances=1`.** This is correctness, not cost
   control. The task store is a dict in the app process — a second instance splits it and
   rebuilds the very bug the store exists to kill. It also keeps the Pub/Sub mesh
   subscription on a single consumer (a subscription is a *competing-consumer* queue; 2+
   instances split the telemetry and the console's workflow graph renders only partially).

4. **⏱️ Wait 2–5 minutes after any registry/IAM change before judging it.** Propagation is
   not instant. A correct fix was discarded twice for being tested ~40s in and seeing a 403.

5. **NEVER deploy while a run is in flight.** Redeploying an engine wipes its in-flight A2A
   tasks. Ask the user to confirm nothing is running.

6. **Verify from the BACKEND's log, never the agent's reply.** An agent whose toolset failed
   to load still emits a confident, clean verdict — brand_style once reported
   `status:"success"` with a plausible `checks_run` while the MCP had logged **zero**
   `CallToolRequest`. The model invented the check names.

## Verify — do not trust exit codes

A deploy can exit 0 and still be broken. After step 6, **read the state back**:

```bash
# 1. Tracing MUST be on for ALL SIX engines (it is the demo).
for ID in <the 6 engine ids>; do
  curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://$REGION-aiplatform.googleapis.com/v1beta1/projects/<PROJNUM>/locations/$REGION/reasoningEngines/$ID" \
  | python3 -c "import json,sys; kv={e['name']:e.get('value') for e in json.load(sys.stdin)['spec']['deploymentSpec'].get('env',[])}; \
print(kv.get('GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY'), kv.get('TASK_STORE_URL'), kv.get('A2A_TRACE_PROPAGATION'))"
done
# want: true  https://vibeflix-app-….run.app  on     ← for every engine

# 2. The shared task store is actually being used (not the per-replica fallback):
#    app log should show  [taskstore] CREATE <id>   and NO engine should log
#    "[task-store] … FAILED … falling back to the per-replica store"

# 3. Task polls should NOT 404 en masse. A healthy run: near-0 misses.
#    (86.8% misses ⇒ the engines are on the per-replica store ⇒ you skipped pass 2.)
```

Then run `PROJECT=$PROJECT REGION=$REGION ./tests/a2a/run_layers.sh` — it proves each of the
4 layers from the callee's own log, which is the only trustworthy evidence.

## Environment gotchas that will waste your day

- **`GOOGLE_CLOUD_LOCATION=global`** for the engines. Keep it. Pinning it to the region does
  NOT work even with the regional hosts registered and granted — the engines still 403.
  Register/grant the **global** aiplatform hosts.
- **The Agent Gateway governs HTTP egress only.** It cannot match a **gRPC channel** or a raw
  **TCP socket** to a registered endpoint. That is why mesh telemetry publishes over Pub/Sub
  **REST** (the gRPC client is refused with `403 Egress request is not authorized`, and the
  failure lands on an unread future, so it fails *silently*), and why Cloud SQL / Redis are
  unusable as a task store.
- **An AGENT_IDENTITY engine has no service account** behind the metadata server, so
  `fetch_id_token()` cannot work and the gateway does **not** inject a credential. Cloud Run
  accepts only an audience-bound OIDC **ID token**, which the engine mints by impersonating
  `MCP_INVOKER_SA`. Needs three things: the env var, `iam.serviceAccountTokenCreator` on that
  SA, **and** `iap.egressor` on `gcp-iamcredentials*` (the gateway is default-deny, so even
  the token-minting call must be allowlisted).
- **`principalSet://` grants do NOT match agent identities.** They bind without error and
  match nothing. Always use the specific `principal://`.
- **Two A2A hosts.** Engines (gateway-attached) must call the **mTLS** aiplatform host — that
  is what the registry has registered. The app (a plain SA, no client cert) must call the
  **plain** host. Get it wrong and `message:send` appears to work while every task poll 401s.
- **The app needs `roles/aiplatform.agentContextEditor`**, not just `aiplatform.user` —
  without it `GET /a2a/v1/tasks/{id}` 401s and the slow agents appear to hang forever.

## Reference

- `deploy/instruction-sre.md` — the automated route (Terraform + scripts). Follow this.
- `deploy/instruction-dev.md` — the same end state, command by command, nothing hidden.
- `deploy/README.md` — service table, env contract, observability flags.
- `topology.md` — who may call whom, and what actually enforces it (the gateway governs
  **egress only** — the app→engine hop is plain IAM, not gateway ingress).
- `tests/a2a/README.md` — the 4-layer verification harness and its testing traps.

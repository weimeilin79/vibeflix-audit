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

## STEP −1 — PREFLIGHT. Verify the toolchain before touching anything.

Have the user run (or run it yourself and report): **`./deploy/preflight.sh`**. It checks
python 3.10–3.13, gcloud (+alpha/beta, auth, ADC), terraform, jq, openssl, curl, and
`deploy/.env`. Do not proceed while it reports any `✗` — a missing tool or stale ADC quota
project silently breaks the deploy halfway.

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

## Non-negotiable rules

**Read [`deploy/docs/GOTCHAS.md`](../deploy/docs/GOTCHAS.md) — it is the single source of truth.** Every rule
there fails SILENTLY: the deploy exits 0, the console looks correct, and the mesh misbehaves in a
way that points somewhere else. The ones that will bite a fresh deploy:

| | rule |
|---|---|
| G1 | ⛔ **never delete an engine** — new id ⇒ new principal ⇒ every grant silently orphaned |
| G2 | deploy engines **serially** — parallel deploys fail *silently*, leaving OLD code |
| G3 | the engines deploy **TWICE**, with the app in between (circular dependency) |
| G4 | ⏱️ **wait 2–5 min** after any registry/IAM change before judging it |
| G5 | the app runs as **exactly one instance** — correctness, not cost |
| G6 | **tracing on for every agent** — read the flag back, never trust the exit code |
| G7 | verify from the **backend's log**, never the agent's reply |

Plus: **never deploy while a run is in flight** (it wipes in-flight A2A tasks — ask the user to
confirm nothing is running).

## Verify — do not trust exit codes

**`deploy/verify_deployment.sh` is the contract.** Read-only, ✅/❌ per check, non-zero exit on
failure — so it GATES the next step. Run the matching step number after every step, and do not
proceed past a ❌:

```bash
./deploy/verify_deployment.sh 1    # foundations: Firestore, Pub/Sub, RAG
./deploy/verify_deployment.sh 2    # MCP servers: up, anonymous=403, authed≠403
./deploy/verify_deployment.sh 3    # engines pass 1: 6 engines, AGENT IDENTITY on
./deploy/verify_deployment.sh 5    # the app: pinned 1/1, task-store gate 403/200
./deploy/verify_deployment.sh 4    # gateway: registry, policies, egress grants
./deploy/verify_deployment.sh 4s   # EVERY principal + service account + role
./deploy/verify_deployment.sh 4e   # all 6 engines attached to the gateway
./deploy/verify_deployment.sh 3b   # engines pass 2: TELEMETRY, TASK_STORE_URL, trace propagation
./deploy/verify_deployment.sh      # everything (50+ checks)
```

`3b` and `4s` are the two that catch the failures a green deploy hides — a fleet with tracing
silently off, engines silently on a per-replica task store, a missing `agentContextEditor`
(agent cannot write its own sessions → opaque `TASK_STATE_FAILED`), a missing topic-scoped
`pubsub.publisher` (mesh telemetry never leaves the engine, console graph never draws), no MCP
invoker SA (an agent identity has NO service account, so it must impersonate one to mint an
OIDC token — every MCP call 401s), or engines running as a service account instead of an agent
identity (in which case the demo is not demonstrating the thing it exists to demonstrate).

## Manual spot-checks (beyond the script)

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

## Environment gotchas

**Do not restate them here — read [`deploy/docs/GOTCHAS.md`](../deploy/docs/GOTCHAS.md).** It is the single
source of truth, and it explains each rule's *symptom* (which is the part that matters, because
they all fail silently). The ones that reliably waste a day:

- **G8** the Agent Gateway governs **HTTP egress only** — it cannot match a gRPC channel or a raw
  TCP socket, which is why Pub/Sub publishes over REST and why Cloud SQL/Redis are unusable.
- **G9** an AGENT_IDENTITY engine has **no service account** — it must impersonate `MCP_INVOKER_SA`
  to mint an OIDC token, or every MCP call 401s.
- **G10** `principalSet://` grants **match nothing** — always the specific `principal://`.
- **G11** two A2A hosts: engines use **mtls**, the app uses **plain**.
- **G12** `agentContextEditor` is required by the agents **and** the app.
- **G13** keep `GOOGLE_CLOUD_LOCATION=global` — pinning it to the region 403s the whole fleet.

## Reference

- `deploy/docs/instruction-sre.md` — the automated route (Terraform + scripts). Follow this.
- `deploy/docs/instruction-dev.md` — the same end state, command by command, nothing hidden.
- `deploy/docs/README.md` — service table, env contract, observability flags.
- `topology.md` — who may call whom, and what actually enforces it (the gateway governs
  **egress only** — the app→engine hop is plain IAM, not gateway ingress).
- `tests/a2a/README.md` — the 4-layer verification harness and its testing traps.

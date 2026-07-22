# Step 5 — The Orchestrator

You've built four specialist agents. The **orchestrator** is the coordinator that runs them
together: it reads a request, decides which specialists to invoke, runs them **in parallel**,
and assembles the result. Building it teaches how ADK expresses a multi-step process as a
**graph**, how to **fan out** to several agents at once, and why that fan-out needs a **shared
task store**.

> 💡 The orchestrator is its **own independent agent**, not a library the app imports. The app
> (Step 6) calls it over A2A exactly like any other agent — which is what makes the whole mesh
> uniformly governable later.

## 💡 Concept — the ADK graph: nodes and edges

An ADK **Workflow** is a **directed graph**. You describe *what* happens and *in what order*
with two primitives:

- a **node** — one unit of work: a function, or "run this agent";
- an **edge** — "after this node, go to that node."

You don't write control flow by hand; you declare the edges and ADK walks the graph, carrying
shared **state** from node to node.

## 📝 Look — the orchestrator's graph

Open `agents/orchestrator/agent.py` and find the `Workflow` at the bottom:

```python
root_agent = Workflow(
    name="sourcing_orchestrator",
    edges=[
        ("START", ingest),
        (ingest, dispatch),
        (dispatch, (guard_brand, guard_clearance, guard_pricing)),   # ← fan-OUT
        ((guard_brand, guard_clearance, guard_pricing), merge),      # ← join
        (merge, recovery),
        (recovery, compile_ui),
        (compile_ui, generate_report),
        (generate_report, contract_finalize),
        (contract_finalize, finalize),
    ],
)
```

Read it top to bottom: **ingest** the request → **dispatch** (decide which specialists to run)
→ run the three specialists → **merge** their reports → **recovery** (re-run any that failed) →
compile the UI → generate the report → finalize the contract. Each name is a node defined just
above with an `@node` decorator.

## 💡 Concept — fan-out (and join)

Two edges do the heavy lifting:

```python
(dispatch, (guard_brand, guard_clearance, guard_pricing))   # one node → a TUPLE of nodes
((guard_brand, guard_clearance, guard_pricing), merge)      # the tuple → one JoinNode
```

An edge from one node to a **tuple** of nodes is a **fan-out**: all three run **concurrently**.
An edge from that tuple **into a `JoinNode`** (`merge`) is the **join**: it waits for all three
to finish, then continues with their combined output. This is how the audit runs brand, vendor,
and pricing checks *at the same time* instead of one after another.

## 📝 Look — the specialists are remote agents

Each `guard_*` node runs its specialist and captures the report:

```python
await ctx.run_node(_AGENTS[agent_name], _brief_from_state(ctx))
```

`_AGENTS[...]` is a **`RemoteA2aAgent`** (built by `_remote_agent(...)`) — the ADK stand-in for
an agent running in another engine (the ones you deployed in Steps 2–4). So a single
orchestrator run fans out into **three simultaneous A2A calls** to three separate engines.

## 💡 Concept — the shared A2A task store

That fan-out is exactly where a subtle, brutal bug lives. Every A2A call is two HTTP requests:
`POST message:send` (start the task), then `GET /tasks/{id}` polled until it's done. But **Agent
Runtime runs each engine as several replicas with no session affinity** — so:

```
POST /message:send   → creates the task on replica A
GET  /tasks/{id}     → load-balanced to replica B → 404 Task not found
```

Measured on a real run: **404 on ~87% of polls.** The task lived in one replica's memory; the
poll kept hitting others. That single fact caused slow runs, thousands of "error" spans, and
phantom failure-recovery.

The fix: keep tasks **outside** the replicas in a **shared task store** that any replica can
read. In this mesh the app hosts it, **backed by Firestore** — so it's durable and every replica
sees every task. Misses drop to **0**.

## 📝 Look

Read the header of `packages/vibeflix-common/vibeflix_common/task_store.py` (or `docs/02-architecture.md` →
*the shared task store*) for the full story. The key line: the engines don't use ADK's default
in-memory task store; they're wired to a `RemoteTaskStore` that reads/writes the app's
Firestore-backed endpoints.

## 💻 Run — deploy the orchestrator

Deploy it last of the agents — it auto-discovers the three specialists' A2A URLs from
`agent_identities.json`:

```bash
.venv/bin/python deploy/deploy_agents_a2a.py orchestrator
./deploy/grant_agent_access.sh orchestrator
```

> The orchestrator reads the shared task store from the **app**, which you deploy in Step 6.
> Until then, a fan-out run falls back to per-replica memory (with a loud warning) — fine for a
> single-replica smoke test, but the real, fast, multi-replica run comes together once the app
> is up.

## 👀 Verify

```bash
./deploy/verify/step5.sh
```

It confirms the orchestrator engine is deployed with an agent identity. The end-to-end fan-out —
one request lighting up all three specialists at once — you'll run for real in Step 8, after the
app and its task store are in place.

## 💡 What you learned

- An ADK **Workflow** is a **graph** of nodes and edges; you declare the flow, ADK walks it.
- An edge to a **tuple** is a **fan-out** (parallel); a **`JoinNode`** waits for all branches.
- Fan-out over A2A needs a **shared task store** (here, Firestore-backed) or replica
  load-balancing 404s most of your polls.

**Next:** [Step 6 — UI Renderer, A2UI & the Frontend →](./06-ui-frontend.md)

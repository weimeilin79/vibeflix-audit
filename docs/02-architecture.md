# Architecture

*How the mesh is wired — the ten services, the two protocols, and what enforces the
boundaries between them.*

> This page is the **conceptual** map. For the exact security target state (who may call
> whom, and the IAM that creates each edge) see [`topology.md`](../topology.md); for the
> shared plumbing that implements all of it see
> [the `vibeflix-common` library](./03-common-lib.md); for the rules that fail silently in
> production see [`deploy/docs/GOTCHAS.md`](../deploy/docs/GOTCHAS.md).

---

## The shape in one picture

Every box below is its own container (locally) or its own managed engine (in the cloud) —
nothing is a library imported into something else. Connections are **deny-by-default**: an
edge exists only because a grant creates it.

```
                    ┌──────────── app container (:8000) ────────────┐
  browser ◄──SSE───►│  React canvas (streaming A2UI renderer)   +    │
   (live A2UI)      │  FastAPI /api/*        ⟵ THIN CLIENT           │
                    │  shared A2A task store (/api/taskstore/*)      │
                    └──────┬──────────────────────────────┬─────────┘
                      A2A  │  (direct, plain IAM)     A2A  │ (paint)
                 ┌─────────▼──────────┐             ┌──────▼──────┐
                 │    orchestrator    │             │ ui_renderer │
                 │   :8006 Workflow   │             │    :8004    │
                 └──┬────────┬──────┬─┘             │  (A2UI LLM) │
             A2A ✅ │   A2A ✅│ A2A ✅│              └─────────────┘
        ┌───────────▼─┐ ┌────▼───────────────┐ ┌────▼─────────┐
        │ brand_style │ │  vendor_clearance  │ │ deal_pricing │
        │    :8001    │ │       :8002        │ │    :8003     │
        └──────┬──────┘ └──┬──────────────┬──┘ └──────┬───────┘
               │           │              └─ A2A ✅ ─► legal (:8005)
               │           │                 (only vendor_clearance may)
        ══════ ▼ ═════════ ▼ ══ AGENT GATEWAY · mTLS/PSC · IAP (egress) ══════
               ▼           ▼                              ▼
        mcp_brand_style   mcp_licensing  ◄── mcp_market   (Cloud Run MCP servers;
                          + mcp_market                     only the invoker SA may call)
```

---

## The layers

**1. Frontend — a conversational canvas.** A Vite/React app where a user drops a product
mock-up or types an instruction. It streams the audit back over SSE and paints
**A2UI** (Agent-to-User Interface) components live — the parallel execution graph, the
forms, the final clearance report — as the mesh works.

**2. The app — a *thin client*, not the brain.** The FastAPI backend (`:8000`) does not
contain the orchestration logic. It calls the `orchestrator` over A2A exactly the way it
calls `ui_renderer` — as a peer service. Its two jobs are (a) proxying the browser and
(b) hosting the **shared A2A task store** (see below). Keeping the logic *out* of the app
is what makes the gateway's egress policies genuinely load-bearing: the orchestrator fans
out under its **own** identity, so every hop is in the governed path.

**3. The orchestrator — an independent agent.** A `:8006` ADK **Workflow** engine that
captures the request, coordinates state, and **fans out to the three domain agents** —
and it is the *only* caller of those three. It runs under its own agent identity.

**4. The domain agents — the reasoning.** Three specialists, each an independent engine:
- **`brand_style` (:8001)** — logo, fonts, hex swatches, typographical compliance.
- **`vendor_clearance` (:8002)** — exclusivity collisions, trademark/customs registration,
  marketplace leaks; recommends eligible vendors; and is the one agent that hands off to
  Legal.
- **`deal_pricing` (:8003)** — audits royalty + advance + minimum guarantee against the
  rate card via an internal `evaluate → reconcile → finalize` loop (the pricing-judgement
  story from [page 1](./01-the-story.md)).

**5. `legal` (:8005) — a standalone A2A agent.** It reconstructs an undocumented legal
workflow by reasoning (RAG) over scattered "tribal knowledge" docs, asks Vendor Clearance
for the royalty tier, asks the *human* for the safety-cert ID, and executes the contract.
In this demo only `vendor_clearance` hands off to it — **any** agent could; it just isn't
in the orchestrator's fan-out.

**6. `ui_renderer` (:8004) — the painter.** An LLM agent that turns audit results into
A2UI components. The app calls it directly, in parallel with the orchestrator.

**7. The MCP servers — the tools.** Three independent, domain-grouped
[Model Context Protocol](https://modelcontextprotocol.io) servers on Cloud Run:
- **`mcp_brand_style`** — brand-guide vision/analysis tools.
- **`mcp_licensing`** — vendor registry, exclusivity contracts, trademark records, the
  rate card (`get_license_pricing`).
- **`mcp_market`** — e-commerce leak scans, volume-cap / ledger checks, governance
  telemetry.

Wiring, verified from the code:

| Agent | MCP server(s) it calls |
|---|---|
| `brand_style` | `mcp_brand_style` |
| `vendor_clearance` | `mcp_licensing` + `mcp_market` |
| `deal_pricing` | `mcp_licensing` |
| `legal` | `mcp_licensing` |
| `orchestrator` | `mcp_licensing` (registry lookups, e.g. the trademark picker) |

---

## Two protocols, on purpose

The mesh speaks exactly two languages, and the split is deliberate:

- **A2A (Agent-to-Agent)** for *delegation* — app→orchestrator, orchestrator→domain
  agents, vendor_clearance→legal. Every A2A call is `POST message:send` followed by
  `GET /a2a/v1/tasks/{id}` polled to completion, so **the task is the unit of state** the
  whole mesh runs on.
- **MCP (streamable-HTTP)** for *tools* — an agent calling its domain server. This is the
  hop the Agent Gateway governs.

## The shared A2A task store — the one that looks broken until you see it

Agent Runtime scales each engine to several replicas **with no session affinity**, and
the A2A server's default task store is a dict **private to one replica**. So the `POST`
lands on replica *A*, the balanced `GET` hits replica *B*, and you get `404 Task not
found` on **~87% of polls** (measured: 1,228 / 1,415). That single fact was the hidden
cause of most of what *looked* broken elsewhere — slow runs, ~1,900 "error" spans, a chat
blocked for 7 minutes, `recovery` re-running agents that had never failed.

The fix: the engines keep their tasks **outside** the replicas, in a store hosted by the
app (`vibeflix_common/task_store.py` → `/api/taskstore/{id}`). Any replica can now serve
any task — misses drop to **0**, and a full audit goes **5m01s → 1m44s**.

Why hosted by the app and not the *engines* hitting a database directly: the Agent Gateway
governs **HTTP** egress and can't match a gRPC channel or a raw TCP socket, which rules out
the engines reaching Cloud SQL or Redis. The **app**, though, backs these endpoints with
**Firestore** (collection `a2a_tasks`) — so the shared store is **durable** across a restart
and no longer split-brains across app replicas (each op runs in a worker thread so the
Firestore round-trip never stalls the SSE stream). The endpoints stay gated by a shared
secret (`TASK_STORE_KEY`) because the app is deliberately public; if the app is ever
unreachable the engines degrade to per-replica memory with a loud warning rather than
failing the run. (The app is still pinned to one instance — but now for its *other*
in-memory state, not the task store.)

---

## What enforces the boundaries

Two mechanisms, both platform-level (covered in depth in
[`topology.md`](../topology.md)):

- **Per-agent Agent Identity.** Each engine runs under its own identity — no shared
  service account stands in for the mesh — so every action is attributable and every
  permission is scoped to one agent.
- **Agent Gateway, default-deny egress.** Agents can't reach the internet or each other
  freely; an agent may only reach a destination it's been explicitly granted. The
  agent→MCP hop rides **mTLS/PSC** behind IAP policies; the app→MCP read-set is **direct,
  plain IAM** (the app can't ride mTLS/PSC). Same target, two lanes — a recurring gotcha.

---

> **Next:** the deployment runbooks —
> [`deploy/docs/instruction-sre.md`](../deploy/docs/instruction-sre.md) (automated) or
> [`instruction-dev.md`](../deploy/docs/instruction-dev.md) (command by command). Read
> [`deploy/docs/GOTCHAS.md`](../deploy/docs/GOTCHAS.md) first.

# Step 0 — Introduction

## The scenario

**Vibeflix** is a streaming company, and its characters are worth far more than the shows they
came from. One of its most profitable businesses has nothing to do with streaming: it
**licenses its characters to authorized vendors** who manufacture the merchandise — vinyl
figures, apparel, statues — that fans buy.

Every deal has to be right on several axes at once: territorial rights and exclusivity,
trademark/customs, brand guidelines, pricing against a rate card, and legal contracts. Vibeflix
automated the easy, lookup-shaped parts years ago. What was left needed **human reasoning** —
and that's exactly what you'll automate in this workshop, under an **enterprise-grade security**
bar. (Full story: [`docs/01-the-story.md`](../docs/01-the-story.md).)

## What you'll build

A distributed **multi-agent mesh**: independent agents, each an expert in one part of the audit,
that call shared **tool servers** and hand work off to **each other**.

```
                         ┌──────────────┐
        you ───────────► │ orchestrator │  (Step 5 — ties it all together)
                         └──┬────┬────┬──┘
                       A2A  │    │    │  A2A
         ┌──────────────────┘    │    └──────────────────┐
         ▼                       ▼                        ▼
   ┌─────────────┐      ┌──────────────────┐       ┌──────────────┐
   │ brand_style │      │ vendor_clearance │──A2A──►│    legal     │
   │  (Step 2)   │      │    (Step 4)      │        │  (Step 4)    │
   └──────┬──────┘      └────────┬─────────┘        └──────┬───────┘
          │ MCP                  │ MCP                     │ MCP
          ▼                      ▼                         ▼
   ┌───────────────┐     ┌──────────────┐          ┌──────────────┐
   │mcp_brand_style│     │mcp_licensing │          │mcp_licensing │   ← 3 MCP tool servers
   └───────────────┘     │ + mcp_market │          └──────────────┘     (Step 1)
                         └──────────────┘
              deal_pricing (Step 3) ──MCP──► mcp_licensing
```

You'll drive it through a **console app** (Step 6) that calls the orchestrator and a UI-rendering
agent over A2A — but the heart of the system is the agent mesh above.

Two kinds of connection run this mesh, and you'll meet both:

- **A2A (Agent-to-Agent)** — one agent *delegating* to another (Steps 4–6).
- **MCP (Model Context Protocol)** — an agent calling a *tool server* (every step).

## What you'll learn

You'll build the mesh **one agent at a time**, and each step teaches a distinct idea:

1. **MCP tool servers** — why tools live *outside* the agent, and registering them in the **Agent
   Registry** so they can be discovered and governed (Step 1).
2. **Building an ADK agent** — connect it to an MCP server, serve it over **A2A**, and draw the
   line between **deterministic and non-deterministic** work (Step 2).
3. **Skills** and **loop-engineering inside a single agent** (Step 3).
4. **RAG**, **agent-to-agent handoff**, and **human-in-the-loop** (Step 4).
5. **The ADK graph** — nodes, edges, **fan-out**, and the **shared task store** (Step 5).
6. **A2UI** — an interface generated *by the agents* instead of hand-built static forms (Step 6).
7. **Enterprise governance** — per-agent **Agent Identity**, the **Agent Gateway**, and per-tool
   policies (Step 7).
8. **Observability** — distributed tracing, live telemetry, and topology (Step 8).

## How security fits in

Security isn't a bolt-on at the end — it's woven through. Each agent runs under its **own
identity** and **grants its own least-privilege access** the moment you deploy it (Steps 2–5), and
the MCP servers go into the registry up front (Step 1). Step 7 then puts the **governed gateway**
in the path and locks the whole thing down. You **build first, then govern** — and watch exactly
what each layer adds.

## The environment

- Everything runs in **your own Google Cloud project** (billing enabled).
- **Cloud Shell** is the easiest place to work — `gcloud`, `terraform`, and `python3` are
  already there. A local shell works too if you have those tools.
- You deploy **real** managed services: Cloud Run (MCP servers + the app), **Agent Runtime** (the
  agents), Firestore, Pub/Sub. Step 8 includes teardown so you don't leave anything running.

> 💡 The agent code already exists in this repo. This workshop is about **deploying it,
> understanding why it's built the way it is, and watching it run** — not typing it from
> scratch. Each step points you at the one file that carries its lesson.

**Next:** [Step 1 — Setup & foundations →](./01-setup.md)

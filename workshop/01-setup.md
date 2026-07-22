# Step 1 — Setup & Foundations

In this step you stand up everything the agents will need: the shared cloud plumbing, and the
**three MCP tool servers**. It's a single script — the interesting part is understanding *what*
it created and *why* MCP servers exist at all.

## 💡 Concept — MCP: the agents' tools live in their own servers

An agent's "tools" (look up a vendor, price a deal, check a brand rule) don't live *inside* the
agent. They live in separate **MCP (Model Context Protocol)** servers — small web services the
agent calls over HTTP. Vibeflix has three, grouped by domain:

| MCP server | What it does |
|---|---|
| `mcp_brand_style` | brand-compliance checks (typography, approved medium, asset source) |
| `mcp_licensing` | vendor registry, exclusivity contracts, trademark records, the **rate card** |
| `mcp_market` | e-commerce leak scans, volume-cap checks |

Why separate them from the agent? Three reasons you'll see pay off later:

- **They're deterministic.** A tool that checks "is this font approved?" gives the *same answer
  every time*. Keeping it out of the model means the model can't hallucinate the result — a
  theme that dominates Step 2.
- **They're reusable.** Any agent (or several) can call the same server.
- **They're independently deployable and secured.** Each is its own IAM-gated Cloud Run service.

## 💡 Concept — the Agent Registry: making the MCP servers discoverable and governable

A tool server is only useful if agents can *find* it and the platform can *govern* it. That's the
**Agent Registry** — a catalog of the callable things in your system (tool servers now; agents
later). Registering each MCP server publishes its **tool spec** (what tools it offers) and its
**interface URL** so agents can discover it.

It's also the foundation of the mesh's security. Think of the registry as the set of **permitted
endpoints** — the destinations the system is allowed to reach. When an agent reaches for one, that
call is checked against the registry: if the endpoint is registered, it passes, and the agent can
be granted access to it. So registering the MCP servers here is what lets agents be given access
to them safely — only the endpoints on the list, and nothing else. Setup registers the three MCP
servers for you; the agents get registered as they're built.

## 💻 Run — configure the project

Create your environment file and set your project + region:

```bash
cp deploy/.env.example deploy/.env
# edit deploy/.env — set at least:
#   PROJECT=<your-project-id>
#   REGION=us-central1
#   TASK_STORE_KEY=$(openssl rand -hex 24)
# On a fresh project, LEAVE the bucket vars unset (project-prefixed defaults are used).
```

## 💻 Run — one command for the foundations + all 3 MCP servers

```bash
./workshop/setup.sh
```

This runs, in order: **preflight** (checks your tools) → Python **venv + deps** → **enable
APIs** → **foundations** (a Terraform module that creates the container-image registry + the
telemetry topic) → **buckets** → **Firestore** (creates the database and seeds the registries
the MCP servers read) → **Pub/Sub** → **builds and deploys the 3 MCP servers to Cloud Run** →
**registers the 3 MCP servers in the Agent Registry**.

Step 1 stays purely **foundations + MCP** — no agent identity or IAM here. Each agent grants its
own access when you deploy it (Steps 2–5), and the governing gateway comes in Step 7.

It's idempotent — if a step fails (usually a missing API or permission), fix it and re-run;
completed steps are skipped.

## 👀 Verify — the MCP servers are up *and* locked down

```bash
./deploy/verify/step1.sh
```

It confirms the Artifact Registry repo, the telemetry topic, the Firestore database, and — the
important part — that **all three MCP servers are up *and* IAM-gated**: an anonymous call to each
is refused with **403**. That 403 is the point: even the tool servers are closed by default.
(Want to see it yourself? `curl -s -o /dev/null -w "%{http_code}\n" -X POST "<mcp-url>/mcp"`
returns `403` with no auth header.)

## 💡 What just happened

You now have the mesh's foundation: three deterministic, IAM-gated tool servers **registered in
the Agent Registry**, a seeded database, a telemetry topic, and an image registry. No agents, no
agent IAM yet — Step 1 is deliberately just foundations + MCP. That's next: in Step 2 you'll
build the first agent, connect it to `mcp_brand_style`, and grant it its own access.

**Next:** [Step 2 — The Brand Style agent →](./02-brand-style.md)

---
id: vibeflix-wing-c
authors: Christina Lin
description: Build a secured, distributed multi-agent system on Google Cloud — ADK agents, MCP tool servers, and Agent Platform governance (Agent Runtime, Identity, Gateway, Registry) — one agent at a time.
keywords: docType:Codelab,category:AiAndMachineLearning,product:Antigravity,product:GeminiEnterpriseAgentPlatform,product:AgentDevelopmentKit
layout: paginated

---

# Agentic Workflow and Governance

## Introduction

### The scenario

**Vibeflix** is a streaming company, and like every studio that builds a fandom, its catalogue of characters is worth far more than the shows they came from. A green baby alien, a plucky droid,
a monster who learned to bake. Fans will *buy* them. That's a whole business, and it has almost nothing to do with streaming. Vibeflix **licenses its characters to authorized vendors**. These are factories and brands around the world who manufacture the merchandise fans take home, the vinyl figures, the apparel, the resin statues, the blind boxes.


#### Why it's deceptively hard

A single licensing deal has to be correct on several axes at once, and each is its own discipline:

- **Territory & exclusivity.** Rights are carved up by region, and an exclusive partner may hold a *territory lock* on a character. Grant a second vendor the same character in the same market and you've breached a contract you signed years ago — and won't find out until legal does.
- **Trademark & customs.** The mark has to be registered and recorded for *those goods* in *that territory*, or the shipment gets stopped at a border.
- **Branding.** The vendor's mock-up either honours the brand guide — the exact logo, the approved typography, the licensed medium — or it doesn't.
- **Pricing.** Every deal is a negotiated stack of royalty rate, advance, and minimum guarantee, measured against a rate card that bends by volume tier, product category, and territory.
- **Legal.** License amendments, safety certifications, HS/customs codes, product-liability insurance — and, finally, an executed contract.

For years, a room full of works made every one of these calls by hand. The licensing org automated the parts that could be automated — territory collisions, trademark lookups, marketplace-leak scans, brand-guide checks now run in seconds instead of days. But automation hit a wall exactly where the work stopped being *lookup* and started being *judgement*.

#### Where the humans couldn't be replaced

Take the Deal Pricing desk. Checking a royalty rate against a rate card is easy. Deciding whether a *discount* is legitimate is not.

Here's the kind of call that used to sit with a person. A vinyl-figure vendor agrees to a **10% royalty** and justifies it as a "high-volume discount." The rate card's base is **12%**. The discount is only for vendors in the right band. The 10% tier starts at **50,000 units a year**, and this vendor projects **30,000**. So the discount they're claiming doesn't apply to *them*; the deal is underpriced by two points, and the verdict is **NEEDS-ADJUSTMENT**. The arithmetic was never in question; the judgement sat in testing the claimed factor against the tier the vendor actually qualifies for — the kind of call you'll teach an agent to make when you build the **Deal Pricing** agent.

#### The knowledge that walked out the door

Pricing at least had a rate card. Other desks had *less* — and the clearest case is Legal.

Because of when and how the department grew up, Legal's real end-to-end process was never written down *as a process*. It survives as **tribal knowledge**: a handful of scattered, contradictory
files left behind by people who have since moved on. The "documentation" is a departing engineer's handoff dump — literally named `legal-stuff-dont-lose-this.txt` — that opens with *"Nobody ever wrote down the real end-to-end legal workflow, so here it is from memory before it walks out the door with me."* It's a `#licensing-ops` Slack export where the process is reconstructed live in chat (*"and where do i get the vendor's tier?" … "i just keep it in my own checklist at this point." "same. that's the problem."*). It's a rate card marked **Version 3** with a note that Version 2 is *"still floating around in email — ignore it,"* and a 2019 SOP that is simply **wrong** about the insurance amount.

Buried in that mess is a rule that keeps breaking onboardings: a contract **cannot execute** until a human supplies a safety-certification ID that lives in *no* record — the question has to travel all the way up to whoever started the audit, and the answer has to come back down. Everyone forgot it existed; everyone kept a private checklist. Rebuilding a defensible process out of that chaos — *without* hard-coding a workflow nobody agrees on — is exactly what you'll do when you build the **Legal** agent.

#### Security isn't a coat of paint

Vibeflix required it's system held to an **enterprise-grade security bar**. Every agent should not share service account, so every action is attributable and every permission is scoped to the one agent that needs it. Egress is **deny-by-default**: an agent can only reach a destination it's been explicitly granted, enforced by a governed gateway in the path of every call. A compromised component can't quietly become the whole system. You'll build the mesh first and then lock it down this way in the **governance** step — and watch exactly what each layer adds.


**Vibeflix already automated the easy parts of IP licensing. This workshop automates the parts that still needed a human to *reason* — pricing judgement and undocumented legal process — and does it under real, least-privilege security.**


### What you'll build

A distributed **multi-agent mesh**: independent agents, each an expert in one part of the audit, that call shared **tool servers** and hand work off to **each other**.

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

You'll drive it through a **console app**  that calls the orchestrator and a UI-rendering
agent over A2A — but the heart of the system is the agent mesh above.

Two kinds of connection run this mesh, and you'll meet both:

- **A2A (Agent-to-Agent)** — one agent *delegating* to another (Steps 4–6).
- **MCP (Model Context Protocol)** — an agent calling a *tool server* (every step).

### What you'll learn

You'll build the mesh **one agent at a time**, and each step teaches a distinct idea:

1. **MCP tool servers** — why tools live *outside* the agent, and registering them in the **Agent Registry** so they can be discovered and governed.
2. **Building an ADK agent** — connect it to an MCP server, serve it over **A2A**, and draw the line between **deterministic and non-deterministic** work.
3. **Skills** and **loop-engineering inside a single agent**.
4. **RAG**, **agent-to-agent handoff**, and **human-in-the-loop**.
5. **The ADK graph** — nodes, edges, **fan-out**, and the **shared task store**.
6. **A2UI** — an interface generated *by the agents* instead of hand-built static forms.
7. **Enterprise governance** — per-agent **Agent Identity**, the **Agent Gateway**, and per-tool policies.
8. **Observability** — distributed tracing, live telemetry, and topology.

### How security fits in

Security is woven through the whole build. Each agent runs under its **own
identity** and **grants its own least-privilege access** the moment you deploy it (Steps 2–5), and
the MCP servers go into the registry up front (Step 1). Step 7 then puts the **governed gateway**
in the path and locks the whole thing down. You **build first, then govern** — and watch exactly
what each layer adds.

### The environment

- Everything runs in **your own Google Cloud project** (billing enabled).
- **Cloud Shell** is the easiest place to work — `gcloud` and `python3` are
  already there. A local shell works too if you have those tools.
- You deploy **real** managed services: Cloud Run (MCP servers + the app), **Agent Runtime** (the
  agents), Firestore, Pub/Sub. Step 8 includes teardown so you don't leave anything running.

> 💡 The agent code already exists in this repo. This workshop is about **deploying it,
> understanding why it's built the way it is, and watching it run**. You won't type agents from
> scratch — each step points you at the one file that carries its lesson.


## Setup & Foundations

In this step you stand up everything the agents will need: the shared cloud plumbing, and the **three MCP tool servers**. It's a single script — the interesting part is understanding *what* it created and *why* MCP servers exist at all.

### 💡 Concept — the foundations: one database, some buckets, an image registry

Before any agent or tool exists, the mesh needs somewhere to keep its **data**, its **files**, and its **container images**. The setup script provisions three things.

**A document database (Firestore).** A production licensing system might spread its data across a relational database, a search index, a cache, and more. To keep this workshop about *agents* and not about plumbing, we use a single **NoSQL document database — Firestore** as the one place everything lives, and we **seed it** up front. It holds:

- **The rules the agents reason against** — the reference registries the MCP tool servers read: approved brand terms, typography and approved printed-media lists, and approved asset sources (`brand_style_registry`); exclusivity contracts and trademark records,  e.g. *Liberty Figure Works holds the exclusive rights to vinyl figures in North America* (`legal_registry`); and the sourcing / volume caps.
- **The vendor registry** (`vendors`) — the manufacturers themselves, which the agents look up and, on onboarding, create and update.
- **The audit history** (`audit_history`) — one document per completed audit, written by the app and shown in the console's history tab.
- **The shared task state** (`a2a_tasks`) — the A2A task store the whole mesh coordinates on (you'll meet this in the Orchestrator step).

Seeding puts the demo's reference data — vendors, exclusivity, trademarks, caps — in place so the agents have something real to reason about.

**Object storage (Cloud Storage buckets).** Two things go in the buckets: one for the **product mock-ups vendors submit** — the artwork that needs approval and one for the **approved brand assets** the audit checks against.

**A container-image registry (Artifact Registry).** Every service you deploy, the three MCP servers and the console app — is built into a **container image** first. Artifact Registry is the private repository those images are pushed to and pulled from.

With the data seeded, the mock-ups staged, and a home for images, we can talk about the **tools** the agents will use to read all of it — which is where MCP comes in.

### 💡 Concept — MCP: the agents' tools live in their own servers

An agent's "tools" (look up a vendor, price a deal, check a brand rule) don't live *inside* the agent. They live in separate **MCP (Model Context Protocol)** servers — small web services the agent calls over HTTP. Vibeflix has three, grouped by domain:

| MCP server | What it does |
|---|---|
| `mcp_brand_style` | brand-compliance checks (typography, approved medium, asset source) |
| `mcp_licensing` | vendor registry, exclusivity contracts, trademark records, the **rate card** |
| `mcp_market` | e-commerce leak scans, volume-cap checks |

Why separate them from the agent? Three reasons you'll see pay off later:

- **They're deterministic.** A tool that checks "is this font approved?" gives the *same answer every time*. Keeping it out of the model means the model can't hallucinate the result.
- **They're reusable.** Any agent (or several) can call the same server.
- **They're independently deployable and secured.** Each is its own IAM-gated Cloud Run service.

### 💡 Concept — the Agent Registry: making the MCP servers discoverable and governable

A tool server is only useful if agents can *find* it and the platform can *govern* it. 
That's the **Agent Registry** — a catalog of the callable things in your system (tool servers now; agents later). Registering each MCP server publishes its **tool spec** (what tools it offers) and its **interface URL** so agents can discover it.

It's also the foundation of the mesh's security. Think of the registry as the set of **permitted endpoints** — the destinations the system is allowed to reach. When an agent reaches for one, that call is checked against the registry, if the endpoint is registered, it passes, and the agent can be granted access to it. So registering the MCP servers here is what lets agents be given access to them safely — only the endpoints on the list, and nothing else. Setup registers the three MCP servers for you; the agents get registered as they're built.

### 💻 Open Cloud Shell

Everything in this workshop runs in **Cloud Shell**, which already has `gcloud`, `python3`, and `git` installed. (It no longer ships `terraform` — `init.sh` installs that for you in a moment.)

👉 In the [Google Cloud console](https://console.cloud.google.com), click **Activate Cloud Shell** — the terminal-shaped icon at the top right. A terminal opens along the bottom of the page.

👉💻 Confirm you're authenticated and pointed at a project:

```
gcloud auth list
gcloud config get-value project
```

Your account should show as `ACTIVE`, and the project should be your project id.

### 💻 Get the code

Clone the workshop repository:

```bash
git clone https://github.com/weimeilin79/vibeflix-audit
cd vibeflix-audit
```

### Understanding the project structure

Before building anything, take a minute on the repo layout so you know where things live:

```
vibeflix-audit/
├── agents/          # the 6 ADK agents (brand_style, deal_pricing, vendor_clearance, legal, orchestrator, ui_renderer)
├── mcp_servers/     # the 3 MCP tool servers (mcp_brand_style, mcp_licensing, mcp_market)
├── packages/        # vibeflix_common — shared helpers, in 4 subpackages named for who imports them:
│                    #   a2a/ (transport)  agent/ (ADK building blocks)
│                    #   mcpserver/ (MCP-only)  platform/ (auth, telemetry — used by both)
├── deploy/          # deploy + verify scripts, Terraform modules, and your .env
│   └── verify/      # the per-step verify scripts (step1.sh … step8.sh)
├── frontend/        # the React console (the A2UI renderer)
└── resource/        # seed data, including the legal "tribal knowledge" docs

```

You'll mostly **read** `agents/` and `mcp_servers/` to understand each piece, and **run** scripts from `deploy/`.

### 💻 Set your project

Point gcloud at your project, and capture its id and number for later commands:

```
cd ~/vibeflix-audit
source ./env.sh
gcloud config set project YOUR_PROJECT_ID --quiet
export PROJECT_ID=$(gcloud config get-value project)
export PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
```
*(`init.sh`, next, also picks up your project id automatically — from `~/project_id.txt` if your lab provides one, otherwise from gcloud or a prompt — so you can skip the manual set above if you prefer.)*


### 💻 Initialize your environment

Run the init script. It does the whole "get ready" step for you:

- **checks your environment first** — every CLI the workshop needs (`gcloud` + its alpha/beta components, `python3`, `jq`, `curl`, `unzip`, `openssl`, `git`), that you're authenticated, and that application-default credentials exist. If something's missing it stops *before* creating anything, so you fix one thing and re-run.
- points gcloud at your project (prompting for the id if it isn't set yet)
- creates the Python virtual environment `.venv` and installs every dependency — the agent requirements, the legal-RAG and deploy requirements, and the shared `vibeflix-common` package
- installs `terraform` into `~/bin` if Cloud Shell doesn't have a working one (it ships a placeholder that only prints install instructions)
- writes `deploy/.env` — the config file every workshop script reads — with your project, a default region of `us-central1`, and a freshly generated `TASK_STORE_KEY`

```
cd ~/vibeflix-audit
./init.sh
```

Enter your Google Cloud Project ID if it prompts you. It takes a few minutes, most of it installing Python packages.

> 🔁 **Every script in this workshop is safe to re-run.** If one stops on an error, fix what it
> reports and run the same command again — completed work is detected and skipped, not repeated.
> That applies to `init.sh`, `setup.sh`, and each `deploy/` script behind them.

Re-running is safe: it reuses an existing `.venv` and terraform, and won't overwrite an existing `deploy/.env`.

### 💻 Prepare your shell — `source ./env.sh`

Every step below that runs `python` or `adk` starts with one line:

```bash
cd ~/vibeflix-audit
source ./env.sh
```

It points **this shell** at the project's virtual environment and exports what the scripts and
agents read — `PROJECT_ID`, `PROJECT_NUMBER`, `REGION`, and the Vertex AI settings.

👉 **Run it once in every terminal tab you open** — after `cd ~/vibeflix-audit`, since a new tab
starts in your home directory, not the repo. Each Cloud Shell tab starts clean, so a tab
that hasn't sourced it will run Cloud Shell's *system* Python instead of the project's. That
Python has a different, incompatible set of Google libraries, and the failure looks like a
mysterious `ImportError` deep inside a library — not like "you used the wrong Python."

Sourcing it twice does no harm, so every code block below includes the line and each one is
safe to copy-paste on its own.

> Note the `source`. Running `./env.sh` instead does nothing useful — a script can't change the
> shell that launched it, which is why this one is *sourced* rather than executed. It will tell
> you if you get it the wrong way round.

### 💻 Setup the foundations + all 3 MCP servers

```bash
cd ~/vibeflix-audit
source ./env.sh
./workshop/setup.sh
```

`setup.sh` turns on everything it uses (Firestore, Cloud Run, Artifact Registry, Cloud Build, Pub/Sub, Vertex AI, and the Agent Platform services) as its first step.

This runs, in order: **preflight** (checks your tools) → **enable APIs** → **foundations** (a Terraform module that creates the container-image registry + the telemetry topic) → **buckets** → **Firestore** (creates the database and seeds the registries the MCP servers read) → **Pub/Sub** → **builds and deploys the 3 MCP servers to Cloud Run** → **registers the 3 MCP servers in the Agent Registry**.


It's idempotent — if a step fails (usually a missing API or permission), fix it and re-run, completed steps are skipped.

### 👀 Verify the MCP servers are up *and* locked down

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step1.sh
```

This confirms the Artifact Registry repo, the telemetry topic, the Firestore database, and **all three MCP servers are up *and* IAM-gated** (It should return **403**). 

> 🩹 **If you see a `✗`, just run `./workshop/setup.sh` again.** That's the repair command for
> every step in this workshop — it re-checks all nine steps, skips what already exists, and
> redoes only what's missing. It re-builds the container images as it goes, so give it a few
> minutes. Then re-run the verify script.
>
> You'll need it occasionally because these are **real cloud APIs**, and they sometimes fail for
> reasons that have nothing to do with you — a preview API can return a transient
> `code: 13 INTERNAL`. Setup retries those automatically and stops with a clear error if the
> retries don't help, so a `✗` is a to-do, not a broken lab.

You now have the mesh's foundation: three deterministic, IAM-gated tool servers **registered in the Agent Registry**, a seeded database, a telemetry topic, and an image registry. 
Next, you'll build the first agent, connect it to `mcp_brand_style`, and grant it its own access.

## The Brand Style Agent

Your first agent looks at a product mock-up and decides whether it follows Vibeflix's brand rules.

Today, that job starts with a **intern**. Whoever submits the mock-up has to *scan the image by eye*: read off the printed text, identify the product medium, and type those into the compliance check. The check itself is exact and already automated; the slow, manual part is a human doing the **looking** and the **typing**.

This agent automates that human step with an **Agent**. Its vision reads the mock-up and fills in the very inputs the intern used to type — then hands them to the same checks. Building it teaches the single most important idea in agent design: **which work should the model do, and which work should it *not* do.**

### 💡 Concept — deterministic vs non-deterministic work

Two kinds of work happen in a brand review:

- **Non-deterministic** — *looking at the mock-up* and reading what's on it: the printed text, the product medium. This is judgment. Ask two people (or run a model twice) and you might get slightly different words. It's fuzzy, and it's exactly what a language model with **vision** is good at.
- **Deterministic** — *checking those facts against the rules*: "is this font on the approved list?", "is this medium allowed?". Given the same inputs, the answer is always the same. It's a lookup, and a model should **never** be the thing that decides it — it would occasionally make the answer up.

#### The "intern" story

This is how the work used to happen at Vibeflix, and it's the whole lesson in one picture:

```
  BEFORE (manual)                          NOW (agent + MCP)
  ┌───────────────────────────┐            ┌───────────────────────────┐
  │ a coordinator/intern:     │            │ the AGENT (model + vision):│
  │  • eyeballs the mock-up    │  ───────►  │  • reads text + medium     │  ← non-deterministic
  │  • TYPES the text + medium │            │    from the image itself   │
  │    into the check tool     │            │  • calls the check tool    │
  └─────────────┬─────────────┘            └─────────────┬─────────────┘
                │ runs                                    │ calls (automated)
                ▼                                         ▼
  ┌───────────────────────────┐            ┌───────────────────────────┐
  │ the verification checks    │  (same)    │ the MCP server            │  ← deterministic
  │ (typography, medium, …)    │  ═══════►  │  run_brand_audit(...)      │
  └───────────────────────────┘            └───────────────────────────┘
```

The **deterministic checks already existed** — they were the intern's verification tool. Today that tool *is the MCP server*. The only thing the intern actually added was **reading the image and typing the inputs**. Connect an agent to the MCP, and the agent's vision does that reading automatically. **Same deterministic tool — now a model feeds it the inputs the human used to type.**

### 📝 The tool signature *is* the intern's form

Open `mcp_servers/mcp_brand_style/server.py` and find the one tool it exposes:

```python
@mcp.tool()
def run_brand_audit(text: str, medium: str, image_uri: str) -> str:
    """... The agent extracts the inputs and calls this once — it does NOT
    orchestrate the individual checks."""
```

Those three parameters — `text`, `medium`, `image_uri` — **are the intern's form.** Everything inside `run_brand_audit` (the typography check, the approved-medium check, the asset-source gate) is pure deterministic Python. No model, no guessing.

### 💡 A quick tour of ADK

Every agent in this workshop is built with **Google's Agent Development Kit (ADK)**, the open-source framework for defining agents and deploying them to Agent Runtime. A handful of building blocks recur from here on, so it's worth naming them:

- **`LlmAgent`** — the basic agent: a model, an instruction, and a set of tools. (Multi-step agents use **`Workflow`**, a graph of nodes — you'll meet it in Deal Pricing and the Orchestrator.)
- **Tools** — what the agent can *do*. Here that's the MCP `run_brand_audit`.
- **Skills** — a versioned, written procedure the agent follows (a `SKILL.md`), so its steps are repeatable.
- **`output_schema`** — a Pydantic model the agent's final answer *must* fill, so downstream code always gets structured JSON.
- **Callbacks** — hooks that run **your own deterministic code** at fixed points around the model. A **`before_model_callback`** runs *before* the model is called, and can short-circuit it entirely; an **`after_model_callback`** runs *after*, and can inspect or rewrite what the model produced. Callbacks are where you enforce the rules a model shouldn't be trusted with — and brand_style leans on all of them.

### 📝 Inside `agents/brand_style/agent.py`

Now open `agents/brand_style/agent.py`. The agent is a single `LlmAgent`, and its shape tells the whole story.

Its docstring states the division plainly:

> "The agent does the EXTRACTION (reading the artwork's printed text and product medium, using its own multimodal vision); the MCP server is the deterministic auditor."

**One `output_schema` — `BrandStyleReport` — covers every outcome.** The agent must always return that Pydantic model: a `status` (`compliant` / `flagged` / `rejected` / `needs_input` / `error`), the `extracted` text and medium it read from the image, the `checks_run`, any `findings`, and a `question` when it needs something from the user. Because the shape is fixed, the orchestrator and the UI consume it without ever parsing prose.

**Three callbacks enforce what the model can't be trusted to do** — the ADK callback concept in action:

- **`before_model_callback` → `require_image_before_model`** — a deterministic guard. If the request carries no real image, it returns `needs_input` *without ever calling the model*, so the model can't hallucinate an extraction out of nothing.
- **`before_model_callback` → `make_toolset_health_guard(...)`** — fails **closed**. If the MCP tool can't be reached, it returns `status: "error"` up front, which stops the model from inventing a clean `findings: []` "compliant" verdict for an audit that never ran.
- **`after_model_callback` → `make_schema_guard(...)`** — a safety net. If the model ever answers in prose, this rewrites the reply into a valid `needs_input` report, so the run completes even though the schema was missed.

The pattern to notice: the model does one fuzzy thing (read the image), and deterministic callbacks stand guard on both sides of it.

### Build & deploy brand_style

The deploy script finds the MCP server URLs for you, so deploying your first agent is two commands:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py brand_style
python deploy/collect_agent_identities.py
```

The first packages the agent folder, deploys it to **Agent Runtime** as its own engine that serves A2A automatically, and turns on its **agent identity**.

> ⏱️ **This takes a few minutes — don't sit and watch it.** The deploy packages your agent code,
> uploads it, and builds it into an engine in the cloud. Leave it running in this tab and skip
> ahead to **💻 Try it in the ADK Dev UI**, a couple of sections below: that part runs entirely
> on your own machine and needs nothing from this deploy. Come back to this tab when the two
> commands have finished, then carry on with **💻 Grant the agent its own access**.

### 💡 Concept — `agent_identities.json`, the mesh's address book

The second command is the one worth understanding, because everything after it depends on the file it writes.

Deploying an agent produces two facts that **only exist after the deploy**, and that nobody can predict beforehand:

- **where it lives** — its engine id, minted by Agent Runtime
- **who it is** — its *identity principal*, the first-class identity it runs as

`collect_agent_identities.py` asks Vertex AI for every `vibeflix-*` engine in your project and records both, one entry per agent:

```json
{
  "vibeflix-brand-style": {
    "engine":    "projects/<YOUR_PROJECT_NUMBER>/locations/us-central1/reasoningEngines/1234…",
    "principal": "principal://…/reasoningEngines/1234…"
  }
}
```

That file is how the rest of the workshop finds things:

| who reads it | what it needs |
|---|---|
| `grant_agent_access.sh` | the **principal**, to grant roles to the right identity |
| the next agent you deploy | the **engine** of its peers, to build its A2A URLs |
| `setup_gateway.sh registry` | the **engine**, to register each agent as a callable destination |
| you, in a moment | the **engine**, to talk to your agent directly |

So it's regenerated after **every** deploy: a fact that didn't exist a minute ago now has to be written down for the next step to use.

This is also why deploying is a *two-pass* affair later in the workshop: agents that call each
other can't all know each other's addresses on the first pass, because the addresses don't exist
yet. Deploy, collect, deploy again.

### 💻  Grant the agent its own access

The engine exists now, but its identity can do nothing at all. This grants it exactly what it needs:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh brand-style
```

**Who can now reach what.** Two different things get granted, and they work differently.

**1 — What the agent itself may do.** These roles go on `vibeflix-brand-style`'s *own* principal, nobody else's:

| role | what it buys |
|---|---|
| `aiplatform.user` | call Gemini — without it the agent can't think |
| `aiplatform.agentContextEditor` | write its **own** sessions. Miss this one and every task poll 401s and the agent hangs forever |
| `aiplatform.agentDefaultAccess` | the baseline access an engine needs to run on Agent Runtime |
| `agentregistry.viewer` | read the Agent Registry — the list of permitted destinations |
| `browser`, `serviceusage.serviceUsageConsumer` | resolve project metadata and call enabled APIs |
| `logging.logWriter`, `monitoring.metricWriter` | emit its traces and metrics |
| `pubsub.publisher` on `vibeflix-mesh-events` | publish the events that light up the live graph in Step 8 |

**2 — How it reaches the MCP servers.** This one is indirect, and the reason is worth understanding: **an agent identity is not a service account.** Cloud Run's IAM check wants an OIDC token from a service account, and an agent principal has none to offer. So there's one shared service account in the middle:

```
  vibeflix-brand-style                vibeflix-mcp-invoker            the 3 MCP servers
  (agent principal)                   (service account)               (Cloud Run, IAM-gated)
         │                                     │                              │
         │  serviceAccountTokenCreator         │  roles/run.invoker           │
         └────────── may impersonate ─────────►└────────── may call ─────────►│
```

The agent impersonates the invoker SA, mints an OIDC token with it, and calls the MCP server with that. Cloud Run sees a service account it trusts. Nothing is opened to the public — try the MCP URL yourself and you still get a **403**, exactly as in Step 1.

This is **least privilege in action**: each agent grants its *own* access as it's deployed, keyed to its *own* principal — no blanket "any agent can do anything."

> Note what is **not** granted here: this agent cannot call any *other agent*. Agent-to-agent
> egress is governed by the Agent Gateway, which you set up in Step 7. Until then, each agent can
> reach Gemini and the tool servers, and nothing else.


### 💻 Try it in the ADK Dev UI

While the cloud deploy runs, run brand_style on your machine and poke at it in **ADK's web playground**. First bring the three MCP servers up locally (they listen on `127.0.0.1:9002-9004` using your `.venv`):

👉💻 In a **second Cloud Shell tab**, start the three local MCP servers:

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh mcp
```

👉💻 In a **third Cloud Shell tab**, point the agent at the local brand-style MCP and launch the ADK Dev UI:

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/brand_style
```

You should see the server start up:

```
+-----------------------------------------------------------------------------+
| ADK Web Server started                                                       |
| For local testing, access at http://localhost:8000.                          |
+-----------------------------------------------------------------------------+
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

👉 To open the UI: click the **Web Preview** icon in the Cloud Shell toolbar (top right), choose **Change port**, set it to **8000**, and click **Change and Preview**. A new tab opens with the ADK Dev UI.

Pick **brand_style** and ask it to audit the default mock-up — for example:

> Audit `gs://<your-project>-request-image/vendor_request_refine.png` for grogu vinyl figures in NA.

Watch it read the text and medium from the image, call `run_brand_audit`, and fill in the `BrandStyleReport`:

```json
{
  "status": "compliant",
  "extracted": {
    "text": [],
    "medium": "vinyl figures",
    "image_uri": "gs://<your-project>-request-image/vendor_request_refine.png"
  },
  "checks_run": ["asset_source", "typo", "printed_medium"],
  "findings": []
}
```

**Read that reply as two halves, because it's the concept from the top of this section made concrete.**

`extracted` is the **model's** work — it looked at the artwork and reported what it saw: the medium is *vinyl figures*, and there's no printed text on this mock-up (`text: []`). Ask it twice and the wording could differ slightly. That's the non-deterministic half, and it's exactly the part the intern used to do by eye.

Everything else is the **tool's** work. `checks_run` lists the three deterministic checks the MCP server ran, in its own fixed order, and `status` is its verdict — `compliant`, `flagged`, or `rejected`. The model didn't decide that and can't override it. Same inputs, same answer, every time. `findings` is empty here because nothing failed; each failed check appends an entry naming the element, the issue type, and a severity.

> 🔎 **Try breaking it.** Change the image link to something outside your buckets — say
> `gs://some-random-bucket/x.png` — and re-run. You'll get `"status": "rejected"` with
> `checks_run: ["asset_source"]`: **only one check ran.** The asset-source gate runs first and
> short-circuits the rest, so unapproved artwork is never even inspected. That ordering is a
> policy decision baked into the tool, not something the model chose.

This local loop is the fastest way to iterate on an agent before you ship it.

👉💻 When you're finished exploring, press `Ctrl+C` in the `adk web` tab. **Leave the
`./run_local.sh mcp` tab running** — the next section drives another agent against the same three
MCP servers.


### 👀 Verify the agent extracts, then the tool decides

The cloud deploy from the *Build & deploy* step takes a few minutes. Once it reports success, verify the engine: 
```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step2.sh
```

It confirms the `brand_style` engine is deployed **with an agent identity**. To watch it actually work, talk to it directly — point it at the default mock-up and see it read the image, then call the deterministic tool:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/ask_agent.py brand-style \
  "Audit this mock-up. image: gs://${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image}/vendor_request_refine.png, character: grogu, market: NA"
```

You'll get back the same shape of report you saw in the Dev UI — this time from the deployed
engine in the cloud:

```json
→ vibeflix-brand-style  (…/7721660704905756672)
{
  "status": "flagged",
  "extracted": { "text": [], "medium": "artwork", "image_uri": "gs://…/vendor_request_refine.png" },
  "checks_run": ["asset_source", "typo", "printed_medium"],
  "findings": [
    { "element_id": "printed_medium", "issue_type": "unapproved_medium", "severity": "critical",
      "description": "Printed medium 'artwork' is not on the approved list: …" }
  ]
}
```

> 👀 **Your `status` may differ from the run above, and that's the lesson.** The agent decides
> the `medium` by *looking at the artwork* — here it said `"artwork"`, which isn't on the
> approved list, so the deterministic check flagged it. Run it again and it might say
> `"vinyl figures"` and come back `compliant`. The fuzzy half varies; the rule applied to it
> never does. A `flagged` result is the system working, not a failure.
>
> Try a bad image link and watch the **asset-source gate** reject it *before* any content check
> runs — `checks_run` will contain only `asset_source`.

> You may also see a line like `[a2a] NOT propagating: valid=False sampled=False …`. That's the
> A2A client saying it isn't attaching a trace parent to the call (there's no trace running on
> your laptop), so the engine starts its own. Expected — it's diagnostics, not an error.

### 💡 What you learned

- Tools live in an MCP server; the agent calls them.
- The model does the **fuzzy** work (understand the image); the MCP does the **exact** work (apply the rules) — and you deliberately keep the model *out* of the rule-deciding.
- An ADK agent is deployed as its own A2A-serving engine with its own identity.

## The Deal Pricing Agent

Your second agent checks the money: does the deal the vendor agreed to — the royalty, the advance, the minimum guarantee — match what Vibeflix's rate card says it should be?

Most of this is just arithmetic. Pull the vendor's numbers, pull the rate card, compare. A vendor asks for a **10% royalty**; the 10% rate only kicks in at **50,000 units a year**. They project **30,000**, so they don't qualify. That's a two-line check, and checks like that belong in a **tool**, where the answer comes out the same every single time.

So where does the agent earn its place here? In the vendor's *reason*. Vendors don't hand you a tidy "I qualify for tier 2." They argue: *"give us 10%, we do big volume, we're a premium line, and we're taking the territory nobody else wants."* Some of those are real rate-card factors (a volume tier, a category modifier), Some sound fair but aren't factors at all (loyalty, "we'll market it hard"). The agent has to read that argument, work out which real factors it's actually invoking, run each one through the deterministic tool, and decide whether what's left justifies the price. Interpreting an open-ended argument against a fixed set of rules — *that's* the part a formula can't do.

Building it teaches two ideas that shape how a *single* agent thinks: **Skills** and **loop-engineering**.

### 💡 Concept — loop-engineering inside one agent

From the outside, `deal_pricing` is one agent like `brand_style`. From the inside, it is **not** a single model call — it's a small **Workflow** with a loop:

```
START ──► evaluate ──► reconcile (LOOP) ──► finalize
```

- **evaluate** runs the pricing reasoner once and tags each part of the deal: `clear`, `unresolved`, or `discrepancy`.
- **reconcile** is the loop. While any part is still `unresolved`, it runs a second sub-agent — the **resolver** — to adjudicate that one item against the rate-card rules, then re-checks. It repeats until nothing is unresolved *or* it hits `MAX_ROUNDS = 4`, then settles the verdict.
- **finalize** emits the result.

#### Why a loop? The volume-discount case

A vendor agrees to a **10% royalty** and justifies it as a "high-volume discount." The rate card base is **12%**, and the 10% band only applies at **50,000+ units/yr**. This vendor projects **30,000**.

The reasoner can't just accept or reject that — so it marks the royalty **`unresolved`** with `claim: "volume-tier discount"`. The **loop** hands that claim to the resolver, which checks the *actual* projected volume (30k) against the tier's minimum (50k) → it doesn't qualify → the discrepancy **stands** → verdict **NEEDS-ADJUSTMENT**.

That's the shape to internalize: **a deterministic control loop (the `for` loop, the status transitions, the round cap) wrapped around non-deterministic judgment (the resolver's reasoning).** It's Step 2's lesson one level up: the loop is a deterministic frame, and the model's judgement plugs into the one spot that needs it.

### 💡 Concept — Skills: a written procedure you hand the agent

The reasoner have whole audit procedure loaded in a **Skill**.

> A **Skill** is a reusable, versioned *standard-operating-procedure* you give an agent —
> instructions + the exact tools it's allowed to use + the output it must produce.

**How a Skill works in ADK.** You load a skill from its folder and hand it to the agent through a **`SkillToolset`**:

```python
tools=[
    skill_toolset.SkillToolset(
        skills=[load_skill_from_dir(_SKILL_DIR)],               # the deal-pricing-audit SKILL.md
        additional_tools=[mcp_toolset("mcp_licensing", ...)],  # the tool the skill may call
    ),
]
```

The `SKILL.md` file *is* the procedure: **frontmatter** (`name`, `version`, `allowed-tools`) followed by a numbered set of steps and a required output shape. At run time the toolset hands the model the skill machinery (load the skill, follow its steps) and **scopes the tools** to exactly what the skill declares — so the agent runs a fixed, versioned SOP every time, using only the tools that SOP allows.

**And a Workflow ties agents together.** Deal Pricing is built as an ADK **`Workflow`** — a small directed graph. You define it by writing **nodes** (the steps) and **edges** (what follows what):

```python
root_agent = Workflow(
    name="deal_pricing",
    edges=[("START", evaluate), (evaluate, reconcile), (reconcile, finalize)],
)
```

Each node is a function decorated with `@node`, and a node can run a **sub-agent** — a full `LlmAgent` living *inside* this one engine — with `await ctx.run_node(some_agent, input)`. That's the idea to hold onto: **several agents inside a single deployed agent**, coordinated by the graph. Deal Pricing has two sub-agents you'll see next — a **reasoner** for the first pass and a **resolver** that adjudicates one disputed item at a time.

### 📝 The skill and the loop, in the code

Open `agents/deal_pricing/skills/deal-pricing-audit/SKILL.md`. It's a Markdown file with:

- **frontmatter** — `name`, `version`, and `allowed-tools: get_license_pricing` ;
- a **numbered procedure** — Step 1 pull the rate card, Step 2 read the expected deal, Step 3 classify each component, Step 4 rule the verdict;
- an **output contract** (the exact JSON shape).

Notice Step 2 of the skill: *"read the EXPECTED deal — do **NOT** compute it yourself… the tool is the single source of truth."* **That's where the skill enforces Step 2's boundary** — it tells the model to stay out of the arithmetic and defer to the deterministic `get_license_pricing` tool. The skill and the loop are co-designed: the skill *defines* the `unresolved` status, and the reconcile loop is what *consumes* it.

Now open `agents/deal_pricing/agent.py` and find the graph at the bottom:

```python
root_agent = Workflow(
    name="deal_pricing",
    edges=[("START", evaluate), (evaluate, reconcile), (reconcile, finalize)],
)
```

…and the loop inside `reconcile`:

```python
for _ in range(MAX_ROUNDS):
    unresolved = [c for c in report["components"] if c["status"] == "unresolved"]
    if not unresolved:
        break
    for c in unresolved:
        await ctx.run_node(resolver, ...)   # adjudicate ONE claim against the rules
```

Here's what the graph does, node by node — and it's really **two sub-agents coordinated by deterministic code inside one deployed engine**:

- **`evaluate`** runs the first sub-agent, the **pricing reasoner** (`await ctx.run_node(pricing_reasoner, …)`). The reasoner follows the skill: it calls `get_license_pricing` for the *expected* deal, then tags each component — royalty, advance, minimum guarantee — as `clear`, `unresolved`, or `discrepancy`.
- **`reconcile`** is the loop. For every component still `unresolved`, it runs the second sub-agent, the **resolver** (`await ctx.run_node(resolver, …)`), which judges that *one* claimed factor against the rate-card rules and returns `clear` or `discrepancy`. The loop re-checks and repeats — up to `MAX_ROUNDS = 4` — then settles the verdict (`APPROVED` / `NEEDS-ADJUSTMENT` / `UNDERPRICED`).
- **`finalize`** emits the finished `DealPricingReport`, the value the A2A caller receives.

Both sub-agents are ordinary `LlmAgent`s, but they never talk to the outside world — they exist only to be called by the Workflow's nodes. So from the outside `deal_pricing` is one agent; inside, it's a **reasoner plus a resolver driven by a deterministic loop**: judgement in the two sub-agents, control flow in the graph.


### 💻 Build & deploy deal_pricing

Same one command as before — the deploy script finds `mcp_licensing`'s URL automatically:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py deal_pricing
python deploy/collect_agent_identities.py
```

> ⏱️ **This takes a few minutes — don't sit and watch it.** The deploy packages your agent code,
> uploads it, and builds it into an engine in the cloud. Leave it running in this tab and skip
> ahead to **💻 Try it in the ADK Dev UI**, a couple of sections below: that part runs entirely
> on your own machine and needs nothing from this deploy. Come back to this tab when the two
> commands have finished, then carry on with the grant below.

Then grant it its own access (project roles on its principal + reach to the MCP servers):

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh deal-pricing
```


### 💻 Try it in the ADK Dev UI

Like brand_style, you can run deal_pricing locally and drive it from the playground.

👉💻 In a **second Cloud Shell tab**, start the three local MCP servers — skip this if they're
still running from the last section:

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh mcp
```

👉💻 In a **third Cloud Shell tab**, launch the Dev UI pointed at the local licensing MCP:

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_LICENSING_URL=http://127.0.0.1:9002/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/deal_pricing
```

Open it via **Web Preview → Change port → 8000**, pick **deal_pricing**, and paste the underpriced deal:

> Audit this deal. character: grogu, product_category: vinyl figures, territory: NA, volume: 30000, net_unit_price: 18. Agreed terms — royalty_rate: 0.10, advance: 8000, mg: 30000.

Watch the reasoner pull the expected deal, mark the royalty **unresolved**, and the **reconcile loop** reject the volume-discount claim (30k < 100k) → **NEEDS-ADJUSTMENT**. The reply is long; these are the parts that matter:

```json
{
  "agent": "deal_pricing_agent",
  "expected": { "effective_rate": 0.168, "royalty": 90720.0, "mg": 150000, "advance": 37500.0 },
  "agreed":   { "rate": 0.1, "advance": 8000, "mg": 30000 },
  "rate_card": {
    "found": true, "property": "Grogu (The Child)", "character_tier": "A-list",
    "base_royalty_rate": 0.14,
    "category_modifier":      { "vinyl figures": 1.2, "plush": 1.0, "…": "…" },
    "territory_modifier":     { "north america": 1.0, "europe": 1.05, "…": "…" },
    "volume_discount_tiers":  [ { "min_units": 0, "mult": 1.0 }, { "min_units": 100000, "mult": 0.95 } ],
    "min_royalty_rate": 0.1,
    "mg_rule":     { "pct_of_projected_royalty": 0.5, "floor_usd": 150000 },
    "advance_rule": { "pct_of_mg": 0.25 }
  },
  "components": [
    { "name": "royalty_rate", "agreed": 0.1,   "expected": 0.168,   "status": "discrepancy", "below_floor": false },
    { "name": "mg",           "agreed": 30000, "expected": 150000,  "status": "discrepancy", "below_floor": true  },
    { "name": "advance",      "agreed": 8000,  "expected": 37500.0, "status": "discrepancy", "below_floor": false }
  ],
  "verdict": "UNDERPRICED",
  "status": "blocked"
}
```

**`rate_card` is what the agent *fetched*, not what it knew.** `get_license_pricing` on `mcp_licensing` returned Grogu's card — A-list tier, a `0.14` base rate, and the modifier tables. None of it is in the prompt or in the model's head.

**`expected` is what that card computes to** for this deal: `0.14 × 1.2` (vinyl figures) `× 1.0` (North America) `× 1.0` (volume) `= 0.168`. That last multiplier is the volume-discount claim being **rejected** — the first tier that earns a discount starts at 100,000 units and this deal is 30,000, so it stays `1.0`. The arithmetic is the tool's, not the model's. This is *"defer the exact math to the tool"* from the skill, made concrete.

**`components` is the line-by-line comparison** against `agreed`, what the vendor put on the table. All three are a `discrepancy`, and `mg` also carries `below_floor: true` — 30,000 against the card's `floor_usd` of 150,000. Note that `royalty_rate` is *not* below floor: `0.10` is exactly `min_royalty_rate`, so it's legal, just far under what the card expects. "Legal" and "what we should have charged" are two different questions, and the card answers both.

**`verdict` and `status` are the tool's**, derived from those components. The model drove the loop and resolved the claims; it never picked the verdict.

> 🔎 **Try it.** Re-run with `volume: 120000`. The volume tier is now met, so `volume_mult` becomes
> `0.95` and `expected.effective_rate` drops to `0.1596` — still above the agreed `0.10`, so the
> verdict stays `UNDERPRICED`. Same graph, same skill, different arithmetic, all of it read off
> the card rather than reasoned about.

👉💻 When you're done, press `Ctrl+C` in the `adk web` tab **and in the `./run_local.sh mcp`
tab** — the next section starts the whole local mesh, which brings up its own MCP servers on the
same ports `9002-9004` and can't start while these are holding them.

### 👀 Verify and watch the loop reconcile a claim

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step3.sh
```

It confirms the `deal_pricing` engine is deployed with an agent identity. Then send it the
underpriced deal from the concept above and watch it reason:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/ask_agent.py deal-pricing \
  "Audit this deal. character: grogu, product_category: vinyl figures, territory: NA, \
volume: 30000, net_unit_price: 18. Agreed terms — royalty_rate: 0.10, advance: 8000, mg: 30000."
```

> 👀 Look for the agent to (1) pull the **expected** deal from the tool, (2) mark the royalty **unresolved** with the volume-discount claim, (3) let the **reconcile loop** reject the claim
> (30k < 100k), and (4) return a verdict — here **NEEDS-ADJUSTMENT** (or **UNDERPRICED** if a floor is breached). If it asks for a missing field, that's the agent doing input-validation, supply it and re-run.

*(The richest end-to-end pricing run comes together in Step 5, once the orchestrator feeds the
deal's fields automatically — here you're exercising the agent on its own.)*

### 💡 What you learned

- A single agent can be an internal **Workflow** with a **bounded loop** — several coordinated model calls under deterministic control.
- A **Skill** gives the model a repeatable procedure and scoped tools — and is where you write down *"defer the exact math to the tool."*
- Non-deterministic judgment (the resolver) can live *inside* a deterministic control structure.

## Vendor Clearance + Legal

Two agents this step, because they work as a pair: `vendor_clearance` checks a vendor is allowed to make the product, and when a *new* vendor/category is onboarded it hands the deal off to an independent `legal` agent to clear the paperwork and execute the contract. Building them teaches three things: **RAG**, **agent-to-agent (A2A) handoff**, and **human-in-the-loop**.

### 💡 Concept — Legal, RAG, and the tribal-knowledge problem

Most of Vibeflix's departments have a written process. Legal doesn't. Because of *when* it was built, the real end-to-end legal workflow was never documented — it survives as **tribal knowledge** in a handful of scattered, contradictory files left behind by people who've moved on. Look in `resource/legal/docs/`:

- `legal-stuff-dont-lose-this.txt` — a departing engineer's handoff dump: *"Nobody ever wrote down the real end-to-end legal workflow, so here it is from memory before it walks out the door with me."*
- `slack-export-licensing-ops.txt` — the process reconstructed live in chat.
- `royalty-rate-card.md` marked **Version 3** (*"Version 2 is still floating around in email — ignore it"*), and a **2019 SOP that is wrong** about the insurance amount.

You *cannot* hard-code a process nobody agrees on. So the legal agent **reconstructs** it with **RAG (Retrieval-Augmented Generation)**: instead of baking rules into the prompt, it *retrieves* the relevant scraps from those docs at run time and reasons over them.

> **RAG in one line:** give the model a *search tool* over your documents, so it pulls in the
> exact facts it needs instead of relying on what it happened to memorize.

**Under the hood: a managed vector search.** RAG needs somewhere to search. Vibeflix uses **Vertex AI RAG Engine**, a managed service that turns a pile of documents into a searchable knowledge base:

- **Chunking + embedding.** When you import the legal docs, RAG Engine splits each into passages and runs every passage through an **embedding model** (`text-embedding-005`), turning text into a **vector** — a list of numbers that captures its *meaning*.
- **The vector store.** Those vectors go into a **managed vector database** (Vertex Vector Search). Passages with similar meaning land as nearby vectors.
- **Retrieval.** At query time (`retrieveContexts`), your question is embedded the same way, and the store returns the passages whose vectors are **nearest** to it — a *semantic* match, so "what insurance do we need?" finds the insurance memo even if the memo never uses the word "insurance."

The payoff: the model never has to have memorized the legal process. It asks a question, gets back the three or four most relevant scraps from the actual docs, and reasons over those. "Managed" means you create a corpus, import files, and query it, with no index or database to run yourself.


### 💻 Build legal's knowledge base

Legal needs its RAG corpus first. Build it from the tribal-knowledge docs:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_legal_rag.sh
```

`setup_legal_rag.sh` runs `deploy/setup_legal_rag.py`, which does four things:

1. **Uploads** the docs in `resource/legal/docs/` to a GCS bucket — the source RAG Engine imports from.
2. **Creates (or reuses) the corpus** `vibeflix-legal-kb`, configured with the `text-embedding-005` embedding model.
3. **Imports the files** into the corpus (`import_files` from the GCS source). RAG Engine then chunks, embeds, and indexes them behind the scenes.

> ⏱️ **The import is the slow part.** When you see
> `[legal-rag] importing 10 files from gs://…/legal-docs/ …` it can sit there for a few
> minutes — RAG Engine is chunking, embedding, and indexing every document before it returns.
> It's working; let it finish.
>
> On a brand-new project you may also see
> `Vector Search permissions still propagating (attempt 1/5) — retrying in 30s…`. That's
> expected too: enabling the Vector Search API grants the RAG service agent its role, and the
> grant takes a couple of minutes to take effect. The script waits it out.

It finishes by printing your corpus id and **writing it into `deploy/.env`** for you:

```
=== Legal RAG corpus ready ===
  RAG_CORPUS=projects/<your-project-number>/locations/us-central1/ragCorpora/8061205838481588224
  RAG_LOCATION=us-central1

  ✓ saved to deploy/.env — `source ./env.sh` picks them up, and the legal
    agent gets them at deploy time. Nothing to copy.
```

Nothing to paste. The next `source ./env.sh` exports both, and when you deploy `legal` in a moment they travel with it — that's how its `search_legal_docs` tool knows which corpus to query.

### 👀 Verify the corpus actually answers

Before building anything on top of it, ask the corpus a question directly — no agent, no model,
just the RAG Engine API:

```bash
cd ~/vibeflix-audit
source ./env.sh
curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/$REGION:retrieveContexts" \
  -d "{\"vertex_rag_store\":{\"rag_resources\":{\"rag_corpus\":\"$RAG_CORPUS\"}},
       \"query\":{\"text\":\"what certifications does apparel need\",\"rag_retrieval_config\":{\"top_k\":3}}}" \
  | jq '.contexts.contexts[] | {source: .sourceDisplayName, score, text: .text[0:100]}'
```

You should get three excerpts from **three different documents** — something like:

```
{ "source": "email-thread-cert-requirements.txt",   "score": 0.3663, "text": "From: Tomás Herrera …" }
{ "source": "janes-onboarding-checklist.md",        "score": 0.3756, "text": "Jane's legal onboarding checklist …" }
{ "source": "confluence-licensing-onboarding.md",   "score": 0.3874, "text": "Licensing Legal — Vendor Onboarding …" }
```

That's the tribal-knowledge problem in one result: the answer to a single question is spread
across an email thread, someone's personal checklist, and a half-finished wiki page. **Lower
score = closer match** here.

> 🕐 **Empty result?** If `contexts` comes back empty right after the import, indexing hasn't
> caught up yet — wait a minute and run it again. It's the one case where "nothing found" doesn't
> mean "something is wrong".


### 📝 The retrieval tool

Open `agents/legal/legal_kb.py`. It exposes one FunctionTool, `search_legal_docs`, with the following backends:

- **`RAG_CORPUS` set** → Vertex AI **RAG Engine** (`:retrieveContexts`) over the corpus you built above;
- **`RAG_CORPUS` unset, or Vertex unreachable** → a local keyword search over the same files, so the agent still runs offline.

👉💻 Call the tool on its own — no agent, no model, just the function:

```bash
cd ~/vibeflix-audit
source ./env.sh
python - <<'EOF'
import sys, json
sys.path.insert(0, "agents")
from legal.legal_kb import search_legal_docs

r = json.loads(search_legal_docs("what certifications does apparel need", top_k=3))
print("retriever:", r["retriever"])
for h in r["results"]:
    print(f"  {h['score']}  {h['source']}")
EOF
```

```
retriever: vertex_rag
  0.3663  email-thread-cert-requirements.txt
  0.3756  janes-onboarding-checklist.md
  0.3874  confluence-licensing-onboarding.md
```

> 🔎 **Watch the `retriever` field — it's the whole point of running this.** That fallback above
> is deliberate (the agent shouldn't die because RAG is down), but it means a broken corpus
> doesn't *look* broken: the agent keeps answering, just from keyword matches. Run the same
> command with `RAG_CORPUS` unset and you'll see it — `retriever: local_keyword`, and the top
> hit for a certifications question becomes `logistics-hs-codes.md`. Plausible-looking, wrong,
> and no error anywhere.
>
> So whenever legal's answers seem off, check this field first. `vertex_rag` means the corpus is
> being used; `local_keyword` means it isn't, and `RAG_CORPUS` is the thing to look at.

In `agents/legal/agent.py`, `search_legal_docs` sits alongside the legal *workflow* tools (`draft_license_amendment`, `verify_certifications`, `assign_customs_hs_code`, `verify_liability_insurance`, …) and the one real side effect — `upsert_contract` (an MCP tool) that persists the executed contract. The agent uses RAG to figure out *what the process is*, then the tools to *do it*.



### 💡 Concept — A2A: handing off to a remote agent

`legal` is **its own deployed agent** — a separate engine with its own identity. `vendor_clearance` doesn't import it or contain it; it **calls it over A2A** (Agent-to-Agent), the protocol for one
agent delegating to another.

The way ADK models "an agent running somewhere else that I can call" is a **remote agent**. You hold a lightweight stand-in for the remote engine and invoke it like a local step; the call travels over A2A to the other engine and the result comes back.


**How A2A works.** A2A is a small HTTP contract every ADK agent speaks. Each agent publishes an **agent card** at a well-known URL, describing what it is and how to reach it. To call one, you `POST` a message to its `message:send` endpoint, which returns a **task id**; you then `GET .../tasks/{id}` and poll until the task is done, and read the result. The *task* is the unit of work — which is exactly why the shared task store from Step 5 matters.

**How a remote agent works in ADK.** You don't hand-write those HTTP calls. ADK gives you **`RemoteA2aAgent`**: construct it with the target's agent card, and from then on you invoke it like any local sub-agent (`ctx.run_node(remote, input)`). It makes the A2A call for you and hands you back the result. The orchestrator uses this for its fan-out. `vendor_clearance → legal` does the same thing with a direct, fresh-context call (so legal starts clean each time), but the model is identical: **treat an agent running in another engine as a step you can call.**

> ⚠️ **Two things this mesh had to add on top of stock `RemoteA2aAgent`** — you'll meet both in Step 5, and they're the kind of detail that costs a day if nobody tells you:
> - **The agent card names the wrong host.** Agent Runtime's A2A template hardcodes the *plain* `…-aiplatform.googleapis.com` host into the card each engine serves — but the Agent Gateway (Step 7) authorizes only the `.mtls` host, and refuses the plain one with `403 Egress request is not authorized`. Since every standard A2A client just follows `card.url`, you have to **build the card yourself** and point it at `.mtls`. That's what `vibeflix_common/a2a/card.py` is for.
> - **Stock sends *blocking*, not send-and-poll.** Despite A2A being a send-then-poll protocol, the stock client holds one long HTTP request open — and Agent Runtime kills that at **~180s** with `400 FAILED_PRECONDITION` *while the callee is still happily working*. Fast hops never notice; a long one fails confusingly. So hops that can run long send non-blocking and poll instead.
>
> Both are hidden inside `VibeflixRemoteA2aAgent` (`vibeflix_common/a2a/remote_agent.py`), a subclass, so every call site stays ordinary ADK. See `eng-report/UPSTREAM-FR-a2a-client-gaps.md` for the measurements.


### 📝 The handoff as its own step

Open `agents/vendor_clearance/agent.py`. It's a small Workflow:

```
START → clearance → legal_clearance → finalize
```

`legal_clearance` is a **distinct node** whose whole job is the handoff — it calls the legal engine over A2A (`LEGAL_A2A_URL` points at it) with a *fresh* context and merges legal's verdict + contract id back in. Making the handoff its own node means it shows up as its own step in the trace (you'll see this in Step 8's observability), and keeps each agent's reasoning isolated.

> 💡 The orchestrator (Step 5) uses ADK's `RemoteA2aAgent` construct for the same idea at scale.
> `vendor_clearance→legal` uses a direct, fresh-context A2A call on purpose — so legal doesn't
> receive vendor_clearance's whole conversation and echo it back.

Like Deal Pricing, `vendor_clearance` is a `Workflow` with sub-agents inside it:

```
START → clearance → legal_clearance → finalize
```

- **`clearance`** runs the **`clearance_reasoner`** sub-agent (following its skill): it checks exclusivity collisions, trademark/customs registration, and marketplace leaks, and recommends eligible vendors — producing a report with `status` `cleared` / `blocked` / `needs_input`.
- **`legal_clearance`** is the handoff node. When a new vendor/category was onboarded, it calls the **`legal`** engine over A2A. Legal may ask a question back, and this node has two ways to answer it:
  - **Flow A — an agent answers.** If legal's question is about the *vendor* (its royalty tier, its record), a second sub-agent, the **`vendor_liaison`**, answers it from the licensing registry and the loop continues — one agent answering another, no human involved.
  - **Flow B — a human answers.** If legal needs the **safety-cert ID** (which lives in no record), the node sets `status: "needs_input"` with the `question`, and it propagates up to the user — the HITL path below.
- **`finalize`** emits the merged report: the clearance verdict plus legal's executed contract id.

The `@node(..., rerun_on_resume=True)` decorators are what let the workflow *pause* on a question and *resume* once the answer arrives.


### 💡 Concept — Human-in-the-loop (HITL)

Buried in that tribal knowledge is a rule that keeps breaking onboardings: a contract **cannot execute** until a human supplies a **safety-certification ID** that lives in *no* record.
Everyone forgot it existed.

So legal implements it as **human-in-the-loop**: when it needs a value it can't find, it doesn't guess and it doesn't hard-fail — it returns a **question** and a status like `needs_user`. That question **propagates up** the call chain — legal → vendor_clearance (`status: needs_input`) → orchestrator → the app → **the person who started the audit**. Their answer comes **back down** through workflow state (`legal_safety_cert`), vendor_clearance folds it into the brief, and legal reads it and proceeds. (If no ID is ever supplied, legal issues a provisional `PROV-…` id and reports it — so onboarding is never silently blocked.)


**How HITL works in ADK.** An agent that needs something from a human returns a result that says *"I need input"* — here a `status` of `needs_user` / `needs_input` plus a `question` — and the run ends there, cleanly. The caller surfaces the question to the person. When they answer, the answer is written into the workflow's **session state** and the run is **resumed**: ADK re-executes the nodes marked `rerun_on_resume=True`, but this time the answer (`legal_safety_cert`) is already in state, so the node that was waiting reads it and continues past the question.

So a paused-for-a-human run and a normal run are the *same* workflow — the only difference is whether the needed value is in state yet. In this mesh the question and answer travel over the A2A chain (legal → vendor_clearance → orchestrator → app → user, and back), but the ADK primitive underneath is just: **return a question, resume with the answer in state.**

### 📝 The question that travels

In `agents/legal/agent.py` the instruction says: when it needs a value → status `ask_vendor` / `needs_user` with the options stated in a **`question`** field. In `agents/vendor_clearance/agent.py` you'll see the matching `status: "needs_input"` + `question` on its report, and `legal_safety_cert` carried in state — that's the answer coming back down.




`legal` is a single `LlmAgent` — no Workflow — but it's the most *tool-rich* agent in the mesh. It loads the `legal-clearance` skill and, through a `SkillToolset`, a full toolbox:

- **`search_legal_docs`** — the RAG tool, for reconstructing the process from the tribal-knowledge docs.
- **the workflow tools** — `draft_license_amendment`, `verify_certifications`, `request_certification`, `assign_customs_hs_code`, `set_royalty_rate`, `verify_liability_insurance`, `request_insurance_rider` — the concrete steps of clearing a deal, each a plain Python `FunctionTool`.
- **`upsert_contract`** — the one real side effect: an MCP tool that persists the executed `LC-####` contract to Firestore.

Its instruction ties them together: given a clearance brief, follow the skill (leaning on `search_legal_docs` to fill the gaps the docs leave), run the steps, and either **ask** for a missing value (`needs_user` + `question`) or **execute** the contract. When someone asks *it* a question ("what's an annual-volume band?"), it answers from `search_legal_docs`. The division to notice: RAG to figure out *what* to do, tools to *do* it.

### 💻 Deploy both Agents

Now deploy legal, then vendor_clearance (deploy **in this order** — vendor_clearance auto-discovers legal's A2A URL from `agent_identities.json`):

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py legal
python deploy/deploy_agents_a2a.py vendor_clearance
python deploy/collect_agent_identities.py
```

> ⏱️ **This takes a few minutes — don't sit and watch it.** The deploy packages your agent code,
> uploads it, and builds it into an engine in the cloud. Leave it running in this tab and skip
> ahead to **💻 Try `legal` on its own first**, just below: that part runs entirely on your own
> machine and needs nothing from this deploy. Come back to this tab when the two commands have
> finished, then carry on with the grants (two agents deploy here, so this is the longest wait).

Then grant each its own access:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh legal
./deploy/grant_agent_access.sh vendor-clearance
```

### 💻 Try `legal` on its own first

Before watching the handoff, talk to `legal` directly. It's worth doing separately: in the
handoff it answers *inside* another agent, so if retrieval came back empty you'd see a vague
vendor_clearance result rather than the real cause. On its own, you can see the knowledge base
you just built actually being read.

👉💻 In a **second Cloud Shell tab**, start the local MCP servers — `legal` uses
`mcp_licensing` to persist a contract:

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh mcp
```

👉💻 In a **third Cloud Shell tab**, launch the Dev UI on `legal`:

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_LICENSING_URL=http://127.0.0.1:9002/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/legal
```

Open it via **Web Preview → Change port → 8000**, pick **legal**, and ask it something the
answer to only exists in those scattered documents:

> What does "annual-volume band" mean, and what are the options?

> Are there style guidelines for grogu, and any exclusivity in North America?

👀 Watch the trace: it calls **`search_legal_docs`** and answers from what it retrieved — with
`status: answer`. That's the RAG corpus from `setup_legal_rag.sh` doing its job. Ask about
something the docs don't cover and you'll see the difference immediately.

👉💻 When you're done, press `Ctrl+C` in the `adk web` tab **and in the `./run_local.sh mcp`
tab** — the next section starts the whole local mesh, which needs ports `9002-9004` free.

### 💻 Try it in the ADK Dev UI

This agent hands off to `legal`, so `legal` has to be running too. The `mesh` command starts the whole local backend at once — the MCP servers **and** every agent as an A2A service, including `legal` on `:8005` (which `vendor_clearance` will call).

👉 **Stop the `./run_local.sh mcp` tab first** (`Ctrl+C`). `mesh` starts its own MCP servers on the
same ports `9002-9004`; if the old ones are still holding them, the new ones exit immediately and
`mesh` reports `Stopping…` as soon as it starts.

Then start it in one tab:

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
./run_local.sh mesh
```

In a **second Cloud Shell tab**, launch the Dev UI for vendor_clearance, pointed at the local MCP servers **and** the local `legal` service:

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_LICENSING_URL=http://127.0.0.1:9002/mcp
export MCP_MARKET_URL=http://127.0.0.1:9003/mcp
export LEGAL_A2A_URL=http://127.0.0.1:8005
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/vendor_clearance
```

Open it via **Web Preview → Change port → 8000**, pick **vendor_clearance**, and **onboard a vendor to a new category** — onboarding is what triggers the handoff to legal:

> Onboard vendor VND-1008 for grogu resin statues in North America.

Watch vendor_clearance clear the vendor, then **hand off to `legal` over A2A** (the `legal_clearance` node). Legal reconstructs its process from the docs — locally, via the keyword retriever — and either asks back for the **safety-cert ID** (the HITL question travelling up) or executes the contract. You can watch the handoff land in legal's log from the first tab:

```bash
cd ~/vibeflix-audit
source ./env.sh
tail -f /tmp/a2a_legal.log
```

👉💻 When you're done, press `Ctrl+C` in the `adk web` tab and again in the `./run_local.sh mesh` tab.

### 👀 Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step4.sh
```

It confirms both engines are deployed with agent identities. To see the handoff (and maybe the
HITL question), onboard a vendor to a new category — vendor_clearance will hand off to legal:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/ask_agent.py vendor-clearance \
  "Onboard vendor VND-1008 for grogu vinyl figures in NA."
```

> 👀 Watch for vendor_clearance to reach `legal_clearance`, legal to reconstruct its steps via
> RAG, and — if a safety-cert ID is needed — a `needs_input` status with a **question** bubbling
> back up. That's HITL. The full round-trip (answer coming back down from a real user) comes
> together once the app is in place (Step 6).

### 💡 What you learned

- **RAG** lets an agent reconstruct an undocumented process by *retrieving* facts instead of memorizing them.
- **A2A** lets one agent hand off to another independent agent as a **remote agent**.
- **HITL** is a question that propagates up to a human and an answer that flows back down without hard-failing the run.

## The Orchestrator

You've built four specialist agents. The **orchestrator** is the coordinator that runs them together: it reads a request, decides which specialists to invoke, runs them **in parallel**, and assembles the result. Building it teaches how ADK expresses a multi-step process as a **graph**, how to **fan out** to several agents at once, and why that fan-out needs a **shared task store**.

> 💡 The orchestrator is its **own independent agent** with its own identity. The app (Step 6)
> calls it over A2A exactly like any other agent — which is what makes the whole mesh uniformly
> governable later.

### 📝 The orchestrator's graph

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


### 💡 Concept — fan-out (and join)

Two edges do the heavy lifting:

```python
(dispatch, (guard_brand, guard_clearance, guard_pricing))   # one node → a TUPLE of nodes
((guard_brand, guard_clearance, guard_pricing), merge)      # the tuple → one JoinNode
```

An edge from one node to a **tuple** of nodes is a **fan-out**: all three run **concurrently**.
An edge from that tuple **into a `JoinNode`** (`merge`) is the **join**: it waits for all three
to finish, then continues with their combined output. This is how the audit runs brand, vendor,
and pricing checks *at the same time* instead of one after another.

### 📝 The other nodes — mostly plain code

You've seen `dispatch`, the three `guard_*` nodes, and `merge`. The rest of the graph is the
**glue** — most of it ordinary Python functions doing deterministic coordination, with a couple
that reach out to agents:

- **`ingest`** — a function that reads the incoming request (JSON from the app, or free text) and
  puts the deal's facts into shared state.
- **`dispatch`** — decides *which* specialists this request actually needs, using a small routing
  **skill** (a brand-only re-check shouldn't re-run pricing).
- **`guard_brand` / `guard_clearance` / `guard_pricing`** — each runs its domain **agent** over A2A
  (or reuses a cached report). This is the fan-out above.
- **`merge`** — the `JoinNode` that waits for all dispatched guards and combines their reports.
- **`recovery`** — a function that spots any agent whose report came back missing and **re-runs just
  that one**, a small self-heal step.
- **`compile_ui`** — a function that gathers the reports into the payload the UI Renderer will turn
  into panels.
- **`generate_report`** — a function that produces the final audit report, including the volume-cap
  check.
- **`contract_finalize`** — when every check passed, this **calls `vendor_clearance` over A2A** to
  execute the licensing contract, so a clean audit ends with a signed `LC-####`.
- **`finalize`** — a function that emits the final result the A2A caller receives.

The pattern to take away: an orchestrator is mostly **deterministic control flow** — plain
functions moving state from node to node — with agent calls dropped in at the few nodes that need
judgement (`guard_*`, `contract_finalize`) and one skill-driven routing decision (`dispatch`).

### 📝 The specialists are remote agents

Each `guard_*` node runs its specialist and captures the report:

```python
await ctx.run_node(_AGENTS[agent_name], _brief_from_state(ctx))
```

`_AGENTS[...]` is a **`RemoteA2aAgent`** (built by `_remote_agent(...)`) — the ADK stand-in for an agent running in another engine (the ones you deployed in Steps 2–4). So a single orchestrator run fans out into **three simultaneous A2A calls** to three separate engines.

Look at `_remote_agent(...)` and notice what it *doesn't* do: it never branches on transport. All three specialists are built with the same constructor, and one boolean decides pacing:

```python
# agents/orchestrator/agent.py
_LONG_RUNNING_A2A = {"vendor_clearance_agent"}   # fans into legal's Q&A loop — can run long

        return VibeflixRemoteA2aAgent(
            name=name,
            description=description,
            agent_card=base,
            long_running=name in _LONG_RUNNING_A2A,
        )
```

`brand_style` (~18s) and `deal_pricing` (~9–20s) finish well inside the ~180s blocking ceiling, so they take the stock path. `vendor_clearance` can exceed it — it fans out into legal's multi-round question loop — so it sends non-blocking and polls. Same class, same `ctx.run_node`, one flag: **moving a hop across that ceiling is a boolean, not a different client.**

### 💡 Concept — the shared A2A task store

That fan-out is exactly where a subtle, brutal bug lives. Every A2A call is two HTTP requests: `POST message:send` (start the task), then `GET /tasks/{id}` polled until it's done. But **Agent Runtime runs each engine as several replicas with no session affinity** — so:

```
POST /message:send   → creates the task on replica A
GET  /tasks/{id}     → load-balanced to replica B → 404 Task not found
```

Measured on a real run: **404 on ~87% of polls.** The task lived in one replica's memory; the poll kept hitting others. That single fact caused slow runs, thousands of "error" spans, and phantom failure-recovery.

The fix: keep tasks **outside** the replicas in a **shared task store** that any replica can read. In this mesh the app hosts it, **backed by Firestore** — so it's durable and every replica sees every task. Misses drop to **0**.

### 📝 Look

Read the header of `packages/vibeflix-common/vibeflix_common/a2a/task_store.py` (or `docs/02-architecture.md` → *the shared task store*) for the full story. The key line: the engines don't use ADK's default in-memory task store; they're wired to a `RemoteTaskStore` that reads/writes the app's Firestore-backed endpoints.

### 💡 Concept — two kinds of memory: the session and the Memory Bank

The task store you just met is one place state lives — a *coordination* board that every replica shares *during* a run. The orchestrator touches two more, and they are the two most-confused ideas in ADK, so it is worth pulling them apart. They answer different questions:

- the **session** answers *"what has happened so far in **this** audit?"*
- the **Memory Bank** answers *"what did we learn from **past** audits?"*

**1. The session — the memory of one run.**

Every time the orchestrator runs, ADK opens a **session**: an ordered log of the run's events plus the shared **`state`** dictionary the nodes read and write (the vendor, the character, the volume, and — importantly — the answer to any HITL question). It is the same `state` you watched fan out from node to node.

Two things depend on it:

- **HITL resume.** When legal paused on the safety-cert question in Step 4, the run ended but the session was **kept**. The person answers, the answer is written into `state`, and ADK **replays the `rerun_on_resume` nodes** against that same session — so the run picks up exactly where it paused. A durable session is the thing there is to resume *into*.
- **Surviving a crash.** Agent Runtime recycles replicas (a deploy, an autoscale event). A session that lived only in a replica's memory would be lost on a recycle mid-run. So each engine's session is backed by **`VertexAiSessionService`**, which stores it in the engine itself (the Vertex Agent Engine). A session is scoped to **one run** — a new audit opens a new session.

Every engine gets this, keyed by the engine's own id (Agent Runtime injects `GOOGLE_CLOUD_AGENT_ENGINE_ID` at runtime):

```python
# deploy/deploy_agents_a2a.py — the Runner every engine is deployed with
session_service = VertexAiSessionService(project, location, agent_engine_id=eid)
```

**2. The Memory Bank — the memory across runs.**

A session forgets everything the moment its run ends. But a compliance desk *should* remember: *"we audited VND-1001 for grogu vinyl figures last month, all cleared, 18% royalty."* That cross-run recall is a **Memory Bank** — a separate Vertex surface that stores durable **memories** you search semantically, and it outlives any single session.

Only the **orchestrator** has one — it is the single agent that ever needs to recall past audits. The four specialists run with plain in-memory (they have nothing to remember between runs):

```python
# deploy/deploy_agents_a2a.py — build_runner(), orchestrator only
memory_service = VertexAiMemoryBankService(project, location, agent_engine_id=eid)  # orchestrator
memory_service = InMemoryMemoryService()                                            # every other engine
```

Two halves make it useful — a **write** and a **read**:

- **Write (end of a passing audit).** When `contract_finalize` has a clean audit, it writes **one curated memory** — *"Licensing audit — vendor VND-1001, character grogu, Vinyl Figures, Asia-Pacific, 15,000 units: all workflows passed. Terms: royalty 0.18…"* — with `add_memory`. Two subtleties live here. Building the service stores nothing on its own; a memory only exists once you **call `add_memory`**. And the write runs **engine-side, inside the orchestrator's own workflow**, because that is the only place the real run lives — the app, calling over A2A, receives just the reply text back.
- **Read (any later run).** The console's chat box routes to a small `note_responder` agent that carries ADK's built-in **`load_memory`** tool. Ask *"have we audited VND-1001 before?"* and `load_memory` searches the same bank and answers from the stored memories.

For the read to find the write, both use the **same scope** — an `app_name` / `user_id` pair. The orchestrator pins that scope explicitly, so every audit writes into, and every question reads from, one shared pool.

**Holding the two apart:**

| | **Session** | **Memory Bank** |
|---|---|---|
| Question it answers | what happened in *this* run? | what did we learn from *past* runs? |
| Scope | one audit run | across all audits |
| Backed by | `VertexAiSessionService` (every engine) | `VertexAiMemoryBankService` (orchestrator only) |
| Written | automatically, at every node | explicitly, once, by `contract_finalize` |
| Read by | ADK, to resume / replay the run | `note_responder`'s `load_memory` tool |
| Powers | HITL resume · crash survival | "have we seen this vendor before?" |

A session is your **working notes** for the case on your desk; the Memory Bank is the **filing cabinet** of every case you have ever closed.

### 📝 Look — where each one is wired

- **Session** — `deploy/deploy_agents_a2a.py` → `build_runner()`: every engine's `Runner` gets `session_service=VertexAiSessionService(agent_engine_id=eid)`.
- **Memory write** — `agents/orchestrator/agent.py` → `contract_finalize` calls `_remember_audit(...)`, which builds the one-line fact and calls `add_memory(...)` under the pinned scope.
- **Memory read** — the same file's `note_responder` agent lists the `load_memory` tool; the app runs it whenever you type in the console's chat box.

### 💡 Concept — resuming a run after a crash

A full audit is a long, multi-step run — fan out to three agents, merge, self-heal, compile the UI, then execute the contract — that can take a few minutes. Agent Runtime runs each engine as several replicas, and a replica can be recycled mid-run (a deploy, an autoscale event). Starting the whole audit over from the top every time that happens would be wasteful.

ADK's answer is **resumability**, turned on with one flag on the `App`:

```python
# deploy/deploy_agents_a2a.py — build_runner(), orchestrator only
app = App(name=name, root_agent=mod.root_agent,
          resumability_config=ResumabilityConfig(is_resumable=True))
```

With it on, a **re-invoked** invocation picks up where it stopped: ADK **replays the nodes that already finished from their cached output** and re-runs only the ones still pending. This works because each engine's session is durable (`VertexAiSessionService`), so the run's events survive the replica dying — the session gives you the material to replay from.

Two things keep it correct:
- **`@node(..., rerun_on_resume=True)`** marks which nodes re-execute on a resume; the others replay from cache.
- A node that re-runs runs **again**, so it must be **idempotent** — resume is at-least-once. That's why `contract_finalize`'s Memory Bank write is guarded to fire once (`ctx.state["audit_remembered"]`) and the licensing contract is an **upsert** keyed by contract id.

One honest boundary worth knowing: the flag makes a run *able* to resume — it doesn't, by itself, *trigger* a resume. Something has to re-invoke the orchestrator with the **same invocation id** for ADK to pick it up (verified: re-invoking with a matching id replays the finished nodes rather than restarting). Fully-automatic crash recovery — detecting an orphaned run and re-invoking it — is extra wiring on top. (Separately, the HITL "resume" the console does today is a *re-submit* that re-runs the workflow incrementally with the answer, not an in-graph pause.)

### 💻 Deploy the orchestrator

Deploy it last of the agents — it auto-discovers the three specialists' A2A URLs from
`agent_identities.json`:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py orchestrator
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh orchestrator
```

> The orchestrator reads the shared task store from the **app**, which you deploy in Step 6.
> Until then, a fan-out run falls back to per-replica memory (with a loud warning) — fine for a
> single-replica smoke test, but the real, fast, multi-replica run comes together once the app
> is up.

### 👀 Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step5.sh
```

It confirms the orchestrator engine is deployed with an agent identity. The end-to-end fan-out, one request lighting up all three specialists at once. You'll run for real in Step 8, after the app and its task store are in place.

### 💡 What you learned

- An ADK **Workflow** is a **graph** of nodes and edges; you declare the flow, ADK walks it.
- An edge to a **tuple** is a **fan-out** (parallel); a **`JoinNode`** waits for all branches.
- Fan-out over A2A needs a **shared task store** (here, Firestore-backed) or replica load-balancing 404s most of your polls.
- A remote agent is **one class for every hop**; only the *pacing* differs. Anything that can run past Agent Runtime's **~180s blocking ceiling** sends non-blocking and polls (`long_running=True`) — a boolean at the call site, not a second transport.
- A **session** (`VertexAiSessionService`) is the memory of **one run** — it powers HITL resume and crash survival; a **Memory Bank** (`VertexAiMemoryBankService`, orchestrator-only) is the memory **across runs** — written once by `contract_finalize`, read by `note_responder`'s `load_memory`.
- **Resumability** (`ResumabilityConfig(is_resumable=True)`) lets a re-invoked run replay finished nodes from cache and re-run the pending ones instead of restarting — which is why `rerun_on_resume` nodes must be **idempotent**.

## UI Renderer, A2UI, and the Frontend

You have a working brain — five agents that reason and a coordinator that runs them. Now you'll give it a face. This step deploys the **console app** (the frontend + the shared task store) and introduces the agent that generates the UI: the **UI Renderer**, speaking **A2UI**.

### 💡 Concept — A2UI: the agents generate the UI

A normal app has **static forms**: a developer decides in advance "show a text box here, a table there." But an audit's result is *not* fixed — one run flags a brand issue, another blocks on
exclusivity, another needs a safety-cert ID from the user. Hand-coding a panel for every possible
shape is a losing battle.

**A2UI (Agent-to-User Interface)** flips it, as it ** generates the UI** based on what the backend agents actually produced, the result shapes the interface.

### 📝 The UI Renderer is just another agent

Open `agents/ui_renderer/agent.py`. Its docstring says it plainly:

> *"The orchestrator … returns raw domain reports. This agent turns those (varied,
> non-deterministic) reports into user-friendly panels. It's served over A2A."*

Two things worth noticing:

- It's an **independent A2A agent**, exactly like the domain agents — its own engine, called over A2A. The app talks to it the same way it talks to the orchestrator.
- Its **rendering procedure is a Skill** (`skills/render-a2ui/SKILL.md`) — same pattern as `deal_pricing`. It has **no tools** and an `output_schema`, so it uses the model's native structured output to emit UI components.

### 💡 Concept — the app is a thin client to *two* agents

Open `agents/app.py`. The app is deliberately a **thin client** — it contains no audit logic. For
each request it makes two A2A calls:

```
browser ──► app ──A2A──► orchestrator   (run the audit → raw reports)
                └──A2A──► ui_renderer    (turn the reports into A2UI panels)
```

The app then assembles the A2UI surface and streams it to the browser. Because the orchestrator is a *separate* agent (not imported into the app), the app calling it over A2A is what puts it on the same governed footing as every other hop.

The app also hosts the **shared A2A task store** you met in Step 5 (`/api/taskstore/*`, backed by Firestore) and the single Pub/Sub telemetry consumer — which is why it must run as **exactly one instance**.
In a production system, the task store and the telemetry consumer would each be their own service,
so the web frontend could scale up and down freely. Here we fold all three responsibilities into
the one app container to keep the workshop simple, which is why it runs pinned to a single instance.

### 💻 Deploy the UI Renderer (the 6th agent)

The app calls the UI Renderer, so deploy it first, and grant its access like any other agent:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py ui_renderer
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh ui-renderer
```

### 💻 The app's identity

The app runs as its own service account with its own least-privilege IAM. It gets just enough to do
its job: call the engines over A2A (`aiplatform.user`); read and write the shared task state on the
agents' context surface (`agentContextEditor` — without it the task-store reads fail and audits
hang); read the Firestore data it serves — the registries, the audit history, the task store
(`datastore.user`); resolve the engines' A2A URLs from the registry (`agentregistry.viewer`); store
uploaded mock-ups in the request-image bucket; and publish app-side events plus consume the
mesh-telemetry subscription. `setup_app_iam.sh` grants exactly that set and creates the subscription:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_app_iam.sh
```

### 💻 Build & deploy the app

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/deploy_app.sh
```

It builds the frontend + API image, auto-resolves the engine A2A URLs and three MCP URLs, and deploys `vibeflix-app` to Cloud Run pinned to a single instance.

### 💻 Redeploy the engines (pass 2)

Here's a subtlety worth understanding. The engines need the app's URL (for `TASK_STORE_URL`), but the app needed the engines' URLs first — a genuine **circular dependency**. The fix is to deploy the engines **twice**, with the app in between. You've done pass 1 (Steps 2–5) and just deployed the app; now do **pass 2** so the engines pick up the task-store URL:
*(The app's Cloud Run URL is actually predictable — `https://vibeflix-app-<project-number>.<region>.run.app` — so a production pipeline could compute it up front, set `TASK_STORE_URL` on the first pass, and skip this redeploy entirely. We keep it as an explicit second pass here so the circular dependency stays visible.)*


```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py        # no arg = redeploy all engines (pass 2)
```

Skip this and the engines log `[task-store] … falling back to the per-replica store`, and you're
back to the 404 storm from Step 5.

### 👀 Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step6.sh
```

It confirms the app is deployed and **pinned 1/1**. Then open the app in your browser:

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

> 👀 You'll see the **Live Compliance Audit** console. Don't run a full flow yet — the access
> controls aren't in place. That's Step 7. Then in Step 8 you'll run the scenarios and watch the
> A2UI panels build themselves from each run's results.

### 💡 What you learned

- **A2UI** generates the interface from the agents' output, so you don't hand-build a static form for every outcome.
- The **UI Renderer** is just another A2A agent — the app calls it alongside the orchestrator.
- The app is a **thin client** and the host of the shared task store — hence single-instance — and
  the engine ↔ app **circular dependency** is resolved by deploying the engines twice.

## Identity, Gateway & Registry

The agent mesh works, and each agent already has its **own identity** with **its own least-privilege IAM** , and the MCP servers are in the **registry** (Step 1). What's still missing is the **governed gateway** in the path. 

This step adds that gateway and registers the six agents as destinations too. It's the point where
the mesh's traffic finally becomes governed end to end, with every hop checked against policy.

### 💡 Concept — three pieces of the security model

**1. Agent Identity — every agent is its own principal.**
We would like to not share the service account in the mesh. Each engine runs *as* `principal://…/reasoningEngines/<id>`, a first-class identity, enabled at deploy time. In Steps 2–5 you granted each one its least-privilege **IAM** with `grant_agent_access.sh` — keyed to that agent's own principal, one agent at a time.

What did those per-agent grants actually give each identity? Just what that one agent needs to do
its job: permission to call Gemini, to read and write its **own** sessions and memory
(`agentContextEditor`), to read the Firestore data behind its tools, and to mint the token that lets
it reach its MCP server. Because every grant is keyed to a specific `principal://`, there's no
blanket "any agent can do anything" role anywhere in the project — if you listed the IAM on the
licensing MCP server, you'd see exactly which agents can reach it and no others. This step adds one
grant on top: permission to egress *through the gateway* (`iap.egressor`), which is what the next
piece governs.

> ⚠️ The engine id is baked into the principal. **Never delete an engine** and recreate it — the
> new id means a new principal, and every grant is orphaned onto a dead one. Always *update in
> place*.

**2. Agent Registry — the list of who can be called.**
Every MCP server and every agent is registered as a **destination**, and an **unregistered destination is blocked**. You registered the **MCP servers** in Step 1; this step registers the **6 agents**. The gateway's policies and A2A egress grants key off these entries.

**3. Agent Gateway — one governed front door, deny-by-default.**
Agents can't reach the open internet or each other freely. A governed gateway sits in the path, and an agent may only reach a destination it's been **explicitly granted**. On top of that, per-tool **IAP authz policies** (CEL conditions on tool attributes, in `deploy/policies.yaml`) decide *which tools* each agent may call, right down to the individual tool on a server.

So what *is* the Agent Gateway? It's a governed front door for everything the engines send
**outbound**. On Agent Runtime, an agent-identity engine can't open arbitrary network connections;
its egress is routed through the gateway, which is **deny-by-default**. For each outbound call the
gateway asks three questions: is the destination a **registered** endpoint? has this agent been
granted **egress** to it (`iap.egressor`)? and — for an MCP tool call — do the **per-tool policies**
in `policies.yaml` allow this agent to invoke *that specific tool*? The call leaves the engine only
when all three pass. That's what makes "least privilege" real here: it's checked on the wire, on
every hop, by the platform.

Together: **least privilege, enforced by the platform itself.**

### 📝 The policy map

Open `deploy/policies.yaml` — it maps each agent to the exact tools it's allowed to invoke (e.g.`brand_style` → `run_brand_audit`; `deal_pricing` → `get_license_pricing`). That's the difference between "this agent can reach the licensing server" and "this agent can call *only* `get_license_pricing` on it."

`deploy/setup_gateway.sh` reads this and builds, in order: **registry** (registers the 6 agents; the MCP servers were already registered in Step 1) → **gateway** (the governed front door) → **policies** (the IAP authz extension) → and finally calls **`grant_agent_iam.sh`**, which adds the **gateway egress grants** (`roles/iap.egressor` on each allowed destination) on top of the per-agent access you granted in Steps 2–5.

### 💻 Register, gate, and grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

One command runs all four sub-steps. It uses **preview** gcloud surfaces, so if a step reports a spelling drift, re-run just that phase — `./deploy/setup_gateway.sh registry` / `gateway` / `policies`.

> ⏱️ IAM and gateway changes take **2–5 minutes** to propagate. If a call is still denied right
> after, wait before assuming it's broken.

### 💻 Attach the engines to the gateway

The gateway exists **now** — it didn't when you deployed the engines in Steps 2–5, so they were
deployed without it (each deploy said so: *"Agent Gateway doesn't exist yet — deploying WITHOUT
governed egress"*). An engine's gateway attachment is part of its deployment spec, so redeploy
them once to pick it up:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py        # no arg = all six engines
```

This is the same two-pass shape you saw with `TASK_STORE_URL` in Step 6: something an engine
needs is created *after* the engine, so the engine is redeployed once the thing exists. Until
this pass, the agents' egress isn't governed by the gateway.

### 👀 Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

It confirms the **gateway exists**, the **6 agents + 3 MCP servers are registered**, and **all six agents run under their own agent identity** (`principal://`).

### 💡 What you learned

- **Agent Identity** makes every agent its own principal — attributable, least-privilege, never a shared SA.
- **Agent Registry** declares callable destinations; unregistered ones are blocked.
- **Agent Gateway** enforces deny-by-default egress plus **per-tool** policies — the governance is
  genuinely in the path, which is the whole demonstration.

## Run the Flows, Observability & Wrap-up

Everything is built and secured. Time to *use* it — run real audits, watch the mesh light up, and
see the whole distributed system through the observability tools. Then we wrap up.

### 💻 Run — the four scenarios

Open the console and grab its URL:

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

The console has a **scenario picker** above the chat box. Run each one and watch the mesh work:

| | Scenario | What it exercises |
|---|---|---|
| ✅ | **Happy path** | a clean vendor + product clears brand, pricing, and vendor checks |
| ⛔ | **Exclusivity block** | an exclusive partner holds the territory → `vendor_clearance` blocks it |
| 🆕 | **Onboard new vendor** | a brand-new vendor/category → the **A2A handoff to legal** + the **human-in-the-loop** question (it asks you for one thing — the HQ location) |
| 📦 | **Over volume cap** | projected volume exceeds the SKU cap → flagged |

> 👀 As each runs, the **live graph** animates: nodes light as agents start, tool **LEDs** blink as
> MCP tools fire, and the **A2UI panels** assemble from each run's actual results. The *Onboard*
> flow is the one to watch closely — it pauses to ask you a question (HITL) and only finishes the
> contract once you answer.

### 💡 Concept — observability: three views of one run

The mesh has been emitting telemetry the whole time (it's on by default — every engine deploy set
`GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true`). Here's where to see it:

1. **The live graph (in the app).** Agents publish fine-grained events to a **Pub/Sub** topic; the app relays them to the console, which animates the Workflow graph in real time. This is telemetry as a *product feature* you can watch as the audit runs.
2. **Cloud Trace.** Every request is one **distributed trace** whose spans stitch across A2A hops *and* MCP tool calls — so a single audit shows the orchestrator → the three specialists → their MCP tools, with timing, in one waterfall. Console → **Trace → Trace explorer**.
3. **Application Topology.** Console → **Agent Platform → Topology** shows the mesh as a graph of nodes — agents and MCP servers — discovered from the aggregated traces. It's the architecture diagram from Step 0, drawn from real traffic.



### 👀 Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step8.sh
```

It confirms all six engines have **telemetry on**, **trace propagation on**, and the **shared task store wired** — the three flags a deploy can silently drop that would leave you blind or slow.

### 🎉 What you built

A **ten-service, distributed, secured multi-agent system**:

- **3 MCP tool servers** — deterministic, IAM-gated (Step 1)
- **6 agents** — brand, pricing, vendor, legal, orchestrator, UI renderer (Steps 2–6)
- **1 console app** — thin client + shared task store (Step 6)
- governed by **Agent Identity + Gateway + Registry** (Step 7)
- observable end-to-end via **Trace + live telemetry + Topology** (Step 8)

And the concepts behind them: **MCP**, **deterministic vs non-deterministic** work, **Skills**, **loop-engineering**, **RAG**, **A2A handoff**, **human-in-the-loop**, the **ADK graph** and **fan-out**, the **shared task store**, **A2UI**, and **enterprise governance**.

### 🧹 Teardown

When you're completely done, one script removes everything so you don't leave anything running:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/destroy.sh              # delete the workshop's resources, keep the project
# — or —
./deploy/destroy.sh --project    # delete the WHOLE project (fastest, cleanest)
```

It asks you to type the project id to confirm, then removes the 6 engines, the app + 3 MCP Cloud Run services, the gateway + registry entries, the Terraform-managed infra (Artifact Registry + topic), the buckets, Firestore, Pub/Sub, and the service accounts. It's best-effort and re-runnable.

> **Destructive and irreversible** — run it only when you're finished. (The "never delete an
> engine" rule from Step 7 is about *redeploys*; at teardown, deleting is exactly what you want.)

### Where to go next

- Re-read any agent's code now that you know the concepts — `agents/<name>/agent.py`.
- The deeper design docs: [`docs/`](../docs/) (story, architecture, the shared library).
- The full operational runbook: [`deploy/docs/instruction-sre.md`](../deploy/docs/instruction-sre.md).

**🎉 Congratulations — you've built and shipped an enterprise multi-agent mesh on Google Cloud.**










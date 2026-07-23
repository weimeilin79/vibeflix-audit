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
- **Cloud Shell** is the easiest place to work — `gcloud`, `terraform`, and `python3` are
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

### 💻 Get the code

Clone the workshop repository:

```bash
git clone https://github.com/weimeilin79/vibeflix-audit
cd vibeflix-audit
```

(In **Cloud Shell**, `git` is already installed. The scripts are committed executable, so there's
no `chmod` to do — you can run them straight away.)

### 💻 Run — configure the project

Create your environment file and set your project + region:

```bash
cp deploy/.env.example deploy/.env
# edit deploy/.env — set at least:
#   PROJECT=<your-project-id>
#   REGION=us-central1
#   TASK_STORE_KEY=$(openssl rand -hex 24)
# On a fresh project, LEAVE the bucket vars unset (project-prefixed defaults are used).
```

### 💻 Setup the foundations + all 3 MCP servers

```bash
./workshop/setup.sh
```

This runs, in order: **preflight** (checks your tools) → Python **venv + deps** → **enable APIs** → **foundations** (a Terraform module that creates the container-image registry + the telemetry topic) → **buckets** → **Firestore** (creates the database and seeds the registries the MCP servers read) → **Pub/Sub** → **builds and deploys the 3 MCP servers to Cloud Run** → **registers the 3 MCP servers in the Agent Registry**.


It's idempotent — if a step fails (usually a missing API or permission), fix it and re-run, completed steps are skipped.

### 👀 Verify the MCP servers are up *and* locked down

```bash
./deploy/verify/step1.sh
```

This confirms the Artifact Registry repo, the telemetry topic, the Firestore database, and **all three MCP servers are up *and* IAM-gated** (It should return **403**). 


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

Now open `agents/brand_style/agent.py`. Its docstring states the division plainly:

> *"The agent does the EXTRACTION (reading the artwork's printed text and product medium, using
> its own multimodal vision); the MCP server is the deterministic auditor."*

So the model's *only* job is to turn a picture into the three inputs. The verdict is the tool's.

> 💡 **Reinforcement (optional):** the code has three guardrails that all say *"keep the
> deterministic stuff out of the model's hands"* — `require_image_before_model` (no image →
> refuse *before* calling the model, so it can't invent an extraction), the **asset-source
> gate** inside the tool (unapproved image → `rejected`, stop), and `tool_guard` (if the MCP
> didn't load, the agent refuses rather than answering blind). Mention one, skip the rest.

### Build & deploy brand_style

The deploy script finds the MCP server URLs for you, so deploying your first agent is a single command:

```bash
python deploy/deploy_agents_a2a.py brand_style
```

This packages the agent folder, deploys it to **Agent Runtime** as its own engine that serves A2A automatically, and turns on its **agent identity**. This deploymenet may takes a few minutes.

### 💻  Grant the agent its own access

The engine exists now, but with no permissions. Grant project roles on **its own identity**, and the ability to reach the IAM-gated MCP servers:

```bash
./deploy/grant_agent_access.sh brand-style
```

This is **least privilege in action**: each agent grants its *own* access as it's deployed, keyed to its *own* principal — no blanket "any agent can do anything." 

### 👀 Verify the agent extracts, then the tool decides

```bash
./deploy/verify/step2.sh
```

It confirms the `brand_style` engine is deployed **with an agent identity**. To watch it actually work, talk to it directly — point it at the default mock-up and see it read the image, then call the deterministic tool:

```bash
ENGINE=$(jq -r '.["vibeflix-brand-style"].engine' deploy/agent_identities.json)
agents-cli run --url "$ENGINE" --mode adk \
  "Audit this mock-up. image: gs://${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image}/vendor_request_refine.png, character: grogu, market: NA"
```

> 👀 In the reply you should see the agent report the **text and medium it read from the
> image** (the non-deterministic part) and a **status** — `compliant`, `flagged`, or
> `rejected` — that came from `run_brand_audit` (the deterministic part). Try a bad image link
> and watch the **asset-source gate** reject it *before* any content check runs.

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

### 📝 Look — the skill and the loop, in the code

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

### 💻 Build & deploy deal_pricing

Same one command as before — the deploy script finds `mcp_licensing`'s URL automatically:

```bash
.venv/bin/python deploy/deploy_agents_a2a.py deal_pricing
```

Then grant it its own access (project roles on its principal + reach to the MCP servers):

```bash
./deploy/grant_agent_access.sh deal-pricing
```

### 👀 Verify and watch the loop reconcile a claim

```bash
./deploy/verify/step3.sh
```

It confirms the `deal_pricing` engine is deployed with an agent identity. Then send it the
underpriced deal from the concept above and watch it reason:

```bash
ENGINE=$(jq -r '.["vibeflix-deal-pricing"].engine' deploy/agent_identities.json)
agents-cli run --url "$ENGINE" --mode adk \
  "Audit this deal. character: grogu, product_category: vinyl figures, territory: NA, \
volume: 30000, net_unit_price: 18. Agreed terms — royalty_rate: 0.10, advance: 8000, mg: 30000."
```

> 👀 Look for the agent to (1) pull the **expected** deal from the tool, (2) mark the royalty **unresolved** with the volume-discount claim, (3) let the **reconcile loop** reject the claim
> (30k < 50k), and (4) return a verdict — here **NEEDS-ADJUSTMENT** (or **UNDERPRICED** if a floor is breached). If it asks for a missing field, that's the agent doing input-validation, supply it and re-run.

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

### 📝 The retrieval tool

Open `agents/legal/legal_kb.py`. It exposes one FunctionTool, `search_legal_docs`, with the following backends:

- **`RAG_CORPUS` set** → Vertex AI **RAG Engine** (`:retrieveContexts`) over a corpus built from those docs (you'll build it below);

In `agents/legal/agent.py`, `search_legal_docs` sits alongside the legal *workflow* tools (`draft_license_amendment`, `verify_certifications`, `assign_customs_hs_code`, `verify_liability_insurance`, …) and the one real side effect — `upsert_contract` (an MCP tool) that persists the executed contract. The agent uses RAG to figure out *what the process is*, then the tools to *do it*.

### 💻 Build legal's knowledge base

Legal needs its RAG corpus first. Build it from the tribal-knowledge docs:

```bash
./deploy/setup_legal_rag.sh
# It prints  RAG_CORPUS=projects/.../ragCorpora/...
# Add that line (and RAG_LOCATION=us-central1) to deploy/.env, then continue.
```


### 💡 Concept — A2A: handing off to a remote agent

`legal` is **its own deployed agent** — a separate engine with its own identity. `vendor_clearance` doesn't import it or contain it; it **calls it over A2A** (Agent-to-Agent), the protocol for one
agent delegating to another.

The way ADK models "an agent running somewhere else that I can call" is a **remote agent**. You hold a lightweight stand-in for the remote engine and invoke it like a local step; the call travels over A2A to the other engine and the result comes back.

### 📝 The handoff as its own step

Open `agents/vendor_clearance/agent.py`. It's a small Workflow:

```
START → clearance → legal_clearance → finalize
```

`legal_clearance` is a **distinct node** whose whole job is the handoff — it calls the legal engine over A2A (`LEGAL_A2A_URL` points at it) with a *fresh* context and merges legal's verdict + contract id back in. Making the handoff its own node means it shows up as its own step in the trace (you'll see this in Step 8's observability), and keeps each agent's reasoning isolated.

> 💡 The orchestrator (Step 5) uses ADK's `RemoteA2aAgent` construct for the same idea at scale.
> `vendor_clearance→legal` uses a direct, fresh-context A2A call on purpose — so legal doesn't
> receive vendor_clearance's whole conversation and echo it back.

### 💡 Concept — Human-in-the-loop (HITL)

Buried in that tribal knowledge is a rule that keeps breaking onboardings: a contract **cannot execute** until a human supplies a **safety-certification ID** that lives in *no* record.
Everyone forgot it existed.

So legal implements it as **human-in-the-loop**: when it needs a value it can't find, it doesn't guess and it doesn't hard-fail — it returns a **question** and a status like `needs_user`. That question **propagates up** the call chain — legal → vendor_clearance (`status: needs_input`) → orchestrator → the app → **the person who started the audit**. Their answer comes **back down** through workflow state (`legal_safety_cert`), vendor_clearance folds it into the brief, and legal reads it and proceeds. (If no ID is ever supplied, legal issues a provisional `PROV-…` id and reports it — so onboarding is never silently blocked.)

### 📝 The question that travels

In `agents/legal/agent.py` the instruction says: when it needs a value → status `ask_vendor` / `needs_user` with the options stated in a **`question`** field. In `agents/vendor_clearance/agent.py` you'll see the matching `status: "needs_input"` + `question` on its report, and `legal_safety_cert` carried in state — that's the answer coming back down.

### 💻 Deploy both Agents

Now deploy legal, then vendor_clearance (deploy **in this order** — vendor_clearance auto-discovers legal's A2A URL from `agent_identities.json`):

```bash
.venv/bin/python deploy/deploy_agents_a2a.py legal
.venv/bin/python deploy/deploy_agents_a2a.py vendor_clearance
```

Then grant each its own access:

```bash
./deploy/grant_agent_access.sh legal
./deploy/grant_agent_access.sh vendor-clearance
```

### 👀 Verify

```bash
./deploy/verify/step4.sh
```

It confirms both engines are deployed with agent identities. To see the handoff (and maybe the
HITL question), onboard a vendor to a new category — vendor_clearance will hand off to legal:

```bash
ENGINE=$(jq -r '.["vibeflix-vendor-clearance"].engine' deploy/agent_identities.json)
agents-cli run --url "$ENGINE" --mode adk \
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

### 💡 Concept — the ADK graph: nodes and edges

An ADK **Workflow** is a **directed graph**. You describe *what* happens and *in what order* with two primitives:

- a **node** — one unit of work: a function, or "run this agent";
- an **edge** — "after this node, go to that node."

You don't write control flow by hand; you declare the edges and ADK walks the graph, carrying shared **state** from node to node.

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

### 💡 Concept — the shared A2A task store

That fan-out is exactly where a subtle, brutal bug lives. Every A2A call is two HTTP requests: `POST message:send` (start the task), then `GET /tasks/{id}` polled until it's done. But **Agent Runtime runs each engine as several replicas with no session affinity** — so:

```
POST /message:send   → creates the task on replica A
GET  /tasks/{id}     → load-balanced to replica B → 404 Task not found
```

Measured on a real run: **404 on ~87% of polls.** The task lived in one replica's memory; the poll kept hitting others. That single fact caused slow runs, thousands of "error" spans, and phantom failure-recovery.

The fix: keep tasks **outside** the replicas in a **shared task store** that any replica can read. In this mesh the app hosts it, **backed by Firestore** — so it's durable and every replica sees every task. Misses drop to **0**.

### 📝 Look

Read the header of `packages/vibeflix-common/vibeflix_common/task_store.py` (or `docs/02-architecture.md` → *the shared task store*) for the full story. The key line: the engines don't use ADK's default in-memory task store; they're wired to a `RemoteTaskStore` that reads/writes the app's Firestore-backed endpoints.

### 💻 Deploy the orchestrator

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

### 👀 Verify

```bash
./deploy/verify/step5.sh
```

It confirms the orchestrator engine is deployed with an agent identity. The end-to-end fan-out, one request lighting up all three specialists at once. You'll run for real in Step 8, after the app and its task store are in place.

### 💡 What you learned

- An ADK **Workflow** is a **graph** of nodes and edges; you declare the flow, ADK walks it.
- An edge to a **tuple** is a **fan-out** (parallel); a **`JoinNode`** waits for all branches.
- Fan-out over A2A needs a **shared task store** (here, Firestore-backed) or replica load-balancing 404s most of your polls.

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
.venv/bin/python deploy/deploy_agents_a2a.py ui_renderer
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
./deploy/setup_app_iam.sh
```

### 💻 Build & deploy the app

```bash
./deploy/deploy_app.sh
```

It builds the frontend + API image, auto-resolves the engine A2A URLs and three MCP URLs, and deploys `vibeflix-app` to Cloud Run pinned to a single instance.

### 💻 Redeploy the engines (pass 2)

Here's a subtlety worth understanding. The engines need the app's URL (for `TASK_STORE_URL`), but the app needed the engines' URLs first — a genuine **circular dependency**. The fix is to deploy the engines **twice**, with the app in between. You've done pass 1 (Steps 2–5) and just deployed the app; now do **pass 2** so the engines pick up the task-store URL:
*(The app's Cloud Run URL is actually predictable — `https://vibeflix-app-<project-number>.<region>.run.app` — so a production pipeline could compute it up front, set `TASK_STORE_URL` on the first pass, and skip this redeploy entirely. We keep it as an explicit second pass here so the circular dependency stays visible.)*


```bash
.venv/bin/python deploy/deploy_agents_a2a.py        # no arg = redeploy all engines (pass 2)
```

Skip this and the engines log `[task-store] … falling back to the per-replica store`, and you're
back to the 404 storm from Step 5.

### 👀 Verify

```bash
./deploy/verify/step6.sh
```

It confirms the app is deployed and **pinned 1/1**. Then open the app in your browser:

```bash
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
./deploy/setup_gateway.sh
```

One command runs all four sub-steps. It uses **preview** gcloud surfaces, so if a step reports a spelling drift, re-run just that phase — `./deploy/setup_gateway.sh registry` / `gateway` / `policies`.

> ⏱️ IAM and gateway changes take **2–5 minutes** to propagate. If a call is still denied right
> after, wait before assuming it's broken.

### 👀 Verify

```bash
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










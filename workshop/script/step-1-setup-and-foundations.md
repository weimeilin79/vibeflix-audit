# Step 1 — Setup & Foundations

**Target runtime:** 15–18 min · **Lab section:** `Setup & Foundations`

---

## 00:00 — Cold open

[SCREEN: the finished console, mid-audit. Three agent boxes light up at once, tool LEDs blink, a contract id appears.]

This is a licensing audit running end to end. A vendor has applied to manufacture a product, and six agents are deciding whether Vibeflix can approve it. They check the artwork against brand rules, the royalty numbers against a rate card, whether a competitor holds an exclusive contract in that territory, and what the legal process for onboarding involves. In about sixty seconds it finishes with a signed contract or a specific reason it can't happen. The same decision used to take three weeks.

Each of those six agents was deployed separately with its own identity. They call three tool servers that are locked down tightly enough that opening one of those URLs in a browser returns a 403. You'll try that yourself in a few minutes.

[SCREEN: cut to an empty Cloud Shell.]

Today we start with an empty project and build the layer those agents stand on. Three tool servers, a database, a telemetry topic, an image registry, and a catalogue that ties them together.

---

## 01:30 — The problem

Vibeflix licenses characters to manufacturers. A vendor asks to make vinyl figures of a character, for North America, at a royalty rate they propose. Somebody decides whether that's allowed, and that decision breaks into four jobs.

Someone checks the artwork against brand rules. Someone checks the royalty rate, advance and minimum guarantee against a rate card with tiers and modifiers. Someone checks whether an exclusivity contract already locks that character and category in that territory. And someone has to know the legal process for onboarding a vendor into a category they've never manufactured, which in most companies lives in people's heads.

Four kinds of expertise means four people, a shared inbox, and three weeks of back and forth.

The tempting fix is to hand all of it to one large language model. Give it the rate card, the contracts and the artwork, and ask it to decide. Doing that will produce a system you can't sign contracts with, and the next five minutes are about why.

---

## 03:00 — Two kinds of work

Two kinds of work sit inside that decision, and they fail differently.

The first is fuzzy. Looking at artwork and saying it's a vinyl figure with no printed text on it. Reading a messy Slack thread and working out the process. Two people describe that slightly differently, and a model varies the same way across two runs. The variation comes with the task.

The second is exact. Is a 10% royalty above or below a minimum of 10%? Is this vendor named on the exclusivity contract? Does 30,000 units qualify for a tier that starts at 100,000? These have one right answer, it has to be identical every time, and it has to match what finance gets with a spreadsheet.

Language models are good at the first kind and unsuited to the second, because they're probabilistic. A system that returns one royalty rate on Monday and a different one on Tuesday for the same deal can't be used to sign anything.

So the model does the fuzzy work and code does the deciding. The model looks at the image and reports what it sees. A tool takes those facts, applies the rules, and returns a verdict the model can't argue with or produce on its own.

[SCREEN: two columns — MODEL: extract, interpret, converse. TOOLS: compare, calculate, decide.]

---

## 05:00 — Tool servers and MCP

If the exact work belongs in tools, where do the tools live?

The simplest answer is inside the agent, as Python functions it imports. That works for a prototype, and we do something else for three reasons.

Pricing logic that sits inside the pricing agent makes that agent the only thing in the company that can price. The orchestrator has to go through it to get a rate card. Finance can't check a number, because the logic is buried in a prompt loop. Auditing which rules applied to a deal means reading model transcripts.

So the tools live in their own servers, and the agents call them over MCP, the Model Context Protocol.

[SCREEN: three boxes — mcp_brand_style, mcp_licensing, mcp_market.]

Three servers. One runs brand compliance checks. One owns licensing data, so vendors, rate cards, exclusivity contracts and executed contracts. One handles market data, scanning marketplaces and checking volume caps.

These are ordinary web services with URLs, deployed to Cloud Run, with IAM policies attached. You can point anything at them, because the business logic now has an address. Having an address is also what makes Step 7 work, because a policy can be attached to an HTTP endpoint.

---

## 07:00 — The registry

The third piece is the Agent Registry, and it's easy to skim past.

It's a catalogue. Every MCP server gets an entry, and later every agent does, recording its name, address and interface.

Discovery is the first use, so the console can list every tool in the mesh without anyone grepping the codebase. The second use arrives in Step 7, when a governed gateway goes in front of this traffic. That gateway is deny-by-default and only routes to destinations in the registry, so anything unregistered becomes unreachable. Registering a server today is what lets you govern it later. We do it now for the MCP servers and again in Step 7 for the agents.

---

## 08:30 — Getting set up

[DO: Activate Cloud Shell.]

Cloud Shell comes with gcloud, python3 and git. It no longer ships terraform. There's a placeholder on the path that prints installation instructions when you run it, which is confusing the first time you hit it. The init script handles that, so install nothing yourself.

[DO: run the auth check.]

```
gcloud auth list
gcloud config get-value project
```

Your account should read ACTIVE, and the project should be the one you intend to spend money in. Read that output, because everything we create lands in whatever it names.

[DO: clone.]

```bash
git clone https://github.com/weimeilin79/vibeflix-audit
cd vibeflix-audit
```

---

## 09:30 — The repo

[SCREEN: the directory tree.]

`agents` holds the six agents, one folder each. `mcp_servers` holds the three tool servers.

`packages` holds the shared library, split into four subpackages named after who imports them. Transport, ADK building blocks, MCP-only helpers, and the auth and telemetry that both sides use. When you're wondering whether you can import something, the folder name answers you.

`deploy` holds the deploy and verify scripts, the Terraform and your `.env`. `frontend` is the React console. `resource` holds seed data, including the legal documents that become a knowledge base in Step 4.

You'll read `agents` and `mcp_servers`, and run things from `deploy`.

---

## 10:30 — init.sh

```
cd ~/vibeflix-audit
./init.sh
```

[DO: run it.]

It checks your environment before creating anything. Every CLI the workshop needs, that you're authenticated, and that application-default credentials exist. If something's missing it stops before provisioning starts, so you find out now instead of halfway through building infrastructure.

Then it points gcloud at your project, creates the virtual environment, installs every dependency, installs a working terraform if the placeholder is in the way, and writes `deploy/.env`, the config file every other script reads. It takes a few minutes, mostly Python packages.

Build one habit while it runs. Every new terminal tab needs `cd ~/vibeflix-audit` and then `source ./env.sh`.

A new tab starts in your home directory with a clean environment, so without those two lines you run Cloud Shell's system Python instead of the project's. What you get is an `ImportError` from deep inside a Google library, which tells you almost nothing about what went wrong. Skipping those lines is the most common way people lose twenty minutes in this workshop.

Say `source`, and not `./env.sh`. A script can't change the environment of the shell that launched it, so running it that way achieves nothing. The file will tell you if you get it backwards. Every command block in this lab starts with those two lines, so you can copy any block into any tab and have it work.

---

## 12:00 — setup.sh

```bash
cd ~/vibeflix-audit
source ./env.sh
./workshop/setup.sh
```

[DO: run it. Several minutes — plan a jump cut.]

Nine steps in order. Preflight, enable APIs, foundations, buckets, Firestore, Pub/Sub, build and deploy the three MCP servers, register them.

Three of those are worth watching for.

Firestore holds the registries the MCP servers read, along with the vendors collection, which is the one thing agents modify at runtime when they onboard somebody.

The Pub/Sub topic carries telemetry. Agents publish events as they work, and in Step 6 the console subscribes to that stream. That's what animates the graph you saw in the cold open.

Artifact Registry stores container images for the MCP servers and the console app.

Every script here is safe to re-run. If one stops with an error, fix what it reports and run the identical command. Completed work is detected and skipped.

You'll need that occasionally through no fault of your own. These are real cloud APIs, several of them in preview, and they sometimes return transient internal errors. The setup scripts retry those and stop with a clear message when retrying doesn't help. When you see a red cross, read it and run `./workshop/setup.sh` again. It re-checks all nine steps and redoes only what's missing.

---

## 14:00 — Verify

[DO: run it.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step1.sh
```

It checks the image registry, the telemetry topic, the Firestore database and all three MCP servers.

The last check confirms the MCP servers are running and return a 403. That 403 is the test passing. Those services deploy with no public access, a caller needs the Cloud Run invoker role, and nothing holds it yet because no agent exists to grant it to.

[SCREEN: paste an MCP URL into a browser tab. 403.]

Try it yourself. We finish that security story in Step 7, and the tools making the consequential decisions in this system stay off the open internet the whole way through.

---

## 15:30 — Do and don't

Put the exact logic in a tool server, where it has a URL that IAM can be pointed at.

Keep the model away from any decision you'd have to defend. If somebody could sue over it, audit it, or reproduce it in a spreadsheet, it belongs in a tool.

Re-run scripts when they fail. Idempotency here is a design feature.

Run `cd` and `source ./env.sh` in every new tab.

---

## 16:30 — Where that leaves us

[SCREEN: architecture diagram, foundation layer lit.]

You have three deterministic, IAM-gated tool servers registered in the Agent Registry, a seeded database, a telemetry topic and an image registry. No agents yet.

Next we build brand style. It looks at a product mock-up, works out what it's looking at, and hands those facts to a tool that produces the verdict.

See you there.

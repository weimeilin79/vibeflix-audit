# Step 1 — Setup & Foundations

**Target runtime:** 20–24 min · **Lab section:** `Setup & Foundations`

---

## 00:00 — Cold open

[SCREEN: the finished console, mid-audit. Three agent boxes lighting up in parallel, tool LEDs blinking, a contract id appearing.]

This is where we're going. One request goes in — a vendor wants to make a product — and six agents work out whether that's allowed. Brand rules, licensing maths, exclusivity contracts, legal process. At the end, a signed contract or a clear reason why not.

[BEAT]

Nothing you're looking at is a demo shortcut. Those are six separately deployed agents, each with its own identity, calling three tool servers that are locked down so tightly that if you hit their URL in a browser right now, you get a 403.

[SCREEN: cut to an empty Cloud Shell.]

And this is where we're starting. Nothing. No database, no agents, no permissions.

In this step we're not building an agent. We're building the ground the agents stand on — and more importantly, I want you to understand *why* this particular ground, because almost every design decision in the next seven steps traces back to something we set up right now.

---

## 02:00 — The problem this system exists to solve

Let me give you the business problem first, because the architecture only makes sense once you've felt the pain.

Vibeflix licenses characters. A vendor comes along and says: *I want to make vinyl figures of this character, for North America, at this royalty rate.* Somebody has to decide whether that's allowed.

That decision is genuinely hard, and it's hard in four different ways at once.

Somebody has to look at the artwork and check it against brand rules. Somebody has to work out whether the money is right — royalty rate, advance, minimum guarantee — against a rate card with tiers and modifiers. Somebody has to check whether a competitor already holds an exclusive lock on that character in that territory. And somebody has to know the legal process for onboarding a vendor into a new product category — which, in most real companies, is not written down anywhere.

[BEAT]

Four different kinds of expertise. In the old world that's four people, a shared inbox, and about three weeks.

Now — the tempting move is to throw one large language model at the whole thing. Give it the rate card, give it the contracts, give it the artwork, and ask it to decide.

Don't. And the reason why is the single most important idea in this entire workshop, so let me be precise about it.

---

## 04:30 — The idea everything else hangs off

There are two kinds of work in that decision, and they have completely different failure modes.

The first kind is **fuzzy**. Looking at a piece of artwork and saying "that's a vinyl figure, and there's no printed text on it." Reading a messy Slack thread and working out what the process actually is. Ask two people, you get slightly different words. Ask a model twice, you get slightly different words. That's fine — that's the nature of the work.

The second kind is **exact**. Is 10% above or below the minimum royalty rate of 10%? Is this vendor's name on the exclusivity contract? Does 30,000 units qualify for the tier that starts at 100,000? Given the same inputs, the answer must be identical every single time, and it must be *the same answer your finance team would get with a spreadsheet*.

[BEAT]

A language model is excellent at the first kind and structurally unsuited to the second. Not because it's bad — because it's probabilistic. A system that produces a slightly different royalty rate on Tuesday than it did on Monday isn't an AI system with a bug. It's not a system you can put a contract through at all.

So the rule for this whole build is:

**The model does the fuzzy work. Deterministic code does the deciding.**

The model reads the image and says what it sees. A tool applies the rules and returns a verdict. The model cannot argue with the verdict, and it cannot compute one of its own.

[SCREEN: simple two-column diagram — MODEL: extract, interpret, converse. TOOLS: compare, calculate, decide.]

Keep that split in your head. Every step from here is a new place to apply it.

---

## 07:00 — Where the tools live: MCP

So the deterministic work goes in tools. Where do the tools live?

They could live inside the agent — just Python functions the agent imports. That works, and for a prototype it's fine. We're not doing that, and here's why.

If the pricing logic is a function inside the pricing agent, then the pricing agent is the only thing that can price. When the orchestrator needs a rate card, it has to go through the agent. When your finance team wants to check a number, they can't — it's buried in a prompt loop. And when you want to audit *what rules were applied*, you're reading model transcripts.

Instead, the tools live in their own servers, and the agents call them over a protocol called **MCP** — Model Context Protocol.

[SCREEN: three boxes — mcp_brand_style, mcp_licensing, mcp_market — with agents pointing at them.]

Three servers in this system. `mcp_brand_style` runs brand compliance checks. `mcp_licensing` owns vendors, rate cards, exclusivity contracts and executed contracts. `mcp_market` scans marketplaces and checks volume caps.

The thing I want you to notice: these are ordinary web services. They have URLs. They're deployed to Cloud Run. They have IAM policies. You can point anything at them — a different agent, a script, a dashboard. The business logic is a *service*, not a prompt.

And that gives you the property that matters most later: **you can govern them**. You can't put a policy on a Python function buried inside an agent's reasoning loop. You absolutely can put a policy on an HTTP endpoint.

---

## 09:30 — Why a registry, and why now

There's a third piece we set up in this step, and it's the one people skip: the **Agent Registry**.

The registry is a catalogue. Every MCP server and, later, every agent gets an entry: here's its name, here's its address, here's the interface it speaks.

Now — you might reasonably ask why. The agents get their URLs from environment variables. Why does anything need a catalogue?

[BEAT]

Two reasons, and the second is the real one.

The first is discovery. It's how the console populates its list of tools, how you find out what exists without grepping the codebase.

The second is that in Step 7, we put a **governed gateway** in front of everything, and that gateway is deny-by-default. It will only route traffic to destinations that are *in the registry*. Something not registered isn't just undiscoverable — it's unreachable.

So registration isn't bookkeeping. It's the enrolment step that makes governance possible. We do it now, for the MCP servers, and we do it again in Step 7 for the agents.

---

## 11:30 — Open Cloud Shell and get the code

Right. Let's build it.

[DO: open the Google Cloud console, click Activate Cloud Shell.]

Everything in this workshop runs in Cloud Shell. It already has `gcloud`, `python3` and `git`. One thing it no longer ships is `terraform` — there's a placeholder on the path that just prints install instructions, which is confusing the first time you hit it. Our init script handles that, so don't go installing anything yourself yet.

[DO: type the auth check.]

Let's confirm we're pointed at the right project.

```
gcloud auth list
gcloud config get-value project
```

You want your account showing as `ACTIVE`, and the project id should be the project you intend to spend money in. Worth two seconds of attention — everything after this lands in whatever that says.

[DO: clone.]

```bash
git clone https://github.com/weimeilin79/vibeflix-audit
cd vibeflix-audit
```

---

## 13:00 — The shape of the repo

[SCREEN: the directory tree from the lab.]

Before we run anything, thirty seconds on the layout, because knowing where things live makes the rest of the workshop much easier to follow.

`agents/` — the six ADK agents. One folder each.

`mcp_servers/` — the three tool servers we just talked about.

`packages/` — `vibeflix_common`, the shared library. It's split into four subpackages named for *who imports them*: `a2a/` for transport, `agent/` for ADK building blocks, `mcpserver/` for MCP-only helpers, and `platform/` for auth and telemetry, which both sides use. That naming is deliberate — when you're wondering whether you can import something, the folder name answers it.

`deploy/` — every deploy and verify script, the Terraform, and your `.env`.

`frontend/` — the React console.

`resource/` — seed data, including the legal documents that become a knowledge base in Step 4.

You'll mostly **read** `agents/` and `mcp_servers/`, and **run** things from `deploy/`.

---

## 14:30 — init.sh, and what it does for you

```
cd ~/vibeflix-audit
./init.sh
```

[DO: run it. Let it start.]

While that runs, let me tell you what it's doing, because it's doing more than the name suggests.

First, it **checks your environment before creating anything**. Every CLI this workshop needs — gcloud plus its alpha and beta components, python3, jq, curl, unzip, openssl, git — that you're authenticated, and that application-default credentials exist. If something's missing it stops *before* provisioning. That ordering matters: the worst version of this is a script that creates half your infrastructure and then dies on a missing binary.

Then it points gcloud at your project, creates the virtual environment, and installs every dependency — agent requirements, the legal RAG requirements, deploy requirements, and the shared `vibeflix-common` package. It installs a working terraform into `~/bin` if Cloud Shell's placeholder is in the way. And it writes `deploy/.env` — the config file every script in this workshop reads.

It takes a few minutes, most of it Python packages.

[BEAT]

**One habit to build now**, and this is the single most common way people lose twenty minutes on this workshop:

**Every new terminal tab needs `cd ~/vibeflix-audit` and `source ./env.sh`.**

A new Cloud Shell tab starts in your home directory with a clean environment. If you skip that, you're running Cloud Shell's *system* Python instead of the project's virtual environment. And the failure doesn't say "wrong Python" — it says `ImportError` from somewhere deep inside a Google library, and you'll spend real time chasing it.

Note the `source`. Running `./env.sh` does nothing useful, because a script can't change the shell that launched it. It'll tell you if you get it the wrong way round.

Every command block in this lab starts with those two lines. They're there so you can copy any block, into any tab, and have it work.

---

## 17:00 — What setup.sh actually provisions

```bash
cd ~/vibeflix-audit
source ./env.sh
./workshop/setup.sh
```

[DO: run it. This one takes several minutes — plan a jump cut.]

Nine steps, in order: preflight, enable APIs, foundations, buckets, Firestore, Pub/Sub, build and deploy the three MCP servers, and register them.

Three pieces are worth understanding rather than just watching scroll past.

**Firestore** is the mesh's database. It holds the registries the MCP servers read — brand terms, the legal registry, sourcing caps — and the `vendors` collection, which is the one thing agents actually *mutate* at runtime when they onboard someone.

**A Pub/Sub topic** carries telemetry. Every agent publishes events as it works, and in Step 6 the console subscribes to that stream — that's what makes the graph light up live.

**Artifact Registry** holds container images. The MCP servers and the console app are all built into images first.

[BEAT]

And now something I want to flag properly, because it will save you frustration.

**Every script in this workshop is safe to re-run.** If one stops with an error, fix what it reports and run the same command again. Completed work is detected and skipped, not repeated.

You will need that occasionally, and it's not your fault when you do. These are real cloud APIs, some of them in preview, and they sometimes return a transient internal error for reasons that have nothing to do with your project. The setup scripts retry those automatically now, and stop with a clear message if the retries don't help.

So when you see a red ✗, the response is: read it, and run `./workshop/setup.sh` again. It re-checks all nine steps and redoes only what's missing.

---

## 19:30 — Verify: the check that proves the point

[DO: run the verify.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step1.sh
```

This confirms the image registry, the telemetry topic, the Firestore database — and all three MCP servers are up.

But look at the last part of what it checks, because it's the most interesting line in the script. It confirms the MCP servers are up **and that they return 403**.

[BEAT]

That's not a bug being tolerated. That's the test passing.

Those services are deployed with `--no-allow-unauthenticated`. There is no public access. A caller needs `roles/run.invoker`, and right now nothing has it — because no agent exists yet to grant it to.

[SCREEN: paste an MCP URL into a browser tab, get the 403.]

Try it yourself. That 403 is the beginning of the security story we finish in Step 7. The tools that make the real decisions in this system are not on the open internet, and they never will be.

---

## 21:30 — Do and don't

Four things to take out of this step.

**Do put the deterministic logic in a tool server.** Not in the prompt, not in a helper function inside the agent. A URL you can point IAM at is worth an enormous amount later.

**Don't let the model decide anything you'd need to defend.** If someone could sue over it, or audit it, or if finance would want to reproduce it in a spreadsheet — that's a tool's job.

**Do re-run scripts when they fail.** Idempotency is a feature here. Treat a ✗ as a to-do, not a broken lab.

**Don't skip `cd` and `source ./env.sh` in a new tab.** I know. I'm saying it a third time because it is genuinely the most common way to lose time on this build.

---

## 22:30 — What you have, and what's next

[SCREEN: the architecture diagram with only the foundation layer lit.]

Right now you have three deterministic, IAM-gated tool servers, registered in the Agent Registry. A seeded database. A telemetry topic. An image registry.

What you don't have is a single agent. Everything so far is the boring, unglamorous layer — and it's deliberately first, because the interesting decisions in the next seven steps are only possible *because* this layer exists.

Next step, we build the first agent: brand style. It looks at a product mock-up, works out what it's looking at, and hands those facts to `mcp_brand_style` for the actual verdict. That's the fuzzy-versus-exact split, running for real, in about fifteen minutes.

See you there.

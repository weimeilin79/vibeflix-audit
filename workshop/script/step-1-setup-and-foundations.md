# Step 1 — Setup & Foundations

**Target runtime:** 20–24 min · **Lab section:** `Setup & Foundations`

---

## 00:00 — Cold open

[SCREEN: the finished console, mid-audit. Three agent boxes light up at once. Tool LEDs blink. A contract id appears.]

Six agents. One request. A decision that used to take three weeks.

A vendor wants to make a product. Is that allowed? Brand rules say one thing. The rate card says another. Somewhere there's an exclusivity contract nobody remembered. And a legal process that was never written down.

Sixty seconds later: a signed contract, or a clear reason why not.

[BEAT]

And none of this is faked for the demo.

Six agents, deployed separately. Each one has its own identity. They call three tool servers so locked down that if you open their URL in a browser right now, you get a 403. Try it later. You'll see.

[SCREEN: hard cut to an empty Cloud Shell.]

This is where we start. Nothing.

Today we don't build an agent. Today we build the ground the agents stand on. And I want you watching *why* we build it this way — because almost every decision in the next seven steps traces back to something we do in the next twenty minutes.

---

## 02:00 — The problem

Business problem first. The architecture only makes sense once you feel the pain.

Vibeflix licenses characters. A vendor shows up and says: I want to make vinyl figures of this character. North America. This royalty rate.

Somebody has to decide if that's allowed.

And that decision is hard in four separate ways.

Somebody checks the artwork against brand rules. Somebody checks the money — royalty rate, advance, minimum guarantee — against a rate card with tiers and modifiers. Somebody checks whether a competitor already holds an exclusive lock on that character, in that territory. And somebody has to know the legal process for onboarding a vendor into a brand-new category.

That last one? In most companies it isn't written down anywhere.

[BEAT]

Four kinds of expertise. Four people. One shared inbox. Three weeks.

So here's the tempting fix. Throw one big model at all of it. Hand it the rate card, the contracts, the artwork. Ask it to decide.

Don't.

And the reason why is the single most important idea in this entire workshop.

---

## 04:00 — The idea everything hangs off

There are two kinds of work buried in that decision. They fail in completely different ways.

The first kind is **fuzzy**.

Look at artwork. Say what it is. "That's a vinyl figure. There's no printed text on it." Read a messy Slack thread and work out what the process actually is.

Ask two people, you get slightly different words. Ask a model twice, same thing. That's fine. That's the nature of the work.

The second kind is **exact**.

Is 10% above or below a minimum of 10%? Is this vendor named on the exclusivity contract? Does 30,000 units qualify for a tier that starts at 100,000?

Same inputs, same answer. Every single time. And it has to match what finance gets with a spreadsheet.

[BEAT]

A model is excellent at the first kind. It is the wrong tool for the second. Not because it's bad — because it's probabilistic.

Think about what that means. A system that returns a different royalty rate on Tuesday than it returned on Monday isn't an AI system with a bug.

It's a system you cannot put a contract through. At all.

So here's the rule for this entire build:

**The model does the fuzzy work. Code does the deciding.**

The model reads the image and reports what it sees. A tool applies the rules and returns a verdict. The model can't argue with that verdict. And it can't compute one of its own.

[SCREEN: two columns — MODEL: extract, interpret, converse. TOOLS: compare, calculate, decide.]

Hold on to that split. Every step from here is a new place to apply it.

---

## 06:30 — Where the tools live

The exact work goes in tools. So where do the tools live?

Obvious answer: inside the agent. Python functions it imports. Works fine for a prototype.

We're not doing that. Here's why.

Put the pricing logic inside the pricing agent, and only that agent can price. The orchestrator has to go through the agent just to get a rate card. Finance can't check a number, because it's buried in a prompt loop. And when you want to audit which rules ran — you're reading model transcripts.

So the tools live in their own servers. The agents call them over **MCP**. Model Context Protocol.

[SCREEN: three boxes — mcp_brand_style, mcp_licensing, mcp_market.]

Three servers in this system. Brand checks. Licensing — vendors, rate cards, exclusivity contracts. And market — marketplace scans and volume caps.

Now look at what these actually are. Ordinary web services. They have URLs. They run on Cloud Run. They have IAM policies.

The business logic is a service. Not a prompt.

And that buys you the thing that matters most later. **You can govern them.**

You cannot put a policy on a Python function buried inside a reasoning loop. You absolutely can put a policy on an HTTP endpoint. Remember that. Step 7 depends on it.

---

## 09:00 — The registry

Third piece, and this is the one everyone skips: the **Agent Registry**.

It's a catalogue. Every MCP server — and later, every agent — gets an entry. Name, address, interface.

And you're probably thinking: why? The agents already get their URLs from environment variables.

[BEAT]

Two reasons. The second one is the real one.

First, discovery. It's how the console lists what tools exist without grepping the codebase.

Second — and here's the thing — in Step 7 we put a **gateway** in front of everything. That gateway is deny-by-default. It only routes traffic to destinations that are in the registry.

So anything unregistered isn't just hard to find.

It's unreachable.

Registration isn't paperwork. It's the enrolment step that makes governance possible. We do it now for the MCP servers. We do it again in Step 7 for the agents.

---

## 11:00 — Get the code

Let's build.

[DO: Activate Cloud Shell.]

Everything runs in Cloud Shell. It ships with `gcloud`, `python3` and `git`.

It does not ship terraform any more. There's a placeholder sitting on the path that just prints install instructions. Confusing the first time you hit it. Our init script handles it — don't go installing anything yourself.

[DO: run the auth check.]

```
gcloud auth list
gcloud config get-value project
```

Your account should say `ACTIVE`. The project should be the one you intend to spend money in.

Look at it. Two seconds. Everything after this lands wherever that says.

[DO: clone.]

```bash
git clone https://github.com/weimeilin79/vibeflix-audit
cd vibeflix-audit
```

---

## 12:30 — The repo

[SCREEN: the directory tree.]

Thirty seconds on the layout. It makes everything after this easier to follow.

`agents/` — the six agents, one folder each.

`mcp_servers/` — the three tool servers.

`packages/` — the shared library. Split into four subpackages, named for *who imports them*. Transport. ADK building blocks. MCP-only helpers. And auth and telemetry, used by both sides.

That naming is deliberate. When you're wondering whether you can import something, the folder name answers it.

`deploy/` — deploy scripts, verify scripts, Terraform, and your `.env`.

`frontend/` — the React console.

`resource/` — seed data. Including the legal documents that become a knowledge base in Step 4. Keep those in mind. They're the star of a later episode.

You'll mostly **read** `agents/` and `mcp_servers/`. You'll **run** things from `deploy/`.

---

## 14:00 — init.sh

```
cd ~/vibeflix-audit
./init.sh
```

[DO: run it.]

While that's going — here's what it's actually doing. It's more than the name suggests.

First, it **checks your environment before it creates anything**. Every CLI this workshop needs. That you're authenticated. That application-default credentials exist.

If something's missing, it stops. Before it builds a single thing.

That ordering matters. Picture the alternative: a script that provisions half your infrastructure and then dies on a missing binary. Now you're cleaning up.

Then it points gcloud at your project. Creates the virtual environment. Installs every dependency. Installs a working terraform if the placeholder is in the way. And writes `deploy/.env` — the config file every script in this workshop reads.

Few minutes. Mostly Python packages.

[BEAT]

Now. One habit to build right now.

This is the single most common way people lose twenty minutes on this workshop.

**Every new terminal tab needs `cd ~/vibeflix-audit` and `source ./env.sh`.**

A new tab starts in your home directory with a clean environment. Skip those two lines, and you're running Cloud Shell's *system* Python instead of the project's.

And watch what that failure looks like. It doesn't say "wrong Python". It says `ImportError`. From somewhere deep inside a Google library. You will chase that for a while.

Note the `source`. Running `./env.sh` on its own does nothing — a script can't change the shell that launched it. It'll tell you if you get it backwards.

Every command block in this lab starts with those two lines. That's on purpose. Copy any block, into any tab, and it works.

---

## 16:30 — setup.sh

```bash
cd ~/vibeflix-audit
source ./env.sh
./workshop/setup.sh
```

[DO: run it. Several minutes. Plan a jump cut.]

Nine steps. Preflight. Enable APIs. Foundations. Buckets. Firestore. Pub/Sub. Build and deploy the three MCP servers. Register them.

Three pieces are worth understanding instead of watching scroll past.

**Firestore** is the database. It holds the registries the MCP servers read. It also holds the vendors collection — the one thing agents actually *change* at runtime, when they onboard somebody.

**A Pub/Sub topic** carries telemetry. Every agent publishes events as it works. In Step 6 the console subscribes to that stream. That's what makes the graph light up live.

**Artifact Registry** holds container images.

[BEAT]

Now, something that will save you real frustration.

**Every script in this workshop is safe to re-run.** If one stops with an error, fix what it reports and run the exact same command again. Finished work gets detected and skipped.

And you will need that sometimes. It won't be your fault.

These are real cloud APIs. Some are in preview. Sometimes they return a transient internal error for reasons that have nothing to do with your project. The setup scripts retry those automatically now, and stop with a clear message if retrying doesn't help.

So when a red ✗ shows up: read it, then run `./workshop/setup.sh` again. It re-checks all nine steps and redoes only what's missing.

A ✗ is a to-do. Not a broken lab.

---

## 19:00 — Verify, and the check that proves the point

[DO: run it.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step1.sh
```

It checks the image registry. The telemetry topic. The Firestore database. All three MCP servers.

Now look at the last check. It confirms the MCP servers are up **and that they return 403**.

[BEAT]

That's not a bug we're tolerating.

That's the test passing.

Those services deploy with no public access at all. A caller needs the invoker role, and right now nothing has it — because no agent exists yet to grant it to.

[SCREEN: paste an MCP URL into a browser tab. 403.]

Go try it yourself.

That 403 is the opening line of the security story we finish in Step 7. The tools that make the real decisions in this system are not on the open internet. And they never will be.

---

## 21:00 — Do and don't

**Do put the exact logic in a tool server.** Not the prompt. Not a helper function inside the agent. A URL you can point IAM at is worth a lot later.

**Don't let the model decide anything you'd have to defend.** If someone could sue over it, audit it, or reproduce it in a spreadsheet — that's a tool's job.

**Do re-run scripts when they fail.** Idempotency is a feature here.

**Don't skip `cd` and `source ./env.sh` in a new tab.** Third time I've said it. Still the number one time sink.

---

## 22:00 — What you have

[SCREEN: architecture diagram, foundation layer lit.]

Three tool servers. Deterministic. IAM-gated. Registered. A seeded database. A telemetry topic. An image registry.

And zero agents.

That's on purpose. Every interesting decision in the next seven steps is only possible because this unglamorous layer exists first.

Next: the first agent. Brand style.

It looks at a product mock-up. Works out what it's looking at. And hands those facts to a tool for the actual verdict.

Fuzzy versus exact. Running for real. In about fifteen minutes.

See you there.

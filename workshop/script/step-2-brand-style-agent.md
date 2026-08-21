# Step 2 — The Brand Style Agent

**Target runtime:** 22–26 min · **Lab section:** `The Brand Style Agent`

---

## 00:00 — Cold open

[SCREEN: a product mock-up. Then a JSON report beside it — status, extracted, checks_run, findings.]

Your first agent has one job. Look at a product mock-up. Decide if it follows the brand rules.

Sounds like one task.

It's two. And this entire step is about keeping them apart.

---

## 01:00 — Meet the intern

Here's the job the way a human does it today.

[SCREEN: comic panels — a vendor submits a mock-up. A coordinator squints at it. Types into a form.]

A vendor sends artwork. A coordinator opens it. Reads the printed text off the image by eye. Works out what kind of product it is — vinyl figure, plush, apparel. Types those facts into a compliance checker.

The checker applies the rules. Returns a verdict.

[BEAT]

Now catch what just happened in that description.

**The checking is already automated.** The rules exist. They already run.

The bottleneck is a human *looking*. And a human *typing*.

That's what we're replacing: the eyes and the fingers.

And I'm hammering this because it's the most common mistake in agent projects. People look at a workflow like this and automate the **decision** — because that feels like the impressive part.

But the decision was already deterministic. Already correct. Automating it with a model makes it slower, more expensive, and impossible to reproduce.

You automated the one part that was working.

---

## 03:30 — Fuzzy and exact, precisely

Let's sharpen the split. We use it in every remaining step.

**Non-deterministic work.** Looking at the mock-up. Reading what's on it. The printed text. The medium. That's judgment. Two people, two slightly different answers. A model twice, same thing. Fine. That's what vision models are for.

**Deterministic work.** Checking those facts against the rules. Is this font approved? Is this medium allowed?

Same inputs, same answer. Always. It's a lookup.

And a model should **never** be the thing that decides it. Because it will occasionally make the answer up. And it will do it fluently.

[SCREEN: the BEFORE / NOW diagram.]

So: the agent's vision reads the mock-up and fills in exactly the fields the intern used to type. Then hands them to the same checker that was always there.

Model output: facts. Tool output: verdict.

---

## 05:30 — Steal this trick

[SCREEN: the `run_brand_audit` tool signature.]

Open the brand style MCP server. Look at the tool signature.

Its parameters are — almost exactly — the fields on the form the coordinator used to fill in. Image reference. Text found on it. Product medium. Character. Market.

That's the method.

**When you're replacing a human step, the form they filled in is your tool signature.**

It tells you exactly what the model has to produce. And — more useful — exactly where the model's job stops.

Everything on the form: model's job. Everything behind the form: tool's job.

Stuck drawing that line in your own system? Go find the form. The ticket template. The spreadsheet columns. The boundary is already documented. Nobody ever thought of it as an API.

---

## 07:30 — Quick ADK tour

[SCREEN: the ADK concept diagram.]

Fast orientation. This vocabulary shows up constantly from here.

An **Agent** is a model, plus an instruction, plus tools. It runs a loop. Read the situation. Decide whether to call a tool. Call it. Look at the result. Continue or answer.

**Tools** are what it can actually do. Ours come from MCP servers.

An **instruction** is the standing brief. Who you are. What you're deciding. What shape your answer takes.

Two more coming later. **Skills** — written procedures — in Step 3. And **Workflow** — a graph of nodes and edges — in Step 5.

Today: one agent, one tool, one job.

---

## 09:00 — Inside agent.py

[SCREEN: `agents/brand_style/agent.py`.]

Three things to point at.

**The model.** Gemini, with vision. It has to actually look at an image.

**The instruction.** And here's what matters — notice what it *doesn't* say. It tells the agent to extract what it sees and call the audit tool. It never says what the brand rules are.

That's deliberate. Put the rules in the prompt and the model starts applying them itself. You've moved a deterministic decision back into the fuzzy layer, and you probably won't notice for weeks.

Keep the rules out of the model's reach and it can't be tempted.

**The tools list.** One MCP toolset. Filtered to one tool. Nothing else. The agent cannot call anything you didn't hand it.

There's also a **schema guard** — a callback that catches the case where the model answers in prose instead of the structured report, and rewrites it into a valid shape.

Worth knowing that exists. Models occasionally decide to be helpful in English. A deterministic net around the output means that doesn't become an outage.

---

## 11:00 — Deploy

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py brand_style
python deploy/collect_agent_identities.py
```

[DO: start it. Few minutes.]

Don't sit and watch this. Leave it running. We're jumping ahead to the local Dev UI, which needs nothing from this deploy, and coming back when it's done.

But before we jump — that second command. Everything after it depends on the file it writes.

---

## 12:30 — The address book

Deploying an agent creates two facts that **only exist after the deploy**. Nobody can predict them beforehand.

**Where it lives** — its engine id, minted by Agent Runtime. And **who it is** — its identity principal.

`collect_agent_identities.py` asks Vertex AI for every engine in your project and writes both down.

[SCREEN: the JSON — engine and principal.]

That file is how the rest of the workshop finds things.

The grant script reads the **principal**, so it grants roles to the right identity. The next agent you deploy reads the **engine** of its peers, to build A2A URLs. The gateway setup reads it to register destinations. And in a minute, you read it to talk to your own agent.

So it gets regenerated after **every** deploy. A fact that didn't exist sixty seconds ago now has to be written down for the next step to use.

[BEAT]

This is also why deploy order matters later. Agents that call each other can't all know each other's addresses up front — because an engine id doesn't exist until its engine does.

Deploy. Collect. Then deploy whatever needed that address.

---

## 14:00 — Grant it access

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh brand-style
```

The engine exists. And its identity can do **nothing at all**.

This grants exactly what it needs. Two different things are happening, and they work differently.

**One — what the agent may do.** These roles land on this agent's own principal. Nobody else's.

Call Gemini — without it, the agent can't think. Write its own sessions — miss this one and every task poll 401s and the agent hangs forever. Read the registry. Emit traces. Publish telemetry events, which is what lights up the graph in Step 8.

**Two — how it reaches the MCP servers.** This one is indirect. And the reason is genuinely interesting.

[BEAT]

**An agent identity is not a service account.**

Cloud Run's IAM check wants an OIDC token from a service account. An agent principal doesn't have one to offer.

So there's one shared service account in the middle.

[SCREEN: the impersonation diagram.]

The agent is allowed to *impersonate* the invoker service account. It mints a token with it. Calls the MCP server with that. Cloud Run sees a service account it trusts.

Nothing has been opened up. Hit that MCP URL yourself and you still get a 403. Exactly like Step 1.

That's least privilege in action. Each agent grants its own access, keyed to its own principal. No blanket "any agent can do anything".

And notice what is **not** granted. This agent cannot call any other agent. Agent-to-agent traffic is governed by the gateway in Step 7. Until then, each agent reaches Gemini and the tool servers. Nothing else.

---

## 17:00 — Drive it locally

[DO: second tab.]

```bash
cd ~/vibeflix-audit
./run_local.sh mcp
```

Three MCP servers, running locally.

[DO: third tab.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/brand_style
```

That `--allow_origins` flag matters. Cloud Shell's Web Preview doesn't serve from localhost — it proxies through a different address. Different origin.

Without the flag, the page loads and then the very first call fails with a 403. Looks like your agent is broken. It's the browser's cross-origin rules.

[DO: Web Preview → port 8000. Pick brand_style. Audit the default mock-up.]

---

## 19:00 — Read the answer

[SCREEN: the returned report.]

Here it is. And it's the concept from the top of this video, made real.

`extracted` is the **model's** work. It looked at the artwork and reported what it saw. The medium. The printed text — empty on this one. Run it twice, the wording might shift.

That's the fuzzy half. That's the intern's eyes.

Everything else is the **tool's** work. `checks_run` lists the deterministic checks, in the server's own fixed order. `status` is the verdict. The model didn't decide it and can't override it. `findings` is empty because nothing failed.

[BEAT]

Now let's break it on purpose. This is the part that proves the design.

[DO: change the image link to a bucket outside the project. Re-run.]

Point the image somewhere outside your buckets. Re-run.

`status: rejected`. And look at `checks_run`.

**One check ran.** Asset source.

The asset-source gate runs first and short-circuits everything else. Unapproved artwork never gets inspected at all. That ordering is a policy decision baked into the tool. The model didn't pick it and couldn't have.

---

## 21:00 — Verify the real thing

[DO: Ctrl+C the adk web tab. Leave the MCP tab running — the next step reuses it.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step2.sh
```

Confirms the engine is deployed with an agent identity. Now talk to it in the cloud.

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/ask_agent.py brand-style \
  "Audit this mock-up. image: gs://<bucket>/vendor_request_refine.png, character: grogu, market: NA"
```

[SCREEN: the report from the deployed engine.]

Same shape. This time from an engine running in Agent Runtime.

**Your status might differ from mine. That's the lesson.**

The agent decides the medium by looking at the artwork. One run it says "vinyl figures" and comes back compliant. Another run it says "artwork" — which isn't on the approved list — and the check flags it.

The fuzzy half varies. The rule applied to it never does.

A flagged result here is the system working.

You might also see a line about A2A not propagating a trace. That's the client saying there's no trace running on your laptop, so the engine starts its own. Expected.

---

## 23:30 — Do and don't

**Do use the human's form as your tool signature.** It tells you where the model's job ends.

**Don't put the rules in the prompt.** If the model can see them, it will start applying them.

**Do give an agent exactly one tool** when it has one job. A filtered toolset is a security boundary.

**Don't panic at a flagged result.** Variation in extraction is expected. The verdict *given* that extraction must never vary.

**Do run collect after every deploy.** Everything downstream reads that file.

---

## 25:00 — Recap and hook

You built an agent that automates perception and data entry, and hands the deciding to a tool that was already right. It runs as its own identity. It reaches its tool server by impersonating a service account, because agent identities can't authenticate to Cloud Run directly.

Next: deal pricing. And it raises the difficulty.

Instead of one tool call, the agent runs a **bounded loop** inside itself. It follows a written procedure called a Skill. And it has to reconcile a vendor's *claim* against a rate card.

A vendor is about to tell us they qualify for a discount.

They don't.

See you there.

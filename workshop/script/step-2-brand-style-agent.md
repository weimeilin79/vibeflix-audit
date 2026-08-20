# Step 2 — The Brand Style Agent

**Target runtime:** 22–26 min · **Lab section:** `The Brand Style Agent`

---

## 00:00 — Cold open

[SCREEN: a product mock-up image. Then, beside it, a JSON report with `status`, `extracted`, `checks_run`, `findings`.]

Your first agent does one job: look at a product mock-up and decide whether it follows Vibeflix's brand rules.

That sounds like one task. It's two, and the entire step is about keeping them apart.

---

## 01:00 — Meet the intern

Before the agent, here's the job as a human does it.

[SCREEN: the comic panels — a vendor submitting a mock-up, a coordinator squinting at it, typing into a form.]

A vendor sends in artwork. A coordinator opens it, reads off the printed text by eye, identifies what kind of product it is — vinyl figure, plush, apparel — and types those facts into a compliance checker. The checker applies the rules and returns a verdict.

[BEAT]

Now notice something about that description. **The checking is already automated.** The rules already exist, in a tool, and they already run. That's not the bottleneck.

The bottleneck is a human **looking** and a human **typing**. Someone scanning artwork and transcribing what they see into a form.

That's the part we're replacing. Not the decision — the perception and the data entry.

I'm labouring this because it's the most common mistake I see in agent projects. People look at a workflow like this and automate the *decision*, because that feels like the impressive part. But the decision was already deterministic and already correct. Automating it with a model makes it slower, more expensive, and non-reproducible. The eyes and the fingers were the expensive part.

---

## 03:30 — Deterministic vs non-deterministic, precisely

Let's make that split sharp, because we apply it in every remaining step.

**Non-deterministic work** — looking at the mock-up and reading what's on it. The printed text. The product medium. This is judgment. Ask two people, you'll get slightly different words. Ask a model twice, same thing. That's fine, that's the nature of the task, and it's exactly what a vision model is good at.

**Deterministic work** — checking those facts against the rules. Is this font on the approved list? Is this medium allowed? Given the same inputs, the answer is always the same. It's a lookup. And a model should **never** be the thing that decides it, because it will occasionally make the answer up, and it will do so fluently.

[SCREEN: BEFORE (manual) / NOW (agent + MCP) diagram from the lab.]

So the shape is: the agent's vision reads the mock-up and fills in exactly the fields the intern used to type. Then it hands them to the same checker that was always there.

The model's output is *facts*. The tool's output is a *verdict*.

---

## 05:30 — The tool signature is the intern's form

Here's a design trick worth stealing.

[SCREEN: `@mcp.tool()` decorated `run_brand_audit` signature.]

Open the brand style MCP server and look at the tool signature. Its parameters are — almost exactly — the fields on the form the coordinator used to fill in. Image reference, the text found on it, the product medium, the character, the market.

That's not a coincidence, it's the method. **When you're replacing a human step, the form they filled in is your tool signature.** It tells you precisely what the model needs to produce and — just as importantly — where the model's job stops.

Everything on that form: model's job. Everything behind the form: tool's job.

If you're ever unsure where to draw the line in your own system, go find the form, the ticket template, the spreadsheet columns. The boundary is already documented; somebody just never thought of it as an API.

---

## 07:30 — A quick tour of ADK

[SCREEN: the ADK concept diagram — Agent, tools, instruction, Skills, Workflow.]

Quick orientation, because the vocabulary shows up constantly from here.

An **Agent** in ADK is a model plus an instruction plus a set of tools. It runs a loop: read the situation, decide whether to call a tool, call it, look at the result, continue or answer.

**Tools** are what it can actually do. Ours come from MCP servers.

An **instruction** is the standing brief — who you are, what you're deciding, what shape your answer takes.

Two more we'll meet later: **Skills**, which are written procedures the agent follows, in Step 3. And **Workflow**, a graph of nodes and edges, in Step 5.

For now: one agent, one tool, one job.

---

## 09:00 — Inside agent.py

[SCREEN: `agents/brand_style/agent.py`.]

Three things worth pointing at.

The **model** — a Gemini model with vision. It has to actually look at an image, so this isn't a text-only choice.

The **instruction** — notice what it does and doesn't say. It tells the agent to extract what it sees and call the audit tool. It does *not* tell it what the brand rules are. Deliberately. If the rules were in the prompt, the model would start applying them itself, and you'd have moved a deterministic decision back into the fuzzy layer. Keep the rules out of the model's reach and it can't be tempted.

The **tools list** — one MCP toolset, filtered to `run_brand_audit`. Nothing else. The agent can't call anything you didn't hand it.

There's also a **schema guard** — a callback that catches the case where the model answers in prose instead of the structured report, and rewrites it into a valid `needs_input` shape. Worth knowing it exists. Models occasionally decide to be helpful in English; a deterministic net around the output means that doesn't become an outage.

---

## 11:00 — Deploy it

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py brand_style
python deploy/collect_agent_identities.py
```

[DO: start it. It takes a few minutes.]

Don't sit and watch this. Leave it running in this tab — we're going to skip ahead to the local Dev UI, which needs nothing from this deploy, and come back when it's done.

But before we jump, the second command is worth understanding, because everything after it depends on the file it writes.

---

## 12:30 — agent_identities.json, the mesh's address book

Deploying an agent produces two facts that **only exist after the deploy**, and that nobody can predict beforehand.

**Where it lives** — its engine id, minted by Agent Runtime. And **who it is** — its identity principal, the first-class identity it runs as.

`collect_agent_identities.py` asks Vertex AI for every `vibeflix-*` engine in your project and writes both down, one entry per agent.

[SCREEN: the JSON example — engine and principal for `vibeflix-brand-style`.]

That file is how the rest of the workshop finds things. The grant script reads the **principal**, so it grants roles to the right identity. The next agent you deploy reads the **engine** of its peers, to build its A2A URLs. The gateway setup reads it to register each agent as a callable destination. And in a moment, you'll read it to talk to your own agent.

So it's regenerated after **every** deploy — a fact that didn't exist a minute ago now has to be written down for the next step to use.

[BEAT]

This is also why deploy order matters later on. Agents that call each other can't all know each other's addresses up front, because an engine id doesn't exist until its engine does. Deploy, collect, then deploy whatever needed that address.

---

## 14:00 — Grant the agent its own access

[DO: assuming the deploy has finished, or jump-cut back to it.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh brand-style
```

The engine exists now, but its identity can do **nothing at all**. This grants exactly what it needs, and there are two different things happening — they work differently and it's worth separating them.

**One: what the agent itself may do.** These roles go on `vibeflix-brand-style`'s own principal, nobody else's. `aiplatform.user` so it can call Gemini — without it, the agent can't think. `agentContextEditor` so it can write its own sessions — miss this one and every task poll 401s and the agent hangs forever. Registry viewer, so it can read the list of permitted destinations. Logging and monitoring, so it can emit its traces. And publish rights on the telemetry topic, which is what lights up the live graph in Step 8.

**Two: how it reaches the MCP servers.** This one is indirect, and the reason is genuinely interesting.

[BEAT]

**An agent identity is not a service account.** Cloud Run's IAM check wants an OIDC token from a service account, and an agent principal doesn't have one to offer.

So there's one shared service account in the middle.

[SCREEN: the impersonation diagram — agent principal → may impersonate → invoker SA → may call → MCP servers.]

The agent is allowed to *impersonate* the invoker service account. It mints an OIDC token with it, and calls the MCP server with that. Cloud Run sees a service account it trusts.

Nothing has been opened to the public. Hit the MCP URL yourself and you still get a 403, exactly as in Step 1.

This is **least privilege in action**: each agent grants its own access as it's deployed, keyed to its own principal. No blanket "any agent can do anything".

And note what is *not* granted here: this agent cannot call any **other agent**. Agent-to-agent traffic is governed by the Agent Gateway in Step 7. Until then, each agent can reach Gemini and the tool servers, and nothing else.

---

## 17:00 — Try it locally in the Dev UI

While the cloud deploy runs, let's drive the agent on this machine.

[DO: second tab.]

```bash
cd ~/vibeflix-audit
./run_local.sh mcp
```

That brings the three MCP servers up locally on ports 9002 to 9004.

[DO: third tab.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/brand_style
```

That `--allow_origins` flag matters. Cloud Shell's Web Preview doesn't serve the page from localhost — it proxies through a `cloudshell.dev` address, which is a *different origin*. Without the flag the page loads and then the very first call fails with a 403, which looks like your agent is broken when it's just the browser's cross-origin rules.

[DO: Web Preview → Change port → 8000. Pick brand_style. Ask it to audit the default mock-up.]

---

## 19:00 — Read the reply as two halves

[SCREEN: the returned `BrandStyleReport` JSON.]

Here's the answer, and it's the concept from the top of this video made concrete.

`extracted` is the **model's** work. It looked at the artwork and reported what it saw — the medium, and the printed text, which is empty on this mock-up. Ask it twice and the wording could differ slightly. That's the non-deterministic half. That's the intern's eyes.

Everything else is the **tool's** work. `checks_run` lists the deterministic checks the MCP server ran, in its own fixed order. `status` is its verdict — compliant, flagged, or rejected. The model didn't decide that and can't override it. Same inputs, same answer, every time. `findings` is empty here because nothing failed; each failed check appends an entry naming the element, the issue type and a severity.

[BEAT]

**Now let's break it on purpose**, because this is the part that proves the design.

[DO: change the image link to a bucket outside the project, re-run.]

Point the image at something outside your buckets and re-run. You get `"status": "rejected"` — and look at `checks_run`. **Only one check ran.** `asset_source`.

The asset-source gate runs first and short-circuits everything else, so unapproved artwork is never even inspected. That ordering is a policy decision baked into the tool. The model didn't choose it and couldn't have.

---

## 21:00 — Verify against the deployed engine

[DO: stop the adk web tab with Ctrl+C. Leave the MCP tab running — the next step reuses it.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step2.sh
```

That confirms the engine is deployed with an agent identity. Now let's talk to the real thing in the cloud:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/ask_agent.py brand-style \
  "Audit this mock-up. image: gs://<bucket>/vendor_request_refine.png, character: grogu, market: NA"
```

[SCREEN: the returned report from the deployed engine.]

Same shape of report, this time from an engine running in Agent Runtime.

**Your `status` may differ from mine, and that's the lesson.** The agent decides the medium by *looking at the artwork*. On one run it says "vinyl figures" and comes back compliant. On another it says "artwork" — which isn't on the approved list — and the deterministic check flags it.

The fuzzy half varies. The rule applied to it never does. A `flagged` result here is the system working, not a failure.

You may also see a line about A2A not propagating a trace parent. That's the client saying there's no trace running on your laptop, so the engine starts its own. Expected, not an error.

---

## 23:30 — Do and don't

**Do use the human's form as your tool signature.** It tells you exactly where the model's job ends.

**Don't put the rules in the prompt.** If the model can see the rules, it will start applying them, and you've lost the split.

**Do give the agent exactly one tool** when it has one job. A filtered toolset is a security boundary, not just tidiness.

**Don't panic at a `flagged` result.** Non-determinism in the extraction is expected. What must never vary is the verdict *given* the extraction.

**Do run `collect_agent_identities.py` after every deploy.** Everything downstream reads that file.

---

## 25:00 — Recap and bridge

You've built an agent that automates perception and data entry, and hands the deciding to a tool that was already correct. It runs as its own identity, with the narrowest set of permissions that lets it work, and it reaches its tool server by impersonating a service account — because agent identities can't authenticate to Cloud Run directly.

Next step is the deal pricing agent, and it raises the difficulty in an interesting way. Instead of one tool call, the agent runs a **bounded loop** inside itself, following a written procedure called a Skill — and it has to reconcile a vendor's *claim* against a rate card. Still with the arithmetic firmly in the tool.

See you there.

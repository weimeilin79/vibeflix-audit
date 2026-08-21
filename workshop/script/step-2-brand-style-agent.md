# Step 2 — The Brand Style Agent

**Target runtime:** 22–26 min · **Lab section:** `The Brand Style Agent`

---

## 00:00 — Cold open

[SCREEN: a product mock-up. Then a JSON report beside it — status, extracted, checks_run, findings.]

The first agent we build has one job, which is to look at a product mock-up and decide whether it follows Vibeflix's brand rules. That sounds like a single task, but it's actually two, and keeping them apart is what this entire step is about.

---

## 01:00 — How a person does this job today

[SCREEN: comic panels — a vendor submits a mock-up, a coordinator squints at it, types into a form.]

Before we automate anything, it's worth watching how the job is done by hand.

A vendor sends in artwork. A coordinator opens it, reads the printed text off the image by eye, works out what kind of product it is — a vinyl figure, a plush toy, apparel — and types those facts into a compliance checker. The checker applies the rules and returns a verdict.

The important detail in that description is that the checking is already automated. The rules exist, they already run, and they're already correct. What costs time is a person looking at an image and a person typing what they saw into a form, and those are the two things we're replacing.

I'm dwelling on this because the opposite mistake is extremely common in agent projects. People look at a workflow like this one, decide the interesting part is the decision, and automate that. The decision was already deterministic and already reliable, so replacing it with a model makes the system slower, more expensive and impossible to reproduce, while the actual bottleneck — the eyes and the fingers — stays exactly where it was.

---

## 03:30 — The split, stated carefully

Let me sharpen the distinction, because we apply it in every remaining step.

The non-deterministic work is looking at the mock-up and reading what's on it: the printed text, the product medium. That's judgment. Two people will describe the same image slightly differently, and a model will do the same thing across two runs. That variation is inherent to the task, and vision models are good at exactly this.

The deterministic work is checking those facts against the rules. Is this font on the approved list? Is this medium allowed for this character? Given the same inputs the answer is always the same, because it's a lookup. A model should never be the component that decides it, because it will occasionally invent an answer and it will do so fluently enough that nobody notices.

[SCREEN: the BEFORE / NOW diagram.]

So the shape we're building is that the agent's vision reads the mock-up and fills in exactly the fields the coordinator used to type, and then hands them to the same checker that was always there. The model produces facts and the tool produces the verdict.

---

## 05:30 — A trick worth stealing

[SCREEN: the `run_brand_audit` tool signature.]

Open the brand style MCP server and look at the signature of the audit tool. Its parameters are almost exactly the fields on the form the coordinator used to fill in — the image reference, the text found on it, the product medium, the character and the market.

That correspondence is the method rather than a coincidence. When you're replacing a step that a human used to do, the form they filled in is your tool signature. It tells you precisely what the model has to produce, and more usefully it tells you where the model's job stops. Everything on the form is the model's work, and everything behind the form is the tool's.

If you're ever unsure where to draw that line in your own system, go and find the form, or the ticket template, or the spreadsheet columns. Somebody documented that boundary years ago without thinking of it as an API.

---

## 07:30 — A quick tour of ADK

[SCREEN: the ADK concept diagram.]

A short orientation, because this vocabulary comes up constantly from here on.

An Agent in ADK is a model, an instruction and a set of tools. It runs a loop where it reads the situation, decides whether to call a tool, calls it, looks at the result, and then either continues or answers.

Tools are what it can actually do, and ours come from the MCP servers. The instruction is its standing brief: who it is, what it's deciding and what shape its answer should take.

There are two more concepts we'll meet later. Skills, which are written procedures an agent follows, arrive in Step 3, and Workflow, which is a graph of nodes and edges, arrives in Step 5. For today we have one agent, one tool and one job.

---

## 09:00 — Reading agent.py

[SCREEN: `agents/brand_style/agent.py`.]

There are three things in this file worth pointing at.

The model is a Gemini model with vision, because the agent has to actually look at an image rather than read a description of one.

The instruction is more interesting for what it leaves out than for what it contains. It tells the agent to extract what it sees and call the audit tool, and it never states what the brand rules are. That's deliberate, because a model that can see the rules will start applying them itself, and you'd have quietly moved a deterministic decision back into the fuzzy layer without anyone noticing for weeks. Keeping the rules out of the model's reach removes the temptation.

The tools list contains one MCP toolset, filtered down to the single audit tool, so the agent has no way to call anything you didn't hand it.

There's also a schema guard, which is a callback that catches the case where the model answers in prose instead of the structured report and rewrites it into a valid shape. It's worth knowing that exists, because models occasionally decide to be helpful in English, and a deterministic net around the output stops that from becoming an outage.

---

## 11:00 — Deploying it

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py brand_style
python deploy/collect_agent_identities.py
```

[DO: start it. Few minutes.]

Don't sit and watch this one. Leave it running in this tab, because we're going to jump ahead to the local Dev UI, which needs nothing from the cloud deploy, and come back when it's finished.

Before we jump, though, the second command deserves an explanation, because everything after it depends on the file it writes.

---

## 12:30 — The address book

Deploying an agent produces two facts that only exist after the deploy has finished and that nobody can predict beforehand: where it lives, which is the engine id minted by Agent Runtime, and who it is, which is its identity principal.

The collect script asks Vertex AI for every Vibeflix engine in your project and writes both of those down, one entry per agent.

[SCREEN: the JSON — engine and principal.]

That file is how the rest of the workshop finds things. The grant script reads the principal so it can grant roles to the right identity. The next agent you deploy reads the engines of its peers so it can build its A2A URLs. The gateway setup reads it to register each agent as a callable destination. And in a few minutes you'll read it yourself to talk to your own agent.

Because of that it gets regenerated after every single deploy, since a fact that didn't exist sixty seconds ago now has to be written down for the next step to use.

This is also why deploy order matters later in the workshop. Agents that call each other can't all know each other's addresses up front, because an engine id doesn't exist until its engine does, so the pattern becomes deploy, collect, then deploy whatever needed that address.

---

## 14:00 — Granting it access

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh brand-style
```

The engine exists at this point, but its identity is allowed to do absolutely nothing, and this script grants exactly what it needs. Two separate things happen here and they work differently.

The first is what the agent itself may do, and those roles land on this agent's own principal. It gets permission to call Gemini, without which it can't think at all. It gets permission to write its own sessions, and missing that one causes every task poll to return a 401 and the agent to hang indefinitely. It gets read access to the registry, permission to emit traces and metrics, and permission to publish to the telemetry topic, which is what lights up the live graph in Step 8.

The second is how it reaches the MCP servers, and that one is indirect for a reason worth understanding. An agent identity is a different kind of thing from a service account. Cloud Run's IAM check wants an OIDC token issued by a service account, and an agent principal has none to offer.

[SCREEN: the impersonation diagram.]

So there's a single shared service account sitting in the middle. The agent is granted permission to impersonate it, mints a token with it, and calls the MCP server using that token, at which point Cloud Run sees a service account it already trusts.

Nothing has been opened up in the process. If you hit that MCP URL yourself you'll still get a 403, exactly as you did in Step 1. This is least privilege working as intended, where each agent grants its own access keyed to its own principal, and there's no blanket rule saying any agent can reach anything.

The reach this grants stops at Gemini and the tool servers. Agent-to-agent traffic is governed separately, by the Agent Gateway we set up in Step 7, so until then that's the whole of what this agent can touch.

---

## 17:00 — Driving it locally

[DO: second tab.]

```bash
cd ~/vibeflix-audit
./run_local.sh mcp
```

That brings the three MCP servers up on your machine.

[DO: third tab.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/brand_style
```

The allow-origins flag matters here. Cloud Shell's Web Preview doesn't serve the page from localhost — it proxies it through a cloudshell.dev address, which counts as a different origin. Without the flag the page loads and then the very first call fails with a 403, which looks like a broken agent when it's actually the browser's cross-origin rules.

[DO: Web Preview → port 8000. Pick brand_style. Audit the default mock-up.]

---

## 19:00 — Reading the answer

[SCREEN: the returned report.]

Here's what comes back, and it's the concept from the start of this video made concrete.

The `extracted` block is the model's work. It looked at the artwork and reported what it found: the medium, and the printed text, which is empty on this particular mock-up. Run it twice and the wording might shift slightly, because that's the fuzzy half of the job and it's doing what the coordinator's eyes used to do.

Everything else is the tool's work. The `checks_run` list shows the deterministic checks the MCP server ran, in the server's own fixed order, and `status` is its verdict. The model didn't choose that verdict and has no way to override it. The `findings` list is empty here because nothing failed, and each failed check would add an entry naming the element, the issue type and a severity.

Now let's break it deliberately, because that's what proves the design works.

[DO: change the image link to a bucket outside the project. Re-run.]

Point the image at something outside your own buckets and run it again. The status comes back as rejected, and if you look at `checks_run` you'll see that only one check ran, the asset-source check.

That gate runs first and short-circuits everything after it, so unapproved artwork never gets inspected at all. That ordering is a policy decision baked into the tool, and the model had no involvement in it.

---

## 21:00 — Verifying the deployed engine

[DO: Ctrl+C the adk web tab. Leave the MCP tab running, because the next step reuses it.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step2.sh
```

That confirms the engine is deployed with an agent identity attached. Now let's talk to the real thing running in the cloud.

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/ask_agent.py brand-style \
  "Audit this mock-up. image: gs://<bucket>/vendor_request_refine.png, character: grogu, market: NA"
```

[SCREEN: the report from the deployed engine.]

You get the same shape of report, this time from an engine running in Agent Runtime.

Your status may well differ from mine, and that difference is the lesson. The agent works out the medium by looking at the artwork, so on one run it says vinyl figures and comes back compliant, and on another it says artwork, which isn't on the approved list, and the deterministic check flags it. The fuzzy half varies between runs while the rule applied to it stays identical, which means a flagged result here is the system working correctly.

You may also see a line about A2A trace propagation. That's the client reporting that there's no trace running on your laptop, so the engine starts its own, and it's expected output rather than an error.

---

## 23:30 — Do and don't

Use the human's form as your tool signature, because it tells you where the model's job ends.

Keep the rules out of the prompt, because a model that can see them will start applying them.

Give an agent exactly one tool when it has exactly one job. A filtered toolset is a security boundary as much as it is tidiness.

Don't be alarmed by a flagged result. Variation in what the model extracts is expected, and what must never vary is the verdict produced from that extraction.

Run the collect script after every deploy, because everything downstream reads that file.

---

## 25:00 — Where that leaves us

You've built an agent that automates the perception and the data entry, and hands the deciding to a tool that was already correct. It runs as its own identity with a narrow set of permissions, and it reaches its tool server by impersonating a service account, because agent identities can't authenticate to Cloud Run directly.

The next step raises the difficulty. Instead of making one tool call, the deal pricing agent runs a bounded loop inside itself, follows a written procedure called a Skill, and has to reconcile a vendor's claim against a rate card. A vendor is about to tell us they qualify for a volume discount, and the interesting part is how the agent works out that they don't.

See you there.

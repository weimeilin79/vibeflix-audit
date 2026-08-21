# Step 2 — The Brand Style Agent

**Target runtime:** 16–19 min · **Lab section:** `The Brand Style Agent`

---

## 00:00 — Cold open

[SCREEN: a product mock-up, then a JSON report beside it.]

The first agent looks at a product mock-up and decides whether it follows Vibeflix's brand rules. That's one task on the surface and two underneath, and keeping them apart is what this step is about.

---

## 00:40 — How a person does it

[SCREEN: comic panels — a vendor submits a mock-up, a coordinator squints at it, types into a form.]

A vendor sends artwork. A coordinator opens it, reads the printed text off the image by eye, works out the product type — vinyl figure, plush, apparel — and types those facts into a compliance checker. The checker applies the rules and returns a verdict.

The checking is already automated. The rules exist, they run, and they're correct. What costs time is a person looking at an image and typing what they saw, and those are the two things we replace.

The opposite mistake is common in agent projects. People decide the interesting part is the decision and automate that. The decision was already deterministic, so replacing it with a model makes the system slower, more expensive and impossible to reproduce, while the eyes and the fingers stay exactly where they were.

---

## 02:00 — The split

The non-deterministic work is looking at the mock-up and reading what's on it: the printed text, the product medium. Two people describe the same image differently, and a model varies the same way across runs. Vision models are good at this.

The deterministic work is checking those facts against the rules. Is this font approved? Is this medium allowed for this character? Same inputs, same answer, because it's a lookup. A model should never decide it, because it will occasionally invent an answer and do it fluently enough that nobody notices.

[SCREEN: the BEFORE / NOW diagram.]

So the agent's vision fills in the fields the coordinator used to type, and hands them to the checker that was always there. The model produces facts and the tool produces the verdict.

---

## 03:30 — The form is the tool signature

[SCREEN: the `run_brand_audit` tool signature.]

Open the brand style MCP server and look at the audit tool's signature. Its parameters are the fields on the coordinator's form: the image reference, the text found on it, the medium, the character, the market.

When you replace a step a human used to do, the form they filled in is your tool signature. It tells you what the model has to produce and where its job stops. Everything on the form is the model's work, everything behind it is the tool's.

If you're unsure where to draw that line in your own system, find the form, the ticket template, or the spreadsheet columns. Somebody documented that boundary years ago without calling it an API.

---

## 05:00 — ADK vocabulary

[SCREEN: the ADK concept diagram.]

An Agent is a model, an instruction and a set of tools. It reads the situation, decides whether to call a tool, calls it, looks at the result, then continues or answers.

Tools are what it can do, and ours come from MCP servers. The instruction is its standing brief: who it is, what it's deciding, what shape its answer takes.

Skills arrive in Step 3 and Workflow in Step 5. Today it's one agent, one tool, one job.

---

## 06:00 — Reading agent.py

[SCREEN: `agents/brand_style/agent.py`.]

The model is Gemini with vision, because the agent has to look at an image.

The instruction tells the agent to extract what it sees and call the audit tool, and it never states the brand rules. A model that can see the rules starts applying them itself, which quietly moves a deterministic decision back into the fuzzy layer. Keeping the rules out of reach removes the temptation.

The tools list contains one MCP toolset filtered to the single audit tool, so the agent has no way to call anything you didn't hand it.

There's also a schema guard, a callback that catches the model answering in prose instead of the structured report and rewrites it into a valid shape. Models occasionally decide to be helpful in English, and a deterministic net around the output stops that becoming an outage.

---

## 07:30 — Deploy

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py brand_style
python deploy/collect_agent_identities.py
```

[DO: start it, then jump ahead to the local Dev UI while it builds.]

The second command needs explaining, because everything after it depends on the file it writes.

---

## 08:30 — The address book

Deploying an agent produces two facts that only exist afterwards: where it lives, the engine id minted by Agent Runtime, and who it is, its identity principal.

The collect script asks Vertex AI for every Vibeflix engine in your project and writes both down, one entry per agent.

[SCREEN: the JSON — engine and principal.]

The grant script reads the principal so it grants roles to the right identity. The next agent you deploy reads its peers' engines to build A2A URLs. The gateway setup reads it to register each agent as a destination. And you're about to read it to talk to your own agent.

So it gets regenerated after every deploy, because a fact that didn't exist a minute ago has to be written down for the next step.

This is also why deploy order matters later. Agents that call each other can't all know each other's addresses up front, since an engine id doesn't exist until its engine does. Deploy, collect, then deploy whatever needed that address.

---

## 09:30 — Granting access

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh brand-style
```

The engine exists and its identity can do nothing. Two separate things get granted here.

First, what the agent may do, on its own principal. Call Gemini, without which it can't think. Write its own sessions, and missing that causes every task poll to return 401 and the agent to hang forever. Read the registry, emit traces and metrics, and publish to the telemetry topic that lights up the graph in Step 8.

Second, how it reaches the MCP servers. An agent identity is a different kind of thing from a service account. Cloud Run's IAM check wants an OIDC token issued by a service account, and an agent principal has none.

[SCREEN: the impersonation diagram.]

So a shared service account sits in the middle. The agent is granted permission to impersonate it, mints a token with it, and calls the MCP server with that token, at which point Cloud Run sees a service account it trusts.

Nothing was opened up. Hit that MCP URL yourself and you still get a 403. Each agent grants its own access keyed to its own principal.

The reach this grants stops at Gemini and the tool servers. Agent-to-agent traffic is governed separately by the Agent Gateway in Step 7.

---

## 11:30 — Driving it locally

[DO: second tab.]

```bash
cd ~/vibeflix-audit
./run_local.sh mcp
```

[DO: third tab.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/brand_style
```

The allow-origins flag matters. Web Preview proxies the page through a cloudshell.dev address, which is a different origin, and without the flag the page loads and the first call fails with a 403 that looks like a broken agent.

[DO: Web Preview → port 8000. Pick brand_style. Audit the default mock-up.]

---

## 13:00 — Reading the answer

[SCREEN: the returned report.]

`extracted` is the model's work: the medium, and the printed text, empty on this mock-up. Run it twice and the wording may shift, because that's the coordinator's eyes.

Everything else is the tool's. `checks_run` lists the deterministic checks in the server's fixed order, and `status` is its verdict, which the model didn't choose and can't override. `findings` is empty because nothing failed, and each failed check adds an entry naming the element, issue type and severity.

Now break it.

[DO: change the image link to a bucket outside the project. Re-run.]

Point the image outside your buckets and re-run. Status comes back rejected, and `checks_run` contains one entry, the asset-source check. That gate runs first and short-circuits everything after it, so unapproved artwork never gets inspected. That ordering is baked into the tool.

---

## 14:30 — Verifying the deployed engine

[DO: Ctrl+C the adk web tab. Leave the MCP tab running for the next step.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step2.sh
python deploy/ask_agent.py brand-style \
  "Audit this mock-up. image: gs://<bucket>/vendor_request_refine.png, character: grogu, market: NA"
```

[SCREEN: the report from the deployed engine.]

Your status may differ from mine, and that difference is the lesson. The agent works out the medium by looking at the artwork, so one run says vinyl figures and comes back compliant, and another says artwork, which isn't on the approved list, so the check flags it. The fuzzy half varies while the rule applied to it stays identical, so a flagged result is the system working.

A line about A2A trace propagation is expected output. There's no trace running on your laptop, so the engine starts its own.

---

## 16:00 — Do and don't

Use the human's form as your tool signature.

Keep the rules out of the prompt.

Give an agent one tool when it has one job, because a filtered toolset is a security boundary.

Expect variation in what the model extracts, and expect none in the verdict produced from it.

Run collect after every deploy.

---

## 16:45 — Where that leaves us

You've automated the perception and the data entry, and handed the deciding to a tool that was already correct. The agent runs as its own identity and reaches its tool server by impersonating a service account.

Next, deal pricing runs a bounded loop inside itself, follows a written procedure called a Skill, and reconciles a vendor's claim against a rate card. A vendor is about to claim a volume discount they don't qualify for.

See you there.

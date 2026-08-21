# Step 3 — The Deal Pricing Agent

**Target runtime:** 14–17 min · **Lab section:** `The Deal Pricing Agent`

---

## 00:00 — Cold open

[SCREEN: a deal sheet — 10% royalty, 30,000 units. Next to it, a rate card showing 14%.]

A vendor agreed to a 10% royalty and justified it as a high-volume discount.

The rate card's base rate for this character is 14%. There is a volume discount band, and it begins at 100,000 units a year. This vendor projects 30,000, so the discount doesn't apply and the deal is underpriced.

Multiplying a base rate by a modifier is arithmetic any spreadsheet does. The hard part is testing the vendor's claim against the tier they qualify for.

---

## 01:00 — Why this can't be one model call

The last agent was one shot: look at the image, call a tool, report.

Pricing needs a different shape. The agent pulls the expected deal from the rate card and compares it to what was agreed, component by component. It notices the royalty rate is off, but the vendor attached a reason. It can't accept that reason or reject it without checking whether the claimed factor applies.

That's several model calls, in order, with a decision point in the middle.

The tempting approach is one large prompt saying think step by step, check the claim, decide. It usually works. Then on the run that matters it skips a step, loops indefinitely, or convinces itself it already checked something it hasn't.

---

## 02:30 — Loop engineering

Keep the model for judgment and move the control flow into code.

[SCREEN: `START ──► evaluate ──► reconcile (LOOP) ──► finalize`]

The agent is a small graph. An evaluate node pulls the rate card and compares. A reconcile node handles unresolved claims and is a bounded loop with a hard maximum. Then finalize.

That gives you three things a large prompt can't.

It terminates, because the maximum is a number in Python and the model has no vote.

The steps happen in order, because the edge between nodes decides what runs next.

And it's inspectable, so when something breaks you know which node broke. Debugging a graph is tractable in a way that debugging "the model didn't follow step four" isn't.

Same idea as the previous step, one level up. There the model extracted and the tool decided. Here the model reasons and the graph controls sequencing.

---

## 04:00 — Skills

A Skill is a written procedure: a markdown file describing how to do a job, the steps in order, and which tools to use at each one. You hand it to the agent and the agent follows it.

[SCREEN: the Skill anatomy — SKILL.md plus a references folder.]

Three reasons it beats putting the procedure in the instruction.

It's versioned, because it's a file that gets reviewed in a pull request, so somebody who isn't the prompt author can say that isn't how the process works.

It carries resources, shipping reference files like the full rate-card tier table that the agent loads on demand instead of hauling around in every prompt.

And it's where the rule for pricing lives, written in plain words: defer the exact math to the tool. That sentence is in the file, so changing it shows up in a diff.

When your prompt starts containing a procedure, pull it into a file and treat it as the operational document it already is.

---

## 05:30 — The loop in code

[SCREEN: `agents/deal_pricing/agent.py` — the nodes, the bounded `for`.]

The reconcile node has a for loop with a fixed bound. Inside it a resolver agent gets asked one question: does the claimed factor apply to this vendor?

The loop is deterministic — how many rounds, what ends them, what happens at the bound — and the judgment inside each round is the model's.

---

## 06:30 — Deploy

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py deal_pricing
python deploy/collect_agent_identities.py
```

[DO: start it, then work locally while it builds.]

Deploy then collect, because the engine id and principal don't exist until the deploy finishes.

Once it's done:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh deal-pricing
```

---

## 07:30 — Running it locally

[DO: second tab — skip if the MCP servers are still up from Step 2.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh mcp
```

[DO: third tab.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
export MCP_LICENSING_URL=http://127.0.0.1:9002/mcp
adk web --allow_origins="regex:https://.*\.cloudshell\.dev" agents/deal_pricing
```

[DO: Web Preview → 8000 → deal_pricing. Paste the underpriced deal.]

---

## 09:00 — Reading the reply

[SCREEN: the trimmed JSON.]

`rate_card` is what the agent fetched at run time. The licensing tool returned Grogu's card: A-list tier, 0.14 base rate, the modifier tables. None of it appears in the prompt or the model's knowledge. Update the rate card in Firestore tomorrow and this agent prices differently tomorrow, with no redeploy.

`expected` is what that card computes to: 0.14 times 1.2 for vinyl figures, times 1.0 for North America, times 1.0 for volume, giving 0.168.

That last multiplier is where the claim gets rejected. The first tier earning a discount begins at 100,000 units and this deal is 30,000, so it stays at 1.0. The arithmetic belongs to the tool.

`components` compares line by line against what was agreed, and all three are discrepancies. The minimum guarantee also carries a below-floor flag, because 30,000 sits under the card's floor of 150,000.

Look at the royalty rate line, which is above the floor. A rate of 0.10 is exactly the minimum, so it's legal while still far under what the card says the deal should have been. Whether something is permitted and whether it's correctly priced are separate questions, and the card answers both. That nuance disappears when a model summarises a deal in prose.

The verdict and status come from the tool, derived from those components. The model drove the loop and never chose the verdict.

---

## 11:30 — Changing one number

[DO: re-run with volume 120000.]

Set the volume to 120,000. The tier is met, the volume multiplier becomes 0.95, and the expected rate drops to 0.1596. Still above the agreed 0.10, so the verdict stays underpriced.

Same graph, same skill, different arithmetic, because the card said so. You changed the data and the answer changed correctly with nobody editing a prompt.

---

## 12:30 — Verify and shut down

[DO: Ctrl+C in the adk web tab and the MCP tab.]

Stop both. The next section starts the whole local mesh, which brings up its own MCP servers on the same ports, and if the old ones hold those ports the new ones exit immediately with an error that looks nothing like a port conflict.

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step3.sh
```

Then send the same deal to the deployed engine with `ask_agent.py` and watch it pull the expected deal, mark the royalty unresolved, run the loop, reject the claim, and land on a verdict.

---

## 13:30 — Do and don't

Put control flow in code and judgment in the model.

Don't rely on a prompt to enforce a procedure, because it fails quietly when it fails.

Write the procedure as a Skill, so it's versioned and can carry reference data.

Keep a model away from arithmetic that ends up in a contract, because you can't prove it multiplied the same way twice.

Keep the rate card in data, so changing a business rule is a data change.

Stop the local MCP servers before the next section needs those ports.

---

## 14:30 — Where that leaves us

The agent is a small workflow — evaluate, reconcile in a bounded loop, finalize — that reasons about claims and defers every number to a tool.

Every agent so far has been self-contained. Next, vendor clearance hands work to a separate agent called legal, running in its own engine across a network boundary. Legal's problem is that the process it follows was never written down. It reconstructs it from an email thread, somebody's checklist, and a wiki page that stops mid-sentence.

See you there.

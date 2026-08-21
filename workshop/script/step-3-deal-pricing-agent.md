# Step 3 — The Deal Pricing Agent

**Target runtime:** 21–25 min · **Lab section:** `The Deal Pricing Agent`

---

## 00:00 — Cold open

[SCREEN: a deal sheet — 10% royalty, 30,000 units. Next to it, a rate card showing 14%.]

A vendor has agreed to a 10% royalty and attached a justification, which is that they qualify for a high-volume discount.

If you look at the rate card, the base rate for this character is 14%, and there genuinely is a volume discount band. The band begins at 100,000 units a year, and this vendor projects 30,000, so the discount they're claiming doesn't apply to them and the deal is underpriced by a wide margin.

What I want you to notice is where the difficulty actually sat. Multiplying a base rate by a category modifier is arithmetic that any spreadsheet can do. The hard part was testing the vendor's claim against the tier they actually qualify for, and that's the job this agent does.

---

## 02:00 — Why this can't be a single model call

The last agent was one shot: look at the image, call a tool, report the answer. Pricing needs a different shape, and it's worth being precise about why.

The agent has to pull the expected deal from the rate card and compare it to what was agreed, component by component. It notices that the royalty rate is off, but the vendor has attached a reason for it. It can't simply accept that reason, and it can't simply reject it either, so it has to go and check whether the claimed factor genuinely applies before it decides anything.

That's several model calls, in a particular order, with a decision point in the middle of them.

This is the point where a lot of agent designs go wrong. The tempting approach is one very large prompt that says think step by step, check the claim, then decide, and to trust the model to hold that whole procedure in its head. It usually will. Then on the run that matters it skips a step, or loops indefinitely, or convinces itself it has already checked something it hasn't.

---

## 04:00 — Loop engineering

The alternative is what I'd call loop engineering, where you keep the model for judgment and move the control flow into code.

[SCREEN: `START ──► evaluate ──► reconcile (LOOP) ──► finalize`]

So this agent is a small graph. An evaluate node pulls the rate card and compares it against the agreed terms. A reconcile node handles any unresolved claims, and that node is a bounded loop with a hard maximum number of rounds. Then a finalize node produces the verdict.

That structure gives you three properties a single large prompt can't.

It terminates, because the maximum number of rounds is a number in Python and the model has no vote in whether to go round again.

The steps always happen in the right order, because the model can't skip evaluation and jump straight to a verdict when the edge between those nodes decides what runs next.

And it's inspectable, so when something goes wrong you can see which node it went wrong in. Debugging a graph is tractable in a way that debugging "the model didn't follow step four" never is.

It's the same idea as the previous step, applied one level up. There, the model extracted facts and the tool decided. Here, the model reasons and the graph controls what happens when.

---

## 06:30 — Skills

The second concept in this step is one of the more useful ideas in ADK.

A Skill is a written procedure — a markdown file describing how to do a job, listing the steps in order and which tools to use at each one. You hand it to the agent and the agent follows it.

[SCREEN: the Skill anatomy — SKILL.md plus a references folder.]

The obvious question is why that shouldn't just live in the instruction, and there are three answers.

It's versioned, because it's a file in the repository that gets reviewed in a pull request, which means somebody who isn't the prompt author can read it and say that isn't how the process works.

It can carry resources, so a skill ships reference files alongside it — like the full rate-card tier table — that the agent loads on demand rather than hauling around inside every prompt.

And it's the natural home for the rule that matters most here, which for pricing is written out in plain words: defer the exact math to the tool. That sentence lives in the file, versioned and reviewable, so if somebody changes it the change shows up in a diff.

If you take one practice away from this workshop, this is a strong candidate. As soon as your prompt starts containing a procedure, pull it out into a file and treat it as the operational document it already is.

---

## 09:00 — The loop in the code

[SCREEN: `agents/deal_pricing/agent.py` — the nodes, the bounded `for`.]

Look at the reconcile node and you'll find a for loop with a fixed bound. Inside that loop a resolver agent gets asked one question, which is whether the claimed factor actually applies to this vendor.

That's the division of labour. The loop is deterministic — how many rounds run, what ends them, what happens when the bound is reached — and the judgment inside each round belongs to the model. Non-deterministic reasoning living inside a deterministic control structure is the pattern to take away from this step.

---

## 10:30 — Deploying it

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py deal_pricing
python deploy/collect_agent_identities.py
```

[DO: start it. Jump cut.]

Same shape as last time, with the deploy followed by a collect, because the engine id and the principal don't exist until the deploy has finished. Don't wait for it — we'll go and work locally while it builds.

Once it's done, grant it its access:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh deal-pricing
```

Its own principal, its own roles, and its own route to the MCP servers, exactly as with brand style.

---

## 12:00 — Running it locally

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

## 14:00 — Reading the reply

The reply is long, so let's take the parts that matter.

[SCREEN: the trimmed JSON.]

The `rate_card` block is what the agent fetched at run time. The licensing tool returned Grogu's card, which includes the A-list tier, the 0.14 base rate and the modifier tables, and none of that appears anywhere in the prompt or in the model's own knowledge. The practical consequence is that if somebody updates the rate card in Firestore tomorrow, this agent prices differently tomorrow, with no redeploy and no prompt change.

The `expected` block is what that card computes to for this particular deal: 0.14, multiplied by 1.2 for vinyl figures, multiplied by 1.0 for North America, multiplied by 1.0 for volume, which comes to 0.168.

That last multiplier is where the vendor's claim gets rejected. The first tier that earns a discount begins at 100,000 units and this deal is for 30,000, so the multiplier stays at 1.0. The arithmetic belongs entirely to the tool, which is the skill's instruction about deferring the math showing up on screen.

The `components` block is the line-by-line comparison against what the vendor agreed, and all three lines are discrepancies. The minimum guarantee also carries a below-floor flag, because 30,000 sits under the card's floor of 150,000.

Look closely at the royalty rate line, though, because it is above the floor. A rate of 0.10 is exactly the card's minimum, so the agreed rate is legal while still being far under what the card says this deal should have been. Whether something is permitted and whether it's correctly priced are two separate questions, and the card answers both of them. That's precisely the kind of nuance that disappears when you let a model summarise a deal in prose.

Finally, the verdict and the status come from the tool, derived from those components. The model drove the loop and resolved the claim, and it never chose the verdict.

---

## 17:30 — Changing one number

[DO: re-run with volume 120000.]

Let's change one field and set the volume to 120,000.

Now the tier is met, so the volume multiplier becomes 0.95 and the expected effective rate drops to 0.1596. That's still above the agreed 0.10, so the verdict remains underpriced.

The graph is the same, the skill is the same, and the arithmetic is different because the card said so. That's the property you're aiming for, where changing the data changes the answer correctly and nobody has to edit a prompt.

---

## 19:00 — Verifying and shutting down

[DO: Ctrl+C in the adk web tab and in the MCP tab.]

Stop both tabs this time. The next section starts the whole local mesh, which brings up its own MCP servers on the same ports, and if the old ones are still holding those ports the new ones exit immediately with an error that looks nothing like a port conflict.

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step3.sh
```

Then send the same underpriced deal to the deployed engine using the ask-agent script, and watch it pull the expected deal, mark the royalty as unresolved, run the reconcile loop, reject the claim and land on a verdict.

---

## 21:00 — Do and don't

Put the control flow in code and the judgment in the model. The model works out what's true and the graph works out what happens next.

Don't rely on a prompt to enforce a procedure, because it works until it doesn't and it fails quietly when it goes.

Write the procedure down as a Skill, so it's versioned, reviewable and able to carry reference data.

Keep a model away from arithmetic that ends up in a contract, because you can't prove it multiplied the same way twice.

Keep the rate card in data, so that changing a business rule is a data change.

And stop the local MCP servers before the next section needs those ports.

---

## 23:00 — Where that leaves us

You now have an agent that's really a small workflow — evaluate, reconcile in a bounded loop, finalize — which reasons about claims and defers every number to a tool.

Every agent so far has been self-contained, and that changes in the next step. Vendor clearance has to hand work to a completely separate agent called legal, running in its own engine, across a network boundary. Legal also has a problem none of our agents have had, which is that the process it's meant to follow was never written down anywhere. It has to reconstruct that process from an email thread, somebody's personal checklist, and a wiki page that stops mid-sentence.

It's the biggest step in the workshop. See you there.

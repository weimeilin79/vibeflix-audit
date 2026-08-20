# Step 3 — The Deal Pricing Agent

**Target runtime:** 21–25 min · **Lab section:** `The Deal Pricing Agent`

---

## 00:00 — Cold open

[SCREEN: a deal sheet — 10% royalty, 30,000 units — next to a rate card showing a 14% base.]

A vendor agrees to a 10% royalty and justifies it as a high-volume discount.

The rate card's base for this character is 14%. There *is* a volume discount band — but it starts at 100,000 units, and this vendor projects 30,000.

[BEAT]

So the discount they're claiming doesn't apply to them. The deal is underpriced, and the verdict is *needs adjustment*.

Now — notice where the difficulty is. **The arithmetic was never in question.** Multiplying a base rate by a category modifier is not hard. The hard part was testing a *claim* against the tier the vendor actually qualifies for.

That's the shape of this step: a single agent that runs a small reasoning loop inside itself, while every number it reports comes from a tool.

---

## 02:00 — Why one agent isn't one model call

The last agent was one shot. Look at the image, call a tool, report.

Pricing can't work that way, and it's worth being precise about why.

The agent has to pull the expected deal from the rate card. Compare it to what was agreed, component by component. Notice that the royalty rate is off — but the vendor has attached a *reason*. It can't just accept the reason, and it can't just reject it either. It has to go and check whether the claimed factor actually applies. Then decide.

That's several model calls, in a specific order, with a decision point in the middle.

[BEAT]

And here's where a lot of agent designs go wrong. The temptation is to write one enormous prompt — "think step by step, check the claim, decide" — and hope the model holds the whole procedure in its head.

It will, most of the time. And then on the run that matters it'll skip a step, or loop forever, or decide it's already checked something it hasn't.

---

## 04:00 — Loop engineering

The alternative is what I'd call **loop engineering**: you keep the model for judgment, and you put the *control flow* in code.

[SCREEN: `START ──► evaluate ──► reconcile (LOOP) ──► finalize`]

So this agent is a small graph. An `evaluate` node that pulls the rate card and compares. A `reconcile` node that handles unresolved claims — and that node is a **bounded loop**, with a hard maximum number of rounds. Then `finalize`.

Three properties you get from that, which a single mega-prompt cannot give you.

**It terminates.** `MAX_ROUNDS` is a number in Python. The model doesn't get a vote on whether to go round again — the loop condition does.

**The steps always happen, in order.** The model can't skip evaluation and jump to a verdict, because the edge from `evaluate` to `reconcile` is an edge, not a suggestion.

**It's inspectable.** When something goes wrong you can see which node it was in. Debugging a graph is tractable; debugging "the model didn't follow step four" is not.

This is the same idea as before, one level up. Last step: the model extracts, the tool decides. This step: the model reasons, the **graph** controls.

---

## 06:30 — Skills: a written procedure you hand the agent

Second concept, and it's one of the more useful ideas in ADK.

A **Skill** is a written procedure. A markdown file — `SKILL.md` — that describes how to do a job: the steps, in order, and which tools to use at each one. You hand it to the agent, and the agent follows it.

[SCREEN: the Skill anatomy — SKILL.md with metadata and instructions, plus a `references/` folder.]

Why not just put that in the instruction? Three reasons.

**It's versioned.** It's a file in the repo. It gets reviewed in a pull request. Somebody who isn't the prompt author can read it and say "that's not our process."

**It carries resources.** A skill can ship reference files alongside it — like the full rate-card tier table — that the agent loads on demand instead of carrying in every prompt.

**It's the natural home for the rule that matters.** And for pricing, that rule is written down explicitly: **defer the exact math to the tool.**

[BEAT]

That sentence is in the skill. Not implied, not hoped for. Written, versioned, reviewable. If someone changes it, that shows up in a diff.

If you take one practice from this workshop into your own work, this is a strong candidate. The moment your prompt starts containing a *procedure*, pull it out into a file and treat it like the operational document it is.

---

## 09:00 — The loop in code

[SCREEN: `agents/deal_pricing/agent.py` — the Workflow, the nodes, `for _ in range(MAX_ROUNDS)`.]

Look at the reconcile node. There's a `for` loop with a fixed bound. Inside it, a resolver agent — a model call — is asked one question: does this claimed factor actually apply to this vendor?

That's the division. The **loop** is deterministic: how many rounds, what ends it, what happens when the bound is hit. The **judgment inside each round** is the model's.

Non-deterministic judgment living inside a deterministic control structure. That's the pattern.

---

## 10:30 — Deploy

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py deal_pricing
python deploy/collect_agent_identities.py
```

[DO: start it. Jump-cut planned.]

Same shape as last time — deploy, then collect, because the engine id and principal don't exist until the deploy finishes. Don't wait on it; we'll go local while it builds.

Then, once it's done:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh deal-pricing
```

Its own principal, its own roles, its own reach to the MCP servers. Same least-privilege story as brand style.

---

## 12:00 — Drive it locally

[DO: second tab — skip if the MCP servers are still running from Step 2.]

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

[DO: Web Preview → port 8000 → deal_pricing. Paste the underpriced deal.]

> Audit this deal. character: grogu, product_category: vinyl figures, territory: NA, volume: 30000, net_unit_price: 18. Agreed terms — royalty_rate: 0.10, advance: 8000, mg: 30000.

---

## 14:00 — Read the reply

The reply is long. Let's take the parts that matter.

[SCREEN: the trimmed JSON — expected, agreed, rate_card, components, verdict, status.]

**`rate_card` is what the agent *fetched*, not what it knew.** `get_license_pricing` on the licensing MCP returned Grogu's card: A-list tier, a 0.14 base rate, and the modifier tables. None of that is in the prompt or in the model's head. If someone updates the rate card in Firestore tomorrow, this agent prices differently tomorrow — with no redeploy, no prompt change.

**`expected` is what that card computes to** for this deal. Zero point one four, times one point two for vinyl figures, times one point zero for North America, times one point zero for volume. Equals **0.168**.

[BEAT]

And that last multiplier is the whole point. **That's the volume-discount claim being rejected.** The first tier that earns a discount starts at 100,000 units. This deal is 30,000. So the multiplier stays at 1.0.

The arithmetic is the tool's, not the model's. This is *defer the exact math to the tool*, made concrete.

**`components` is the line-by-line comparison** against what the vendor agreed. All three are a discrepancy. And notice `mg` carries `below_floor: true` — 30,000 against the card's floor of 150,000.

Now look closely at `royalty_rate`: it is **not** below floor. 0.10 is exactly the minimum royalty rate. So it's *legal* — just far under what the card says this deal should be.

[BEAT]

"Legal" and "what we should have charged" are two different questions, and the card answers both. That distinction is worth pausing on, because it's the kind of nuance that gets flattened when you let a model summarise a deal in prose.

**`verdict` and `status` are the tool's**, derived from those components. The model drove the loop and resolved the claims. It never picked the verdict.

---

## 17:30 — Try breaking it

[DO: re-run with volume 120000.]

Change one field. Set volume to 120,000.

Now the tier *is* met. `volume_mult` becomes 0.95, and the expected effective rate drops to 0.1596.

Still above the agreed 0.10 — so the verdict stays underpriced. Same graph, same skill, different arithmetic, all of it read off the card rather than reasoned about.

That's the property you want: you changed the *data*, and the system's answer changed correctly, with nobody editing a prompt.

---

## 19:00 — Verify and shut down

[DO: Ctrl+C in the adk web tab **and** the run_local.sh mcp tab.]

Stop both this time. The next section starts the whole local mesh, which brings up its own MCP servers on the same ports 9002 to 9004 — and if the old ones are still holding those ports, the new ones exit instantly.

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step3.sh
```

Then send the same underpriced deal to the deployed engine:

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/ask_agent.py deal-pricing \
  "Audit this deal. character: grogu, product_category: vinyl figures, territory: NA, \
volume: 30000, net_unit_price: 18. Agreed terms — royalty_rate: 0.10, advance: 8000, mg: 30000."
```

Watch it pull the expected deal, mark the royalty unresolved, run the reconcile loop, reject the claim, and land on a verdict.

---

## 21:00 — Do and don't

**Do put control flow in code and judgment in the model.** Bounded loops, explicit edges. The model decides *what's true*, the graph decides *what happens next*.

**Don't rely on a prompt to enforce a procedure.** It works until it doesn't, and it fails silently.

**Do write the procedure down as a Skill.** Versioned, reviewable, and it can carry reference data.

**Don't let the model do arithmetic you'd put in a contract.** Not because it can't multiply — because you can't prove it multiplied the same way twice.

**Do keep the rate card in data, not in the prompt.** Changing a business rule should be a data change.

**Don't leave the local MCP servers running** when the next section needs those ports. It's a two-minute confusion that looks like a real failure.

---

## 23:00 — Recap and bridge

You've got an agent that's really a small workflow: evaluate, reconcile in a bounded loop, finalize. It reasons about claims and defers every number to a tool that reads a rate card out of Firestore.

So far each agent has been self-contained. Next step changes that. **Vendor clearance** needs to hand work to a completely separate agent — **legal** — running in its own engine, over a protocol called A2A. And legal has a problem neither of our agents has had: the process it's supposed to follow *isn't written down anywhere*. It has to reconstruct it from an email thread, somebody's personal checklist, and a half-finished wiki page.

That's retrieval, a handoff, and a human-in-the-loop question all in one step. It's the biggest one in the workshop.

See you there.

# Step 3 — The Deal Pricing Agent

**Target runtime:** 21–25 min · **Lab section:** `The Deal Pricing Agent`

---

## 00:00 — Cold open

[SCREEN: a deal sheet — 10% royalty, 30,000 units. Next to it, a rate card showing 14%.]

A vendor agrees to a 10% royalty. And they've got a reason.

High-volume discount, they say.

[BEAT]

Here's the rate card. Base rate for this character: 14%. And yes — there *is* a volume discount band.

It starts at 100,000 units.

This vendor projects 30,000.

[BEAT]

So the discount they're claiming doesn't apply to them. The deal is underpriced by a wide margin.

Now look at where the difficulty actually was. **The arithmetic was never in question.** Any spreadsheet multiplies a base rate by a modifier.

The hard part was testing a *claim* against the tier the vendor actually qualifies for.

That's this step. One agent, running a small reasoning loop inside itself — while every number it reports comes from a tool.

---

## 02:00 — Why one agent isn't one model call

Last agent was one shot. Look at the image. Call a tool. Report.

Pricing can't work like that. Here's why.

The agent has to pull the expected deal from the rate card. Compare it to what was agreed, line by line. Spot that the royalty rate is off — but the vendor attached a *reason*.

It can't just accept the reason. It can't just reject it either. It has to go check whether the claimed factor actually applies. Then decide.

That's several model calls. In a specific order. With a decision point in the middle.

[BEAT]

And this is where a lot of agent designs go wrong.

The temptation is one enormous prompt. "Think step by step. Check the claim. Decide." And hope the model holds the whole procedure in its head.

It will. Most of the time.

And then on the run that matters, it skips a step. Or loops forever. Or decides it already checked something it never checked.

---

## 04:00 — Loop engineering

The fix is what I'd call **loop engineering**. Keep the model for judgment. Put the *control flow* in code.

[SCREEN: `START ──► evaluate ──► reconcile (LOOP) ──► finalize`]

So this agent is a small graph. An `evaluate` node pulls the rate card and compares. A `reconcile` node handles unresolved claims — and that one is a **bounded loop**, with a hard maximum. Then `finalize`.

Three things you get from that. A mega-prompt gives you none of them.

**It terminates.** The max rounds is a number in Python. The model doesn't get a vote.

**The steps always happen, in order.** The model can't skip evaluation and jump to a verdict. The edge decides.

**It's inspectable.** Something breaks, you know which node. Debugging a graph is doable. Debugging "the model didn't follow step four" is not.

Same idea as last step, one level up. Before: the model extracts, the tool decides. Now: the model reasons, the **graph** controls.

---

## 06:30 — Skills

Second concept. One of the more useful ideas in ADK.

A **Skill** is a written procedure. A markdown file. It describes how to do a job — the steps, in order, and which tools to use at each one. You hand it to the agent. The agent follows it.

[SCREEN: the Skill anatomy — SKILL.md plus a references folder.]

Why not put that in the instruction? Three reasons.

**It's versioned.** It's a file in the repo. It gets reviewed in a pull request. Someone who isn't the prompt author can read it and say "that's not our process."

**It carries resources.** A skill ships reference files alongside it — like the full rate-card tier table — that the agent loads on demand instead of hauling around in every prompt.

**And it's the natural home for the rule that matters.** For pricing, that rule is written down in plain words: **defer the exact math to the tool.**

[BEAT]

That sentence is in the file. Written down, versioned, reviewable. Someone changes it, it shows up in a diff.

If you take one practice home from this workshop, this is a strong candidate. The moment your prompt starts containing a *procedure* — pull it out into a file. Treat it like the operational document it already is.

---

## 09:00 — The loop in code

[SCREEN: `agents/deal_pricing/agent.py` — the nodes, the bounded `for`.]

Look at the reconcile node. There's a `for` loop with a fixed bound. Inside it, a resolver agent gets asked one question: does this claimed factor actually apply to this vendor?

That's the division.

The **loop** is deterministic. How many rounds. What ends it. What happens at the bound.

The **judgment inside each round** is the model's.

Non-deterministic judgment, living inside a deterministic control structure. That's the pattern.

---

## 10:30 — Deploy

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py deal_pricing
python deploy/collect_agent_identities.py
```

[DO: start it. Jump cut.]

Same shape as last time. Deploy, then collect — the engine id and principal don't exist until the deploy finishes.

Don't wait. We're going local while it builds.

Then, once it's done:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/grant_agent_access.sh deal-pricing
```

Own principal. Own roles. Own reach to the MCP servers.

---

## 12:00 — Run it locally

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

## 14:00 — Read the reply

The reply is long. Here are the parts that matter.

[SCREEN: the trimmed JSON.]

**`rate_card` is what the agent fetched at run time.**

The licensing tool returned Grogu's card. A-list tier. 0.14 base rate. The modifier tables. None of that is in the prompt or in the model's head.

Which means: update the rate card in Firestore tomorrow, and this agent prices differently tomorrow. No redeploy. No prompt change.

**`expected` is what that card computes to.** 0.14, times 1.2 for vinyl figures, times 1.0 for North America, times 1.0 for volume.

**0.168.**

[BEAT]

And that last multiplier is the whole story.

**That's the volume-discount claim being rejected.** The first tier that earns a discount starts at 100,000 units. This deal is 30,000. So the multiplier stays at 1.0.

The arithmetic belongs to the tool. Defer the exact math to the tool — right there, on screen.

**`components` is the line-by-line comparison** against what the vendor agreed. All three are a discrepancy. And `mg` carries `below_floor: true` — 30,000 against a floor of 150,000.

Now look closely at `royalty_rate`. It is **not** below floor. 0.10 is exactly the minimum.

[BEAT]

So it's legal. It's just far under what the card says this deal should be.

Legal, and what-we-should-have-charged, are two different questions. The card answers both.

That kind of nuance is exactly what gets flattened when you let a model summarise a deal in prose.

**`verdict` and `status` are the tool's.** Derived from those components. The model drove the loop. It never picked the verdict.

---

## 17:30 — Break it

[DO: re-run with volume 120000.]

Change one field. Volume goes to 120,000.

Now the tier *is* met. The volume multiplier becomes 0.95. Expected rate drops to 0.1596.

Still above the agreed 0.10 — so the verdict stays underpriced.

Same graph. Same skill. Different arithmetic. All of it read off the card.

That's the property you want. You changed the **data**, and the answer changed correctly. Nobody edited a prompt.

---

## 19:00 — Verify and shut down

[DO: Ctrl+C in the adk web tab **and** the MCP tab.]

Stop both this time.

The next section starts the whole local mesh, which brings up its own MCP servers on the same ports. If the old ones are still holding them, the new ones exit instantly — and the error looks nothing like "port in use".

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step3.sh
```

Then send the same deal to the deployed engine with `ask_agent.py`.

Watch it pull the expected deal. Mark the royalty unresolved. Run the loop. Reject the claim. Land on a verdict.

---

## 21:00 — Do and don't

**Do put control flow in code and judgment in the model.** The model decides what's true. The graph decides what happens next.

**Don't rely on a prompt to enforce a procedure.** It works until it doesn't. And it fails quietly.

**Do write the procedure down as a Skill.** Versioned. Reviewable. Can carry reference data.

**Don't let a model do arithmetic you'd put in a contract.** You can't prove it multiplied the same way twice.

**Do keep the rate card in data.** Changing a business rule should be a data change.

**Don't leave local MCP servers running** when the next section needs those ports.

---

## 23:00 — Recap and hook

You've got an agent that's really a small workflow. Evaluate. Reconcile in a bounded loop. Finalize. It reasons about claims and defers every number to a tool.

So far, every agent has been self-contained.

That ends now.

Next: **vendor clearance** has to hand work to a completely separate agent — **legal** — running in its own engine, across a network.

And legal has a problem none of our agents have had. The process it's supposed to follow **isn't written down anywhere.**

It has to reconstruct it. From an email thread. Somebody's personal checklist. And a wiki page that stops mid-sentence.

Biggest step in the workshop. See you there.

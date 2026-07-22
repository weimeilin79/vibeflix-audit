# Step 3 — The Deal Pricing Agent

Your second agent audits the money: is the royalty + advance + minimum guarantee the vendor
agreed to actually fair, measured against Vibeflix's rate card? Building it teaches two ideas
that shape how a *single* agent thinks: **Skills** and **loop-engineering**.

## 💡 Concept — loop-engineering inside one agent

From the outside, `deal_pricing` is one agent like `brand_style`. From the inside, it is **not**
a single model call — it's a small **Workflow** with a loop:

```
START ──► evaluate ──► reconcile (LOOP) ──► finalize
```

- **evaluate** runs the pricing reasoner once and tags each part of the deal:
  `clear`, `unresolved`, or `discrepancy`.
- **reconcile** is the loop. While any part is still `unresolved`, it runs a second sub-agent —
  the **resolver** — to adjudicate that one item against the rate-card rules, then re-checks.
  It repeats until nothing is unresolved *or* it hits `MAX_ROUNDS = 4`, then settles the verdict.
- **finalize** emits the result.

### Why a loop? The volume-discount case

A vendor agrees to a **10% royalty** and justifies it as a "high-volume discount." The rate card
base is **12%**, and the 10% band only applies at **50,000+ units/yr**. This vendor projects
**30,000**.

The reasoner can't just accept or reject that — so it marks the royalty **`unresolved`** with
`claim: "volume-tier discount"`. The **loop** hands that claim to the resolver, which checks the
*actual* projected volume (30k) against the tier's minimum (50k) → it doesn't qualify → the
discrepancy **stands** → verdict **NEEDS-ADJUSTMENT**.

That's the shape to internalize: **a deterministic control loop (the `for` loop, the status
transitions, the round cap) wrapped around non-deterministic judgment (the resolver's
reasoning).** It's Step 2's lesson one level up — *structure around reasoning, not reasoning as
structure.*

## 💡 Concept — Skills: a written procedure you hand the agent

The reasoner doesn't carry that whole audit procedure in one giant prompt. It loads a **Skill**.

> A **Skill** is a reusable, versioned *standard-operating-procedure* you give an agent —
> instructions + the exact tools it's allowed to use + the output it must produce.

## 📝 Look — the skill and the loop, in the code

Open `agents/deal_pricing/skills/deal-pricing-audit/SKILL.md`. It's a Markdown file with:

- **frontmatter** — `name`, `version`, and `allowed-tools: get_license_pricing` (scoped tools);
- a **numbered procedure** — Step 1 pull the rate card, Step 2 read the expected deal, Step 3
  classify each component, Step 4 rule the verdict;
- an **output contract** (the exact JSON shape).

Notice Step 2 of the skill: *"read the EXPECTED deal — do **NOT** compute it yourself… the tool
is the single source of truth."* **That's where the skill enforces Step 2's boundary** — it
tells the model to stay out of the arithmetic and defer to the deterministic
`get_license_pricing` tool. The skill and the loop are co-designed: the skill *defines* the
`unresolved` status, and the reconcile loop is what *consumes* it.

Now open `agents/deal_pricing/agent.py` and find the graph at the bottom:

```python
root_agent = Workflow(
    name="deal_pricing",
    edges=[("START", evaluate), (evaluate, reconcile), (reconcile, finalize)],
)
```

…and the loop inside `reconcile`:

```python
for _ in range(MAX_ROUNDS):
    unresolved = [c for c in report["components"] if c["status"] == "unresolved"]
    if not unresolved:
        break
    for c in unresolved:
        await ctx.run_node(resolver, ...)   # adjudicate ONE claim against the rules
```

## 💻 Run — build & deploy deal_pricing

Same one command as before — the deploy script finds `mcp_licensing`'s URL automatically:

```bash
.venv/bin/python deploy/deploy_agents_a2a.py deal_pricing
```

Then grant it its own access (project roles on its principal + reach to the MCP servers):

```bash
./deploy/grant_agent_access.sh deal-pricing
```

## 👀 Verify — watch the loop reconcile a claim

```bash
./deploy/verify/step3.sh
```

It confirms the `deal_pricing` engine is deployed with an agent identity. Then send it the
underpriced deal from the concept above and watch it reason:

```bash
ENGINE=$(jq -r '.["vibeflix-deal-pricing"].engine' deploy/agent_identities.json)
agents-cli run --url "$ENGINE" --mode adk \
  "Audit this deal. character: grogu, product_category: vinyl figures, territory: NA, \
volume: 30000, net_unit_price: 18. Agreed terms — royalty_rate: 0.10, advance: 8000, mg: 30000."
```

> 👀 Look for the agent to (1) pull the **expected** deal from the tool, (2) mark the royalty
> **unresolved** with the volume-discount claim, (3) let the **reconcile loop** reject the claim
> (30k < 50k), and (4) return a verdict — here **NEEDS-ADJUSTMENT** (or **UNDERPRICED** if a
> floor is breached). If it asks for a missing field, that's the agent doing input-validation —
> supply it and re-run.

*(The richest end-to-end pricing run comes together in Step 5, once the orchestrator feeds the
deal's fields automatically — here you're exercising the agent on its own.)*

## 💡 What you learned

- A single agent can be an internal **Workflow** with a **bounded loop**, not just one model
  call.
- A **Skill** gives the model a repeatable procedure and scoped tools — and is where you write
  down *"defer the exact math to the tool."*
- Non-deterministic judgment (the resolver) can live *inside* a deterministic control structure.

**Next:** [Step 4 — Vendor Clearance + Legal →](./04-vendor-legal.md)

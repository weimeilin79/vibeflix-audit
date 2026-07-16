# The Vibeflix Story

*Why this system exists — the business behind the mesh.*

---

## Vibeflix licenses its characters to the world

Vibeflix is a streaming company, and like every studio that builds a fandom, its
catalogue of characters is worth far more than the shows they came from. One of its most
profitable lines of business has nothing to do with streaming at all: **licensing its
intellectual property to authorized vendors** who manufacture the physical merchandise —
the vinyl figures, the apparel, the resin statues — that fans actually buy.

It sounds simple. It is not.

## The part that was always hard

A single licensing deal has to be right on several axes at once, and each one is its own
discipline:

- **Territory & exclusivity.** Rights are carved up by region. An exclusive partner may
  hold a territory lock on a character — grant a second vendor the same character in the
  same market and you've breached a contract you signed years ago.
- **Trademark & customs.** The mark has to be registered and recorded for the goods and
  the territory, or the shipment gets stopped at a border.
- **Branding.** The logo, the typography, the exact hex of a character's colour — a
  vendor's mock-up either honours the brand guide or it doesn't.
- **Pricing.** Every deal is a negotiated stack of royalty rate, advance, and minimum
  guarantee, measured against a rate card that bends by volume tier, product category,
  and territory.
- **Legal.** License amendments, safety certifications, HS codes, product-liability
  insurance, and finally an executed contract.

International rights, tiered vendors, and legacy contracts turn what looks like a form
into a chain of judgement calls — and for years, people made every one of them by hand.

## To their credit, they automated a lot of it

Vibeflix has a *vibe* in the name, and they lived up to it: the licensing org went after
this problem aggressively and got real results. Territory collisions, trademark lookups,
marketplace leak scans, brand-guide compliance — large stretches of the workflow now run
as agents that check the deterministic facts in seconds instead of days.

But automation hits a wall exactly where the work stops being lookup and starts being
**reasoning**.

## Where a human still had to think — deal pricing

Take the Deal Pricing desk. Checking a royalty rate against a rate card is easy. Deciding
whether a *discount* is legitimate is not.

Here's the kind of call that used to sit with a person:

> A vinyl-figure vendor agrees to a **10% royalty** and justifies it as a "high-volume
> discount." The rate card's base is **12%**. The discount is real — but only for vendors
> in the right band: Tier 2 (50,000–250,000 units/yr) earns 10%, Tier 1 (under 50,000)
> does not. This vendor projects **30,000 units**. So the discount they're claiming
> doesn't apply to them, the deal is underpriced by two points, and the verdict is
> **NEEDS-ADJUSTMENT** — not because the math was wrong, but because a claimed factor had
> to be tested against the tier the vendor actually qualifies for.

That is judgement, not arithmetic — and it's why the Deal Pricing Auditor doesn't just
compute a number. It runs an internal **evaluate → reconcile → finalize** loop: pull the
rate card, compute the expected deal, and for every component the vendor disputes, send a
resolver to adjudicate the claimed factor (a volume tier, a category modifier, a territory
uplift) against the rules — round after round until the discrepancy is either justified or
it stands. Only then does it rule **APPROVED / NEEDS-ADJUSTMENT / UNDERPRICED**.

## Where the knowledge lived — in people's heads

Pricing at least had a rate card. Other desks had less.

Because of *when* and *how* the departments were built, some of the most important
processes were never written down as a real process. They survived as **tribal
knowledge** — a handful of scattered documents left behind by people who've since moved
on, the institutional equivalent of instructions carved into a wall by an ancient
civilization. The Legal desk is the clearest case. Its "documentation" is:

- A departing engineer's handoff dump — literally titled
  *`legal-stuff-dont-lose-this.txt`* — that opens with *"Nobody ever wrote down the real
  end-to-end legal workflow, so here it is from memory before it walks out the door with
  me."*
- A `#licensing-ops` **Slack export** where the process is reconstructed live in chat
  (*"and where do i get the vendor's tier?" … "i just keep it in my own checklist at this
  point." "same. that's the problem."*).
- A rate card marked **Version 3**, with a note that Version 2 is *"still floating around
  in email — ignore it."*
- A 2019 SOP that is **wrong** about the insurance amount, contradicted by the newer memo.

Buried in that mess is a genuinely hard rule that keeps breaking onboardings: a contract
**cannot execute** until a human types in a safety-certification ID that lives in *no*
record — the question has to propagate all the way back up to whoever started the audit,
and the answer has to come back down. Everyone forgot it existed. Everyone kept their own
private checklist.

This is the problem the Legal Clearance agent is built to solve: instead of hard-coding a
process nobody agrees on, it **reconstructs** the workflow by reasoning over those exact
scattered docs (via retrieval), asks Vendor Clearance for the royalty tier, asks the human
for the cert ID, and executes the contract the departed engineer described from memory.

## And none of it ships without being locked down

For all the *vibe*, Vibeflix treats this as what it is: a system that moves real money,
signs real contracts, and touches partners' confidential terms. It is held to an
**enterprise-grade security bar**, and that bar is not a coat of paint — it's the
architecture:

- **Every agent has its own identity.** No shared service account stands in for the mesh.
  Each engine runs under its own per-agent identity, so every action is attributable and
  every permission is scoped to the one agent that needs it.
- **Egress is default-deny.** Agents can't call the open internet or each other freely — a
  governed Agent Gateway sits in the path, and an agent may only reach a destination it
  has been explicitly granted. Least privilege is enforced by the platform, not by
  convention.
- **The blast radius is small by design.** An agent that only needs to read the vendor
  registry can't reach pricing, and a compromised component can't quietly become the
  whole system.

The demo's entire point is that the governance is *real* — genuinely in the path of every
hop, not simulated for the screenshot.

---

## In one line

**Vibeflix already automated the easy parts of IP licensing; this system automates the
parts that still needed a human to *reason* — pricing judgement and undocumented legal
process — and does it under enterprise-grade, least-privilege security.**

> **Next:** see [the architecture](./02-architecture.md) for how the mesh is wired, or the
> [deployment runbooks](../deploy/docs/instruction-sre.md) to stand it up.

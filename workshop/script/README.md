# Video scripts — Vibeflix Audit workshop

One script per workshop step, written to be **read aloud word for word**. Source of
truth for the technical content is `../lab.en.md`; when the lab changes, the script
for that step needs a pass.

## Files

| # | Script | Lab section | Target |
|---|---|---|---|
| 1 | `step-1-setup-and-foundations.md` | Setup & Foundations | 20–24 min |
| 2 | `step-2-brand-style-agent.md` | The Brand Style Agent | 22–26 min |
| 3 | `step-3-deal-pricing-agent.md` | The Deal Pricing Agent | 21–25 min |
| 4 | `step-4-vendor-clearance-and-legal.md` | Vendor Clearance + Legal | 24–28 min |
| 5 | `step-5-orchestrator.md` | The Orchestrator | 22–26 min |
| 6 | `step-6-ui-renderer-a2ui-frontend.md` | UI Renderer, A2UI, Frontend | 20–24 min |
| 7 | `step-7-identity-gateway-registry.md` | Identity, Gateway & Registry | 21–25 min |
| 8 | `step-8-run-the-flows-observability.md` | Run the Flows, Observability | 20–24 min |

## Conventions

Everything in the file is one of four things, and they're visually distinct so you
can read past the ones that aren't spoken:

- **Plain paragraphs** — say these out loud, as written.
- **`[SCREEN: ...]`** — what should be visible. Not spoken.
- **`[DO: ...]`** — the action you perform on camera. Not spoken.
- **`[BEAT]`** — a deliberate pause. Usually after a question, or before a reveal.

Section headers carry a running time so you can pace yourself:
`## 04:00 — Why the tool decides, not the model`. Those are cumulative targets, not
hard cuts.

## Pacing maths

These are written at **~140 words per minute**, which is an unhurried explaining
pace. Narration alone therefore runs 12–18 minutes per script; the rest of the
runtime is **demo time** — running commands, reading output aloud, clicking through
the Dev UI and the console.

Measured narration length, so you can see which scripts have the most headroom:

| Script | Words | Narration only |
|---|---|---|
| 1 · Setup & Foundations | ~2,500 | ~18 min |
| 2 · Brand Style | ~2,380 | ~17 min |
| 3 · Deal Pricing | ~1,850 | ~13 min |
| 4 · Vendor Clearance + Legal | ~2,370 | ~17 min |
| 5 · Orchestrator | ~2,140 | ~15 min |
| 6 · UI Renderer / A2UI | ~1,910 | ~14 min |
| 7 · Identity & Gateway | ~1,680 | ~12 min |
| 8 · Run the Flows | ~1,815 | ~13 min |

Steps 3, 6, 7 and 8 are the leanest — if a read-through lands short of the target,
those are the ones to deepen first.

The runtimes assume you **cut the waiting**. Several steps kick off a cloud deploy
that takes 3–6 minutes; the scripts are written so you keep talking through a jump
cut rather than sitting in silence. Where a deploy is genuinely running in the
background, the script says so.

## Voice

**Connected prose, no filler.** Every sentence carries a fact, an instruction, or a
reason. If a sentence only labels or summarises the sentence next to it, delete it.

**Cut labelling sentences.** "That's blast radius made concrete." "That's the pattern
to take away." "Here's the thing." "The thing worth noticing is…" These announce a
point instead of making one.

**Cut reader management.** No "it's worth noting", "worth pausing on", "I'd like you
to", "let me be precise", "worth appreciating for a moment", "before we X, let's Y".
Just do the thing.

**Cut hedges.** fairly, genuinely, quite, rather, actually, somewhat, generally,
usually, essentially, basically. They dilute and add nothing.

**Cut throat-clearing openers.** Sentences starting "Now," "So," "Right," "Well,".

**Say it once.** If two sentences make the same point in different words, keep the
better one.

**Still: complete sentences, joined with connectives.** No fragment stacks, no
one-line dramatic reveals, no `[BEAT]` markers.

**Never define by negation.** No "it's not X, it's Y". No "we don't X, we do Y". No
trailing "Not a prompt." State the positive claim.

Bad: "That's blast radius made concrete. A compromised pricing agent can look up
prices, and it has no route to writing a contract."
Good: "A compromised pricing agent can look up prices and has no route to writing a
contract."

Shorter is fine. A tight 15-minute script beats a padded 25-minute one.

## The through-line

Every step is a variation on one idea, and each script restates it in its own terms:

> The model does the **fuzzy** work. Deterministic code does the **deciding**.
> Governance sits **in the traffic path**.

If a segment doesn't serve that, it's a candidate for the cutting-room floor.

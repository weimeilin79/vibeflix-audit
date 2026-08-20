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

**News anchor meets true-crime storyteller.** Think a broadcast segment crossed with
Rotten Mango. Clear and factual, but it pulls you along.

Two halves, and you need both:

**The news half — clarity.**
- Lead with the headline. Say the finding first, explain it second.
- Short sentences. One idea each.
- Plain words. *Stop*, not *cease*. *Shows*, not *demonstrates*.
- No throat-clearing. Cut "it's worth noting", "I want you to", "let me be precise".
- Never "simply" or "just".

**The story half — pull.**
- **Set a scene.** Not "there is a race condition". Instead: "The request leaves.
  It lands on replica A. The poll comes back — and hits replica B."
- **Ask the question the viewer is already thinking.** "So why not let one model do
  all of it?" Then answer it.
- **Hold the reveal.** State the symptom. Pause. Then the cause.
- **Use fragments for punch.** "404. Task not found. For a task that is running fine,
  three metres away."
- **Present tense** for anything happening on screen.
- **End every step on a hook** into the next one.

Phrases that fit this voice: *Here's the thing. Watch what happens. And this is where
it gets interesting. Nothing is broken — that's the point.*

Bad: "Now, this is a detail worth dwelling on, because it speaks to something
fundamental about how these systems are architected."

Good: "Here's the part that catches everyone. Watch."

Do not let the story half win over accuracy. Drama comes from the real failure, never
from overselling it.

## The through-line

Every step is a variation on one idea, and each script restates it in its own terms:

> The model does the **fuzzy** work. Deterministic code does the **deciding**.
> Governance sits **in the path**, not in a document.

If a segment doesn't serve that, it's a candidate for the cutting-room floor.

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
pace. Roughly 2,600–3,200 spoken words per script.

The runtimes assume you **cut the waiting**. Several steps kick off a cloud deploy
that takes 3–6 minutes; the scripts are written so you keep talking through a jump
cut rather than sitting in silence. Where a deploy is genuinely running in the
background, the script says so.

## Voice

Second person, present tense, no hype. Three rules that keep it consistent:

1. **Name the failure before the fix.** Every trap in these scripts is one that
   actually happened during the build — say what it looks like when it goes wrong,
   then what to do. That's the part viewers remember.
2. **Never say "simply" or "just".** If it were simple it wouldn't need a video.
3. **Explain the mechanic, not the menu.** Clicking is obvious; *why the system is
   shaped this way* is not. When in doubt, cut a click and add a sentence of why.

## The through-line

Every step is a variation on one idea, and each script restates it in its own terms:

> The model does the **fuzzy** work. Deterministic code does the **deciding**.
> Governance sits **in the path**, not in a document.

If a segment doesn't serve that, it's a candidate for the cutting-room floor.

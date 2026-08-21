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

**Connected prose, plainly written.** Somebody explaining their own system to a
colleague, in full sentences, at an unhurried pace.

**Write in complete sentences and let them vary in length.** Paragraphs are
paragraphs, not stacks of fragments. "Four kinds of expertise. Four people. Three
weeks." should be "That's four kinds of expertise, which in practice means four
people, a shared inbox, and roughly three weeks of back and forth."

**Make the point in the sentence where it arrives.** Do not set something up and then
drop a one-line reveal underneath it. The rhythm of tension-and-payoff reads as
performance, and it gets tiring across eight videos.

**Join ideas with connectives** — because, so, which means, given that, once, after,
and that's why. Causal explanation carries the weight that dramatic pauses were
carrying before.

**Never define something by what it is not.** No "it's not X, it's Y". No "we don't
X, we do Y". No trailing "Not a prompt." fragment. State the positive claim and move
on. If a misconception genuinely needs naming, give it a full sentence of its own.

**No `[BEAT]` markers.** Pacing should come from sentence construction. Keep
`[SCREEN: …]` and `[DO: …]`, which are production notes rather than delivery cues.

**Plain words.** Stop rather than cease, shows rather than demonstrates. Avoid
"simply" and "just" entirely — if it were simple it wouldn't need a video.

**Name the failure, then the fix.** Every trap in these scripts is one that really
happened during the build. Describe what it looks like when it goes wrong and what to
do about it, in ordinary sentences.

Bad: "That's not a bug we're tolerating. That's the test passing."
Good: "That 403 is the test passing, because those services are deployed with no
public access and nothing has been granted the invoker role yet."

## The through-line

Every step is a variation on one idea, and each script restates it in its own terms:

> The model does the **fuzzy** work. Deterministic code does the **deciding**.
> Governance sits **in the traffic path**.

If a segment doesn't serve that, it's a candidate for the cutting-room floor.

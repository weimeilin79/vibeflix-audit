# Video scripts — Vibeflix Audit workshop

One script per workshop step, written to be **read aloud word for word**. Source of
truth for the technical content is `../lab.en.md`; when the lab changes, the script
for that step needs a pass.

## Files

| # | Script | Lab section | Target |
|---|---|---|---|
| 1 | `step-1-setup-and-foundations.md` | Setup & Foundations | 15–18 min |
| 2 | `step-2-brand-style-agent.md` | The Brand Style Agent | 16–19 min |
| 3 | `step-3-deal-pricing-agent.md` | The Deal Pricing Agent | 14–17 min |
| 4 | `step-4-vendor-clearance-and-legal.md` | Vendor Clearance + Legal | 18–21 min |
| 5 | `step-5-orchestrator.md` | The Orchestrator | 16–19 min |
| 6 | `step-6-ui-renderer-a2ui-frontend.md` | UI Renderer, A2UI, Frontend | 14–17 min |
| 7 | `step-7-identity-gateway-registry.md` | Identity, Gateway & Registry | 30–34 min |
| 7b | `step-7-explainer-identity-in-plain-words.md` | *(companion — no lab section)* | 11–14 min |
| 8 | `step-8-run-the-flows-observability.md` | Run the Flows, Observability | 14–17 min |

## The companion explainer

`step-7-explainer-identity-in-plain-words.md` is optional and has no lab section
behind it. Step 7 carries the most unfamiliar vocabulary in the workshop — principals,
SPIFFE, certificates, bound tokens, mTLS, ingress and egress — and this one explains
all of it through a single sustained picture: an office building with a security desk.

It introduces no commands. Every idea maps to one object in that building, and the
last two minutes translate every object back to its real name, so it works as a
primer before the main Step 7 or as a repair afterwards.

Keep the metaphor consistent if you edit it. One building, one desk, badges, day
passes, a runner, and a list. Mixing in a second metaphor is what makes explainers
like this fall apart.

## Conventions

Everything in the file is one of four things, and they're visually distinct so you
can read past the ones that aren't spoken:

- **Plain paragraphs** — say these out loud, as written.
- **`[SCREEN: ...]`** — what should be visible. Not spoken.
- **`[DO: ...]`** — the action you perform on camera. Not spoken.
Section headers carry a running time so you can pace yourself:
`## 04:00 — Why the tool decides, not the model`. Those are cumulative targets, not
hard cuts.

## Pacing maths

These are written at **~140 words per minute**, which is an unhurried explaining
pace. Narration alone therefore runs 12–18 minutes per script; the rest of the
runtime is **demo time** — running commands, reading output aloud, clicking through
the Dev UI and the console.

Measured narration length, so you can see which scripts have the most headroom:

| Script | Spoken words | Narration only |
|---|---|---|
| 1 · Setup & Foundations | ~1,650 | ~12 min |
| 2 · Brand Style | ~1,415 | ~10 min |
| 3 · Deal Pricing | ~1,110 | ~8 min |
| 4 · Vendor Clearance + Legal | ~1,555 | ~11 min |
| 5 · Orchestrator | ~1,285 | ~9 min |
| 6 · UI Renderer / A2UI | ~1,105 | ~8 min |
| 7 · Identity & Gateway | ~3,355 | ~24 min |
| 7b · Explainer (companion) | ~1,565 | ~11 min |
| 8 · Run the Flows | ~1,110 | ~8 min |

Step 7 is the outlier, carrying roughly twice the narration of any other step, because
it explains what was already enforcing the mesh before the gateway existed and then what
the gateway adds. Steps 3, 6 and 8 are the leanest, so if a read-through lands short of
its target, deepen those first.

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

**No colon-introductions or dash-asides in spoken prose.** "Hold one picture: an office
building" and "the Conditions column is empty — that's the platform layer" both read as
written text. Say them as two sentences. Colons inside code spans and literal values are
fine.

**Explain the mechanism where you name it.** A bare error code or role name dropped into
a sentence sends the listener looking for the reason. Give the reason in the same breath:
"a config that also names a `service_account` fails with a 400, because the agent identity
already serves as that engine's workload identity".

**Complete sentences, joined with connectives.** No fragment stacks and no one-line
dramatic reveals.

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

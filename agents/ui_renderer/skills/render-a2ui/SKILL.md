---
name: render-a2ui
description: >-
  Two presentation tasks: (1) render an arbitrary set of compliance-workflow reports
  as an A2UI surface — one card per report, with a title, a plain-language headline,
  and a line per issue with a "how to resolve" hint; (2) DESIGN the console's dynamic
  input form — given the tokens the mesh asked for and the surrounding context, choose
  the right control for each (text / textarea / number / select with options), label
  it, hint the expected format, and prefill what's already known.
metadata:
  version: "4.0.0"
  domain: presentation
---

# Render the audit result

You receive a JSON object of compliance-workflow reports — **one entry per
workflow that ran**. The set is NOT fixed: today there may be three (brand style,
IP counsel, deal pricing), tomorrow more (or fewer). Never assume a count or a
specific set — reason about whatever you are given.

You EMIT THE A2UI directly. The component catalog and message schema you must follow are
given to you below, in the A2UI JSON SCHEMA block — that schema is authoritative for
*what you may emit*; this skill tells you *what to build with it*.

Be strictly faithful to the reports — NEVER invent an issue that isn't there. Keep every
string concise.

## The layout

Emit exactly two messages: a `beginRendering` naming the root, then a `surfaceUpdate`
carrying every component. Each message object has EXACTLY ONE top-level key — the message
name — and the surface's contents live inside it (`{"surfaceUpdate": {"surfaceId": …,
"components": […]}}`), never at the top level.

Render one **Card per report**, in the order the reports appear — never a report without its
Card. When you are given a single report (the usual case), that report's Card IS the root;
don't wrap it in anything. Each Card's child is a **Column**, whose children are, in order:

1. A **Text** with `usageHint: "h5"` — `"<title incl emoji> — **<STATUS>**"`.
   Infer the title from the report's `agent` field (or the object key), e.g.
   `brand_style_compliance_agent` → `🎨 Brand Style`, `vendor_clearance_agent` →
   `⚖️ Vendor & Licensing`, `deal_pricing_agent` → `💰 Deal Pricing`. For an
   unfamiliar workflow, derive a clean name and pick an emoji that suits its domain
   (⚖️ legal, 🎨 design, 🎬 story, 🔒 security, 💰 pricing, 📦 sourcing, …).
   Take the report's `status` VERBATIM — never reword it — and upper-case it
   (`needs_input` → `NEEDS_INPUT`), so every panel reads the same.
2. A **Text** (no `usageHint`) — one short, plain-language sentence summarizing the
   outcome for a non-expert.
3. **One Text per issue / finding / problem.** Reports vary in shape, so **reason about
   where the problems live** — they may be under `findings`, `issues`, a `message`, a
   `question`, or elsewhere. Prefix `⛔` for blocking/critical, `⚠️` for warnings. When
   the report suggests a fix, follow that Text with a **Text** with `usageHint:
   "caption"`: `"↳ how to resolve: <suggestion>"`. A clean report adds no issue Texts.
4. **Positive confirmations** — if a report carries a success confirmation such as a
   `legal_cleared` string, an executed **contract id** (e.g. `LC-6042`), or a newly-created
   **vendor id** (e.g. `VND-0009`), SURFACE it: add a `✅` Text stating those concrete
   identifiers verbatim, and name them in the headline too. A cleared onboarding must SHOW
   what it produced (e.g. "✅ Vendor VND-0009 onboarded · contract LC-6042 executed"),
   never just "passed".

Text supports simple Markdown (`**bold**`, `*italic*`) — use it sparingly, for emphasis.

# Design the input form (task: "design_input_form")

When the input JSON instead has `"task": "design_input_form"`, the mesh paused to
ask the operator for more information, and YOU design the form. **This task emits NO
A2UI**: reply with a single raw JSON object `{"prompt": …, "fields": […]}` and nothing
else — no `<a2ui-json>` block, no code fence, no commentary. You receive:

- `needs` — the field tokens the workflows asked for. **One field per token, and the
  field's `name` MUST be the token VERBATIM** — the backend merges answers by name.
- `questions` — what the workflows asked, in their words.
- `reports` — the current workflow reports (context for what each token means:
  a report's `question`, findings, or `pending_workflow` often spell out exactly
  what's needed, e.g. create_vendor's required sub-fields).
- `known_inputs` — everything the operator already provided.
- `select_options` — authoritative option lists for specific tokens (e.g. the
  registry's licensed characters). If present for a token, you MUST use them.

For each token, reason from the context and design the control. A field is
`{"name", "label", "type", "placeholder", "value", "required", "options"}`, where
`options` is a list of `{"value", "label"}` (empty unless `type` is `select`):

- **type** — `textarea` for free-form / multi-part details (e.g. onboarding info
  listing several sub-fields); `select` (with `options`) when the answer is a
  choice the question enumerates (yes/no approvals, option A/B decisions, or a
  `select_options` list); `number` for quantities/amounts; `text` for ids, names,
  and short values.
- **label** — short, human-friendly, says what the value is FOR.
- **placeholder** — the expected format or the sub-fields to include, extracted
  from the question/report (e.g. "legal name, HQ country, operating territories,
  product categories…" or "UL / CE / ASTM certificate id").
- **value** — prefill when the context already contains the obvious answer
  (e.g. a visual guess the report extracted, or a matching `known_inputs` entry).
- **required** — true unless the question marks it optional.

Set `prompt` to ONE clear instruction merging the workflows' questions (plain
language, no duplication). Never invent tokens that aren't in `needs`, and never drop one.

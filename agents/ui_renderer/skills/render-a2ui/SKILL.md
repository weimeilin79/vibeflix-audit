---
name: render-a2ui
description: >-
  Two presentation tasks: (1) turn an arbitrary set of compliance-workflow reports
  into user-friendly panels (title, status, headline, per-issue lines with a "how
  to resolve" hint); (2) DESIGN the console's dynamic input form — given the tokens
  the mesh asked for and the surrounding context, choose the right control for
  each (text / textarea / number / select with options), label it, hint the
  expected format, and prefill what's already known.
metadata:
  version: "3.0.0"
  domain: presentation
---

# Render the audit result

You receive a JSON object of compliance-workflow reports — **one entry per
workflow that ran**. The set is NOT fixed: today there may be three (brand style,
IP counsel, deal pricing), tomorrow more (or fewer). Never assume a count or a
specific set — reason about whatever you are given.

Produce **one panel per report**, in the order the reports appear. For each panel:

- **title** — a short, human-friendly name for that workflow, with a fitting emoji.
  Infer the name from the report's `agent` field (or the object key), e.g.
  `brand_style_compliance_agent` → `🎨 Brand Style`, `vendor_clearance_agent` →
  `⚖️ Vendor & Licensing`, `deal_pricing_agent` → `💰 Deal Pricing`. For an
  unfamiliar workflow, derive a clean title and pick an emoji that suits its
  domain (⚖️ legal, 🎨 design, 🎬 story, 🔒 security, 💰 pricing, 📦 sourcing, …).
- **status** — copy the report's `status` field VERBATIM.
- **headline** — one short, plain-language sentence summarizing the outcome for a
  non-expert.
- **lines** — one entry per issue / finding / problem in that report. Reports vary
  in shape, so **reason about where the problems live** — they may be under
  `findings`, `issues`, a `message`, a `question`, or elsewhere. For each:
  - `text`: a clear explanation. Prefix `⛔` for blocking/critical, `⚠️` for warnings.
  - `resolve`: a concrete, actionable suggestion for how to fix it.
  - A clean report (no problems) → `lines` is an empty list.
- **Positive confirmations** — if a report carries a success confirmation such as a
  `legal_cleared` string, an executed **contract id** (e.g. `LC-6042`), or a newly-created
  **vendor id** (e.g. `VND-0009`), SURFACE it: add a `✅` line stating those concrete
  identifiers verbatim (no `resolve` needed), and name them in the `headline` too. A cleared
  onboarding must SHOW what it produced (e.g. "✅ Vendor VND-0009 onboarded · contract
  LC-6042 executed"), never just "passed".

Be strictly faithful to the data — NEVER invent issues that aren't in a report.
Keep every string concise. Respond only with the structured schema.

(In this task, leave `prompt` empty and `fields` an empty list.)

# Design the input form (task: "design_input_form")

When the input JSON instead has `"task": "design_input_form"`, the mesh paused to
ask the operator for more information, and YOU design the form. You receive:

- `needs` — the field tokens the workflows asked for. **One field per token, and the
  field's `name` MUST be the token VERBATIM** — the backend merges answers by name.
- `questions` — what the workflows asked, in their words.
- `reports` — the current workflow reports (context for what each token means:
  a report's `question`, findings, or `pending_workflow` often spell out exactly
  what's needed, e.g. create_vendor's required sub-fields).
- `known_inputs` — everything the operator already provided.
- `select_options` — authoritative option lists for specific tokens (e.g. the
  registry's licensed characters). If present for a token, you MUST use them.

For each token, reason from the context and design the control:

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
language, no duplication). Leave `panels` an empty list in this task. Never
invent tokens that aren't in `needs`, and never drop one.

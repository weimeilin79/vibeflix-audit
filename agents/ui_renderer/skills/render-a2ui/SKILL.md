---
name: render-a2ui
description: >-
  Turn an arbitrary set of compliance-workflow reports into user-friendly panels
  (title, status, headline, and per-issue lines with a "how to resolve" hint).
  Reasons about however many reports arrive and whatever shape they take.
metadata:
  version: "2.1.0"
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

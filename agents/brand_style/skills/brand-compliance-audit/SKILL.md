---
name: brand-compliance-audit
description: >-
  Extract a product mockup's printed text, classify its product medium from the
  image, then run the deterministic brand-compliance pipeline (typo +
  printed-medium + asset-source gate) via the run_brand_audit tool. Use for any
  mockup/asset compliance audit.
allowed-tools: run_brand_audit
metadata:
  version: "2.0.0"
  domain: brand_style
  # ADK surfaces these tools to the model once this skill is activated.
  adk_additional_tools:
    - run_brand_audit
---

# Brand Compliance Audit

The audit runs via one tool, `run_brand_audit`, which REQUIRES three inputs:
`text`, `medium`, and `image_uri`. You must have ALL three, obtained legitimately,
before you call it — never guess or fabricate them.

## 1. Gather the inputs
- **`image_uri`** — the mockup's storage link (e.g. a Cloud Storage `gs://…` URI).
  Take it from the known context or the conversation.
- **`text`** — EXTRACT by actually reading the mockup image attached to the request
  (its printed strings). Report ONLY text you can genuinely read in the attached
  image. NEVER invent or guess plausible-sounding text.
- **`medium`** — the physical product it will be MANUFACTURED/PRINTED as. If the
  request explicitly states a medium (e.g. "the vendor states the product medium is
  'vinyl figure box'"), use exactly that — the vendor knows the manufacturing plan.
  Otherwise CLASSIFY it yourself from the attached mockup image: name the physical
  product the artwork is, or is applied to, as a short generic product name in
  lowercase (e.g. "poster", "vinyl figure box", "t-shirt", "mug wrap", "shot
  glass"). Report what you actually SEE — do not steer toward an approved-sounding
  name; the pipeline categorizes and judges it deterministically.

## 2. If anything is missing — ask, don't proceed
Do NOT call `run_brand_audit` and do NOT invent values when something is missing.
Instead set `status`='needs_input`, list what you need in `needs`, and put a clear
question in `question`:
- **No usable image** (no link, or you cannot see the image): `needs`=["image"];
  ask for the mockup image / its approved storage link.
- **Image is visible but you genuinely cannot tell what product it is or is for**
  (rare — e.g. an abstract texture with no product context): `needs`=["medium"].
  Put your best guess, if any, in `extracted.medium` so it can pre-fill the field,
  and ask in `question`, e.g. "I can't tell what product this artwork is for — what
  medium will it be manufactured/printed as?". Still fill
  `extracted.text`/`extracted.image_uri` with what you have.

## 3. When you have all three
Call `run_brand_audit(text=…, medium=…, image_uri=…)` exactly once. It runs the
whole fixed pipeline and returns `{status, checks, checks_run, findings}`. Then:
- If it returns `status`='rejected' (the image source failed the gate), set report
  `status`='rejected', `needs`=["image"], copy its `findings`, and in `question` ask
  the user to provide an image from an APPROVED source
  (`gs://vibeflix-approved-assets/…` or an approved Vibeflix URL) so you can re-run.
- Otherwise copy the tool's `status`, `checks_run`, and `findings` into the report,
  leave `question` EMPTY, and fill `extracted` with the text/medium/image_uri you
  passed in — except `extracted.medium`: if the tool returned a `medium_category`
  (the canonical approved medium it matched), report THAT as `extracted.medium` so
  the report carries the categorized medium, not the raw visual read.

Always respond by filling the BrandStyleReport schema — never reply in prose.

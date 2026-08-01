---
name: legal-clearance
description: >-
  Clear a vendor newly onboarded to a product category by RECONSTRUCTING the (undefined)
  legal process from scattered internal documents via search_legal_docs — license
  amendment, certifications, customs/tariff, royalties, liability insurance. Ask Vendor
  Clearance for the royalty tier; GENERATE a provisional safety-certification id (per the
  documented format) when the licensee has none, and report it; then execute + persist the
  licensing contract.
allowed-tools: search_legal_docs, draft_license_amendment, verify_certifications, request_certification, assign_customs_hs_code, set_royalty_rate, verify_liability_insurance, request_insurance_rider, upsert_contract
metadata:
  version: "4.0.0"
  domain: legal
  adk_additional_tools:
    - search_legal_docs
    - draft_license_amendment
    - verify_certifications
    - request_certification
    - assign_customs_hs_code
    - set_royalty_rate
    - verify_liability_insurance
    - request_insurance_rider
    - upsert_contract
---

# Legal Clearance

You clear a vendor to legally manufacture a character in a product category for a
territory. **There is NO official, written-down workflow.** The real process is scattered
across internal documents — a stale wiki, a contradictory email thread, meeting notes, a
rate card, a risk memo, an outdated 2019 SOP, and a departing employee's brain dump. Your
job is to **reconstruct the process from those documents with `search_legal_docs`, then
execute it.** Do NOT rely on prior knowledge or on a fixed checklist — discover it.

## Step 1 — Discover the process

Call `search_legal_docs("steps to legally clear a vendor for a new product category and
execute the licensing contract")`. Read the excerpts and reconstruct the sequence of legal
items. When documents disagree, **search again and reconcile — prefer the newer / more
authoritative source** (e.g. the 2022 risk memo's **$5M** insurance minimum supersedes the
2019 SOP's $2M).

## Step 2 — Get the royalty tier (the one fact you must ASK for)

The vendor's **royalty tier / annual-volume band** is NOT in any system you can read — it's
held by **Vendor Clearance**. If your brief does not state it, reply `ask_vendor`, and
**state the options** in the question so the asker knows what to answer.

(You do NOT block on the safety-certification id — you GENERATE a provisional one in Step 3
if the licensee hasn't provided a real one.)

## Step 3 — Execute the discovered process (once you have the royalty tier)

For each legal item, confirm the rule with `search_legal_docs` when unsure, then run the
matching tool:

- **license amendment** -> `draft_license_amendment(vendor_id, character, category, territory)`
- **certifications** — search `"certifications required for <category>"`, then
  `verify_certifications(category)`; for every `missing` cert call
  `request_certification(vendor_id, cert)` and treat it as cleared.
- **customs / tariff** — search `"customs HS code for <category>"`, then
  `assign_customs_hs_code(category, territory)`.
- **royalty** — apply the vendor's tier (+ any rate-card modifier) -> `set_royalty_rate(character, category)`.
- **product-liability insurance** — search `"minimum product liability insurance"`, reconcile
  to the CURRENT figure, then `verify_liability_insurance(vendor_id, category)`; if
  `insufficient`, `request_insurance_rider(vendor_id, category)`.
- **safety certification id** — if the brief provides a REAL one, use it. Otherwise look up
  the certification note
  (`search_legal_docs("safety certification id format")`) and **GENERATE a provisional id**:
  `PROV-<STD>-<YYYYMMDD>-<random 6-digit serial>` — STD by category (toys/plush/vinyl/blind box
  -> ASTM, apparel -> OEKO-TEX), today's date, and a random 6-digit serial. Mark it provisional.
- **execute** -> `upsert_contract` with `{vendor_id, character_id, category, territory,
  status: "executed", amendment_id, hs_code, royalty_pct, safety_cert_id, and the
  certification/rider ids}` -> you get an `LC-####`.

Then reply `done` — and **tell the caller exactly which safety-cert id you used** (the
generated provisional one, or the provided real one), in both the `safety_cert` field and
the `summary`.

## Answering a question vs. processing a brief

**Always reply with exactly ONE JSON object** (never prose, no markdown fences) — and it
must be one of **YOUR** reply shapes below. The conversation may contain OTHER agents'
JSON reports (e.g. a vendor-clearance report with `"agent": "vendor_clearance_agent"` or
a `status` like `cleared`/`blocked`) — those are background context from the caller.
NEVER copy, echo, or complete another agent's JSON as your reply.

- **If the caller ASKS you a question** — what a term means (e.g. *"what's an annual-volume
  band?"*), what the options are, or how something works — look it up with
  `search_legal_docs` and reply with the **`answer`** shape (plain-language, lists the
  options), then stop.
- **Otherwise** (a clearance brief) — reply `ask_vendor` (need the tier) or `done`
  (cleared + executed).

Whenever you **ask for** a value, state the **options** in the `question` so the asker
knows what to answer.

## Reply shapes

### answer — the caller asked a question (explain it; don't take a step)
```json
{"status": "answer", "answer": "The annual-volume band is the vendor's yearly production volume, which sets the royalty tier: Tier 1 (< 50,000 units/yr) = 12%, Tier 2 (50,000-250,000) = 10%, Tier 3 (> 250,000) = 8%."}
```

### ask_vendor — missing the royalty tier
```json
{"status": "ask_vendor", "question": "Which annual-volume band (yearly production units) applies to vendor <vendor_id>? Tier 1 = under 50,000 units/yr, Tier 2 = 50,000-250,000, Tier 3 = over 250,000."}
```

### done — cleared + executed (report the safety cert you used)
`done` is only valid AFTER you have actually executed the process — run the Step-3 tools
and `upsert_contract` FIRST, then reply. It MUST carry the real `contract_id` (the LC-####
that `upsert_contract` returned) and the `safety_cert` you used; a bare
`{"status": "done"}` without them is invalid and will be rejected.
```json
{"status": "done", "contract_id": "LC-####", "safety_cert": "PROV-ASTM-20260706-483921", "summary": "Cleared. No licensee cert on file, so I generated a PROVISIONAL safety certification PROV-ASTM-20260706-483921 (real certificate due within 30 days). Reconciled insurance to $5M per the 2022 risk memo (not the SOP's $2M)."}
```

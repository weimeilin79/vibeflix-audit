---
name: legal-clearance
description: >-
  Clear a vendor newly onboarded to a product category by RECONSTRUCTING the (undefined)
  legal process from scattered internal documents via search_legal_docs — license
  amendment, certifications, customs/tariff, royalties, liability insurance — asking the
  vendor clearance agent or the user for anything not in a system, then execute + persist
  the licensing contract.
allowed-tools: search_legal_docs, draft_license_amendment, verify_certifications, request_certification, assign_customs_hs_code, set_royalty_rate, verify_liability_insurance, request_insurance_rider, upsert_contract
metadata:
  version: "3.0.0"
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
execute the licensing contract")`. Read the excerpts and reconstruct the sequence of
legal items. The documents will also tell you that **two facts are NOT held in any
system** and must be obtained from someone:

- the vendor's **royalty tier / annual-volume band** — held by **Vendor Clearance**;
- the licensee's **safety-certification id** — held by the **user / licensee** (it is not
  on any vendor record; a human must provide it).

When documents disagree, **search again with a specific question and reconcile — prefer
the newer / more authoritative source** (e.g. the 2022 risk memo's **$5M** insurance
minimum supersedes the 2019 SOP's $2M).

## Step 2 — Get the two facts you don't have (ask in this order)

Check your brief:

- If the **royalty tier** is not stated → reply `ask_vendor`.
- Else if the **safety-certification id** is not stated → reply `needs_user`.

(Reply shapes below. You'll be re-invoked with the answer added to your brief.)

## Step 3 — Execute the discovered process (only once you have BOTH facts)

For each legal item you found in Step 1, confirm the rule with `search_legal_docs` when
unsure, then run the matching tool:

- **license amendment** → `draft_license_amendment(vendor_id, character, category, territory)`
- **certifications** — search `"certifications required for <category>"`, then
  `verify_certifications(category)`; for every `missing` cert call
  `request_certification(vendor_id, cert)` and treat it as cleared.
- **customs / tariff** — search `"customs HS code for <category>"`, then
  `assign_customs_hs_code(category, territory)`.
- **royalty** — apply the vendor's tier (+ any category modifier from the rate card) →
  `set_royalty_rate(character, category)`.
- **product-liability insurance** — search `"minimum product liability insurance"` and
  reconcile to the CURRENT figure, then `verify_liability_insurance(vendor_id, category)`;
  if `insufficient`, call `request_insurance_rider(vendor_id, category)` and treat as cleared.
- **execute** → `upsert_contract` with `{vendor_id, character_id, category, territory,
  status: "executed", amendment_id, hs_code, royalty_pct, safety_cert_id, and the
  certification/rider ids}` → you get an `LC-####`.

Then reply `done`.

## Reply shapes — ALWAYS one JSON object, never prose, no markdown fences

### ask_vendor — missing the royalty tier
```json
{"status": "ask_vendor", "question": "What is the current royalty tier (annual-volume band) on record for vendor <vendor_id>?"}
```

### needs_user — missing the safety-certification id
```json
{"status": "needs_user", "question": "Provide the product safety certification id (UL/CE/ASTM number) for <category> so legal can execute the contract.", "needs": ["legal_safety_cert"]}
```

### done — cleared + executed
```json
{"status": "done", "contract_id": "LC-####", "summary": "one short line per legal item cleared (mention you reconciled the $5M insurance vs the SOP's $2M)"}
```

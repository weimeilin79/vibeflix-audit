---
name: legal-clearance
description: >-
  Clear every legal item for a vendor newly onboarded to a product category (license
  amendment, certifications, customs/tariff, royalties, liability insurance), asking the
  vendor clearance agent or the user for anything you're missing, then execute + persist
  the licensing contract.
allowed-tools: draft_license_amendment, verify_certifications, request_certification, assign_customs_hs_code, set_royalty_rate, verify_liability_insurance, request_insurance_rider, upsert_contract
metadata:
  version: "2.0.0"
  domain: legal
  adk_additional_tools:
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
territory. You need TWO facts that may not be in your brief. **Always reply with a single
JSON object** — never prose — in exactly one of these shapes:

## 1. Missing the vendor's ROYALTY TIER → ask the vendor clearance agent

If your brief does NOT state the vendor's **royalty tier** (annual-volume band), you
cannot set the royalty. Ask the vendor clearance agent (it has the vendor registry):

```json
{"status": "ask_vendor", "question": "What is the current royalty tier (annual-volume band) on record for vendor <vendor_id>?"}
```

You'll be re-invoked with the answer added to your brief. Do not guess the tier.

## 2. Have the tier, but missing the licensee's SAFETY CERTIFICATION ID → ask the user

If your brief HAS the royalty tier but does NOT state a **safety certification id**
(the licensee's UL/CE/ASTM certificate number), ask the user for it:

```json
{"status": "needs_user", "question": "Provide the product safety certification id (UL/CE/ASTM number) for <category> so legal can execute the contract.", "needs": ["legal_safety_cert"]}
```

This question travels up to the user; you'll be re-invoked once they answer.

## 3. Have BOTH the royalty tier and the safety certification id → clear + execute

Run the checklist (loop until nothing is `pending` / `conditional` / `insufficient`):

1. `draft_license_amendment(vendor_id, character, category, territory)`.
2. `verify_certifications(category)` → for each `missing` cert call
   `request_certification(vendor_id, cert)`, then treat certifications as cleared.
3. `assign_customs_hs_code(category, territory)`.
4. `set_royalty_rate(character, category)` (apply the royalty tier you were given).
5. `verify_liability_insurance(vendor_id, category)` → if `insufficient`, call
   `request_insurance_rider(vendor_id, category)`, then treat insurance as cleared.
6. `upsert_contract` with `{vendor_id, character_id, category, territory,
   status: "executed", amendment_id, hs_code, royalty_pct, safety_cert_id, and the
   certification/rider ids}` — persists the agreement (`LC-####`).

Then reply:

```json
{"status": "done", "contract_id": "LC-####", "summary": "one short line per legal item cleared"}
```

**Always output ONLY the single JSON object — no prose, no markdown fences.**

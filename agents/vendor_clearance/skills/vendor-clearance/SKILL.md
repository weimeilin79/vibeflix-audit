---
name: vendor-clearance
description: >-
  Clear a licensed character with a SPECIFIC manufacturing vendor for a territory +
  product category: verify the vendor exists (onboard it if not), then check
  exclusivity collisions, trademark/customs registration, the vendor's eligibility,
  and marketplace leaks. Report as a ClearanceReport.
allowed-tools: get_vendor, create_vendor, update_vendor, find_vendors, check_vendor_eligibility, scan_global_exclusivity_clauses, verify_trademark_record, scan_ecom_marketplaces
metadata:
  version: "3.0.0"
  domain: vendor_clearance
  adk_additional_tools:
    - get_vendor
    - create_vendor
    - update_vendor
    - find_vendors
    - check_vendor_eligibility
    - scan_global_exclusivity_clauses
    - verify_trademark_record
    - scan_ecom_marketplaces
---

# Vendor & Licensing Clearance

You clear a licensed character to be manufactured by a **specific vendor**. A clearance
is ALWAYS for one named vendor — there is no such thing as a clearance without a vendor.
Work top to bottom; stop and ask (`needs_input`) whenever you don't have what a step
requires. Do the steps IN ORDER — never run the Step 2 checks before Steps 0 and 1.

## Step 0 — gather the inputs (ask for anything missing)

You need FOUR things — do NOT assume or guess any of them. **If VENDOR is empty, that
alone means you MUST stop and ask** (return `needs_input` with `needs` including
`"vendor"`) — do not run any exclusivity/trademark/eligibility checks without a vendor.

- **VENDOR** — the manufacturing vendor to apply for (`{vendor?}`; an id like `VND-1001`
  or a name).
- **CHARACTER** — the licensed character / trademark (`{character_id?}`).
- **TERRITORY** — the target market (`{target_market?}`).
- **CATEGORY** — the manufactured product category (`{product_category?}`). Derive it
  ONLY if a manufacturing medium makes it unambiguous (vinyl figure box / vinyl figures /
  figures → `Vinyl Figures`, plush → `Plush`, T-shirt → `Apparel`, statue → `Resin
  Statues`, blind box → `Blind Box`). **Never** guess the category from the character; a
  "poster / print ad" medium is NOT a manufacturable category.

If any of these is missing/empty, return the ClearanceReport with `status:
"needs_input"`, a `question` naming exactly what you need, and `needs` listing the
missing tokens (any of `"vendor"`, `"character"`, `"territory"`, `"category"`). Stop.

## Step 1 — verify the vendor exists (onboard it if not)

Call the **`get_vendor`** tool with the vendor ID FIRST.

- If it returns an **error / not found**, the vendor isn't onboarded yet. Look at the
  **`create_vendor` tool's own parameters** to see what a vendor record requires — its
  REQUIRED fields (`legal_name`, `hq_country`) and the key optional ones
  (`operating_territories`, `product_categories`, …). Return the ClearanceReport with
  `status: "needs_input"`, `needs: ["new_vendor"]`, a `question` that asks the user for
  exactly those fields (list them), and a `pending_workflow` of
  `{tool: "create_vendor", reason, params}` (fill `params` with whatever you already
  know, e.g. the vendor name + the CATEGORY as a product category + the TERRITORY as an
  operating territory). Stop — you'll be re-invoked with the details.
- When the details arrive (in `{new_vendor?}` or the message), call the
  **`create_vendor`** tool with the `vendor_json` — set `"status": "active"` so the newly
  onboarded vendor is immediately usable (do NOT set it to pending_review) — then
  continue to Step 2.
- If `get_vendor` returns a record, use it and continue.

## Step 2 — clear the character for this vendor

Using VENDOR, CHARACTER, TERRITORY, and CATEGORY:

1. **Exclusivity** — Call `scan_global_exclusivity_clauses` with the character ID and target market. If
   `has_conflict`, record an `exclusivity_collision` issue (severity `critical`), set
   `partner_conflict`, and describe the block + expiration.
2. **Trademark / customs** — Call `verify_trademark_record` with the character ID and target market. If
   `registration_status` isn't `Valid` or `territory_status` isn't `registered`, record
   a `trademark_customs` issue (severity `warning`).
3. **Vendor eligibility** — Call `check_vendor_eligibility` with the vendor ID, target market, product category, and character ID. Put the vendor in `recommended_vendors` with `vendor_id`, `legal_name`,
   `hq_country`, its `eligible` flag, and a `note` (the first blocking reason, if any).

   **Category onboarding:** if the ONLY reason the vendor is ineligible is that it does
   NOT manufacture CATEGORY (it IS active, cleared for the territory, and there's no
   exclusivity lock), do NOT just block. Instead offer to add the category: return the
   ClearanceReport with `status: "needs_input"`, `needs: ["add_category_approved"]`, a
   `question` asking the user to approve adding CATEGORY to this vendor's approved
   categories, and a `pending_workflow` of `{tool: "update_vendor", reason, params:
   {vendor_id, updates: {product_categories: [existing… + CATEGORY]}}}`. Stop.
   - When you're re-invoked and `{add_category_approved?}` is "yes":
     1. call `update_vendor` to add CATEGORY to the vendor's `product_categories`;
     2. call `check_vendor_eligibility` again to confirm it's now eligible;
     3. set `status: "cleared"` and finish. (You do NOT call any legal tool — the
        workflow detects that you ran `update_vendor` and automatically hands off to
        the independent Legal agent to execute the licensing contract.)
   - If the vendor is ineligible for any OTHER reason (suspended, not cleared for the
     territory, or an exclusivity lock), just record a `vendor_ineligible` issue
     (severity `critical`) — do not offer onboarding.
4. **Marketplace leaks** — Call `scan_ecom_marketplaces` with the character ID and target market → `ecom_status`.

Set `status` to `blocked` if there is an exclusivity collision OR the vendor is not
eligible; otherwise `cleared`. Output the ClearanceReport schema only — never prose.

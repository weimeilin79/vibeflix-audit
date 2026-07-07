---
name: deal-pricing-audit
description: >-
  Audit the vendor's AGREED total consideration (royalty rate + advance + minimum guarantee)
  for using the IP against the mcp_licensing rate card. Compute the expected deal, compare
  each component, mark vendor CLAIMS as unresolved for the loop to adjudicate, and return
  APPROVED / NEEDS_ADJUSTMENT / UNDERPRICED.
allowed-tools: get_license_pricing
metadata:
  version: "1.0.0"
  domain: licensing
  adk_additional_tools:
    - get_license_pricing
---

# Deal Pricing Audit

You audit the price the vendor AGREED to pay to use the IP on their product. You do NOT set
the price — you validate theirs against the licensor's rate card. You judge the money only;
form-fit, exclusivity, and design are other agents' jobs.

## Step 1 — Pull the rate card + expected deal
Call `get_license_pricing(character_id, product_category, territory, volume, net_unit_price)`.
If `found` is false, return `status: "flagged"`, `verdict: "NEEDS_ADJUSTMENT"`, one component
noting no rate card. Keep the returned `rate_card` and the `expected` block in your output.

## Step 2 — Read the EXPECTED deal (do NOT compute it yourself)
The tool already returned an `expected` block: `effective_rate`, `volume_mult`, `royalty`,
`mg`, `advance`. Use those numbers **verbatim** — never re-derive the arithmetic; the tool is
the single source of truth. (If `expected` is missing, `net_unit_price`/`volume` weren't
provided — say so as a component and rule NEEDS_ADJUSTMENT.)

## Step 3 — Evaluate each component (agreed vs expected)
Emit a `components` list, one entry each for `royalty_rate`, `mg`, `advance`:
- `clear` — agreed is within `tolerance_pct` of expected AND not below any floor.
- `unresolved` — agreed is LOWER than expected BUT the vendor appears to rely on a factor
  that must be checked (e.g. a volume-tier discount). Set `claim` to what they rely on. The
  reconcile loop will adjudicate it.
- `discrepancy` — agreed is off with no legitimate factor. Set `below_floor: true` if it
  breaches a hard floor (`agreed_royalty_rate < min_royalty_rate`, or `agreed_mg <
  mg_rule.floor_usd`).
Structural checks (always `discrepancy` if violated): `agreed_advance <= agreed_mg`.

## Step 4 — Verdict
The reconcile loop settles it after adjudicating `unresolved` items:
- any `discrepancy` with `below_floor` -> **UNDERPRICED** (blocked)
- any other `discrepancy` -> **NEEDS_ADJUSTMENT** (flagged)
- else -> **APPROVED** (cleared)

## Output shape (one JSON object)
```json
{
  "agent": "deal_pricing_agent",
  "expected": { "effective_rate": 0.1449, "royalty": 13041, "mg": 100000, "advance": 20000 },
  "agreed":   { "rate": 0.08, "advance": 8000, "mg": 30000 },
  "rate_card": { "...": "the get_license_pricing result" },
  "components": [
    { "name": "royalty_rate", "agreed": 0.08, "expected": 0.1449, "status": "unresolved", "claim": "volume-tier discount", "below_floor": false },
    { "name": "mg",           "agreed": 30000, "expected": 100000, "status": "discrepancy", "below_floor": true },
    { "name": "advance",      "agreed": 8000,  "expected": 20000,  "status": "discrepancy", "below_floor": false }
  ]
}
```
(`status`/`verdict` at the top level are filled by the reconcile loop, not you.)

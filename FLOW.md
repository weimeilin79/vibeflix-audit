# Vendor & Licensing Clearance — flow

How an audit flows through the mesh, with a focus on the `vendor_clearance` agent and
the `legal` agent it hands off to.

---

## 1. Mesh topology (who calls whom)

The orchestrator fans out to **brand_style ‖ vendor_clearance ‖ deal_pricing**. The
`legal` agent is **not** dispatched by the orchestrator and is **not** in readiness — it's
a standalone agent that, **in this demo, only `vendor_clearance` hands off to** (only that
service is given `LEGAL_A2A_URL`), though any agent could.

```
                            ┌──────────── app (:8000) ────────────┐
   browser ◄──SSE──────────►│  React + FastAPI + Orchestrator      │
                            └───┬─────────┬─────────┬──────────┬───┘
                          A2A   │    A2A  │    A2A  │   A2A     │ (paint)
                    ┌───────────▼─┐ ┌─────▼──────┐ ┌▼────────┐ ┌▼───────────┐
   orchestrator ──► │ brand_style │ │  vendor_   │ │ pricing │ │ ui_renderer│
   fans out to      │             │ │ clearance  │ │         │ │            │
   these 3          └──┬───────┬──┘ └─┬────┬───┬─┘ └─────────┘ └────────────┘
                       │       │      │    │   │
             mcp_brand │  mcp_ │ mcp_ │ mcp│   │  A2A  (hand-off — only vendor_clearance
              _style   │ vision│ lic. │ mkt│   └──────►  has LEGAL_A2A_URL) ────────┐
                                                                                    ▼
                                                              ┌──────────────────────────┐
                                                              │  legal  (:8005)          │
                                                              │  independent A2A service │
                                                              │  NOT in orchestrator      │
                                                              │  fan-out / readiness      │
                                                              └───────────┬──────────────┘
                                                                          │ writes contract
                                                                          ▼  mcp_licensing
```

---

## 2. Inside `vendor_clearance` (the decision flow)

`⏸` = pauses and asks the user (async `needs_input` → resume). Terminal states are the
three `ClearanceReport.status` values: `cleared` / `blocked` / `needs_input`.

```
             ┌─────────────────────────────────────────────┐
             │ STEP 0 — gather inputs                       │
             │  need: VENDOR, CHARACTER, TERRITORY, CATEGORY│
             └───────────────────┬─────────────────────────┘
                                 │
                any missing?  ───►  YES ─► needs_input(needs:[…])  ──►  ⏸ ask user, re-run
                                 │          (VENDOR missing = hard stop)
                                 ▼ all present
             ┌─────────────────────────────────────────────┐
             │ STEP 1 — get_vendor(VENDOR)                  │
             └───────────────────┬─────────────────────────┘
                                 │
              ┌──────────────────┴───────────────────┐
         NOT FOUND                                  FOUND
              │                                        │
              ▼                                        ▼
   needs_input(needs:['new_vendor'])       ┌─────────────────────────────────┐
   reads create_vendor's fields            │ STEP 2 — clear for this vendor  │
   pending_workflow: create_vendor         │  • scan_global_exclusivity      │
              │                             │  • verify_trademark_record      │
   ⏸ ask user for details, re-run          │  • check_vendor_eligibility     │
              │                             │  • scan_ecom_marketplaces       │
   create_vendor(status:active) ───────────┤                                 │
                                            └───────────────┬─────────────────┘
                                                            │
                                          eligible? ────────┼─────────────────┐
                                                            │                 │
                                                   YES ─► CLEARED       NO, and only reason
                                                                        = category not made?
                                                                              │
                                    ┌─────────────────────────────────────────┤
                          NO (suspended / wrong territory / exclusivity lock)  │ YES
                                    ▼                                          ▼
                                 BLOCKED                    needs_input(needs:['add_category_approved'])
                                 (vendor_ineligible /       pending_workflow: update_vendor
                                  exclusivity_collision)              │
                                                            ⏸ "add category X to vendor?" — approve?
                                                                      │ yes
                                                                      ▼
                                                     ┌────────────────────────────────────┐
                                                     │ CATEGORY ONBOARDING                 │
                                                     │ 1. update_vendor (add CATEGORY)     │
                                                     │ 2. hand off ► legal (see §3)        │
                                                     │ 3. finalize on legal's pass/fail    │
                                                     └────────────────┬───────────────────┘
                                                                      ▼
                                                          CLEARED (+ legal_cleared line)
```

---

## 3. Inside `legal` (RAG-discovers the process, asks for what it's missing, executes)

There is **no defined legal workflow** — the process is scattered across the docs in
`resource/legal/docs/`. The agent **RAG-discovers** it with **`search_legal_docs`**
(local keyword retriever by default; Vertex AI RAG Engine when `RAG_CORPUS` is set),
reconstructing the steps + the two facts it must ask for, and reconciling contradictions
(e.g. the 2022 risk memo's $5M insurance supersedes the 2019 SOP's $2M). It then replies
with ONE JSON object — `ask_vendor`, `needs_user`, or `done`:

```
   receive {vendor, character, category, territory, (royalty tier?), (safety cert?)}
        │
        ├─ no royalty tier in brief   →  {status:"ask_vendor", question}   (Flow A, see §5)
        ├─ no safety cert in brief    →  {status:"needs_user", question, needs:[legal_safety_cert]}  (Flow B)
        └─ have both  →  loop until nothing pending:
             draft_license_amendment ──► LA-####
             verify_certifications ──► request_certification (each missing) ─► cleared
             assign_customs_hs_code ──► HS code + recordation
             set_royalty_rate ──► rate %
             verify_liability_insurance ──► request_insurance_rider ─► cleared
             upsert_contract(...) ──► LC-#### (REAL write to mcp_licensing._CONTRACTS)
                  │
                  ▼
             {status:"done", contract_id:"LC-####", summary}
```

---

## 4. The legal hand-off — current vs. planned

**Streaming today:** app → browser is streamed (SSE). But the vendor_clearance → legal
call is currently an **`AgentTool`** — a *blocking sub-call folded into one
vendor_clearance turn*. That single turn ends up doing `update_vendor` + the whole legal
loop + emitting the big final report, which is too long and makes the final report
malform.

**Implemented — `vendor_clearance` is a declarative ADK 2.0 graph; the app never touches
legal.** Each step is its own node (so `legal_clearance` shows up distinctly in the
Agent Platform / ADK trace):

```
  START → clearance → legal_clearance → finalize

  clearance (@node):        ctx.run_node(clearance_reasoner)  # conversational LLM (no output_schema)
                            → emit ClearanceReport
  legal_clearance (@node):  runs ONLY if a category was onboarded (the update_vendor fact);
                            ctx.run_node(legal, {vendor,character,category,territory})
                            # ▲ vendor_clearance → legal directly (A2A); the app is NOT involved
                            legal: self-loop ─► upsert_contract ─► PASS/FAIL + LC-####
                            → merge legal's pass/fail into the report
  finalize:                 emit the final report (content = what A2A returns to the orchestrator)
```

(Earlier this was one `clear_and_legal` node doing all three; it was split into three
nodes purely for observability — same behavior, `legal` now visible as its own step.)

Why this fixed the malform: with the old `AgentTool`, legal's result came back *inside*
the reasoner's turn, so that one turn did update + legal + the big `set_model_response`
report → malformed. Now (a) the reasoner is **conversational** (no `output_schema`, so
no `set_model_response` finalizer to malform), and (b) legal runs as its **own child
run** via `ctx.run_node`; the node then writes the final report in a small deterministic
step. Legal **reports pass/fail back** (the contract id), and the node "picks up where
it left off."

**How the node knows legal is needed (no guessing):** it does NOT rely on the reasoner
emitting a signal or on string-matching `add_category_approved`. It runs legal when a
**fact in the event log** says a vendor was onboarded for a category — the reasoner
actually called **`create_vendor`** (a NEW vendor) or **`update_vendor`** (a NEW category
on an existing vendor) and the vendor came back `cleared` — OR when we're **resuming a
legal Q&A** (a `legal_safety_cert` was echoed into the report; see §5 Flow B). Params
(vendor/character/category/territory) are read from the reasoner's real
`check_vendor_eligibility` call args. A normal cleared result (no onboarding, no
pending answer) never triggers legal.

Notes:
- A remote-agent workflow node's **`node_input` and `ctx.state` are unreliable** (state
  doesn't propagate over A2A; node_input is often empty). What DOES work is **LlmAgent
  state templates** — the reasoner resolves `{vendor?}`, `{add_category_approved?}`,
  `{legal_safety_cert?}` etc. from the orchestrator-seeded state. So values the graph
  code needs (like the safety cert) are **echoed by the reasoner into its report**, and
  the nodes read them from there.
- `mcp_licensing`'s stores are **in-memory and persist** across requests until the
  container restarts — restart `mcp_licensing` (+ its dependents) to reset test data.

---

## 5. Legal's clarifying questions — two loops

Legal can ask for information it's missing. Two distinct paths:

**Flow A — legal ↔ vendor_clearance (internal, auto-resolved):** legal needs a fact from
the vendor registry (e.g. the vendor's royalty tier). It replies `ask_vendor`; the
`legal_clearance` node answers it *itself* using the **`vendor_liaison`** LLM (which has
the `mcp_licensing` read tools), appends the answer to legal's brief, and re-invokes
legal. This loops inside the node — it never leaves the service, no user involvement.

```
  legal_clearance node loop:
    legal → {ask_vendor: "royalty tier for VND-1002?"}
         → vendor_liaison looks it up → "Tier-2 / high-volume"
         → re-brief legal with the answer → legal continues
```

**Flow B — legal → user (propagates all the way up and back):** legal needs a fact only
the user/licensee has (the safety certification id). It replies `needs_user`; the node
turns the `clearance_report` into `needs_input` carrying legal's question + the
`legal_safety_cert` token. This rides the **existing** needs_input path up to the user:

```
  UP:   legal → needs_user  →  clearance_report = needs_input{question, needs:[legal_safety_cert]}
        → orchestrator compile_ui  →  app renders a field  →  USER
  DOWN: /api/audit/resume{legal_safety_cert} → orchestrator ingest → state
        → reasoner echoes legal_safety_cert into its report → legal_clearance re-enters
          (resuming=True) → legal has the cert → done → LC-####
```

Note the re-run trigger: on resume the category is already onboarded, so `update_vendor`
won't recur — the **echoed `legal_safety_cert`** is what re-enters legal (see §4). Both
loops were verified end-to-end (Flow A: liaison answers the royalty question; Flow B:
`input_required` → resume → contract executed).

---

## 6. Demo matrix — frontend inputs to trigger every path

Frontend fields: **Character**, **Target Market**, **Product Category**, **Vendor**,
**Volume**, **Medium** (optional — blank → brand_style classifies it from the mockup
image; type/pick to override, e.g. `shot glass` to trigger the unapproved-medium
path) (image optional). Some paths ask a follow-up field (shown in the last column).
Registry reference below the table.

### A. `vendor_clearance` asks for missing input (`needs_input`)
| # | Character | Market | Category | Vendor | → Outcome / follow-up |
|---|---|---|---|---|---|
| A1 | grogu | Europe | Resin Statues | *(blank)* | Asks **which vendor** (hard gate) → answer **Vendor** |
| A2 | *(blank)* | Europe | Resin Statues | VND-1002 | Asks for the **character** → answer **Character** |
| A3 | grogu | Europe | *(blank)*, Medium=`poster` | VND-1002 | Asks for a **product category** (poster isn't manufacturable) |

### B. Vendor doesn't exist → onboard a new vendor
| # | Character | Market | Category | Vendor | → Outcome / follow-up |
|---|---|---|---|---|---|
| B1 | grogu | Europe | Resin Statues | `Acme Toys Ltd` (unknown) | Asks for **new-vendor details** (reads `create_vendor` fields) → answer **New Vendor** → vendor created `active` → clears |

### C. Active exclusivity collision → `blocked`
| # | Character | Market | Category | Vendor | Contract hit |
|---|---|---|---|---|---|
| C1 | grogu | North America | Vinyl Figures | VND-1001 | EXC-4471 Hasbro |
| C2 | gremlins | North America | Action Figures | VND-1001 | EXC-5120 NECA |
| C3 | gremlins | Europe | Vinyl Figures | VND-1006 | EXC-5588 Super7 |
| C4 | stitch | Asia-Pacific | Vinyl Figures | VND-1004 | EXC-5333 Bandai |
| C5 | minions | North America | Plush | VND-1003 | EXC-5567 Mattel |

### D. Expired exclusivity → does NOT block (clears)
| # | Character | Market | Category | Vendor | Note |
|---|---|---|---|---|---|
| D1 | little_green_men | North America | Action Figures | VND-1001 | EXC-5450 Mattel **expired** → cleared |

### E. Vendor ineligible for a reason OTHER than category → `blocked`
| # | Character | Market | Category | Vendor | Reason |
|---|---|---|---|---|---|
| E1 | grogu | Europe | Apparel | VND-1005 | vendor **suspended** |
| E2 | grogu | Europe | Vinyl Figures | VND-1004 | not cleared for **Europe** (Osaka = APAC only) |
| E3 | grogu | Latin America | Resin Statues | VND-1011 | vendor **pending_review** (not active) |

### F. Fully cleared (happy path, no legal)
| # | Character | Market | Category | Vendor | Note |
|---|---|---|---|---|---|
| F1 | grogu | Europe | Resin Statues | VND-1002 | active, in-territory, native category, no exclusivity |
| F2 | stitch | Latin America | Plush | VND-1009 | clean clear (stitch registered everywhere, no exclusivity in LatAm/Plush) |
| F3 | grogu | Latin America | Vinyl Figures | VND-1003 | cleared **+ trademark_customs warning** (grogu LatAm = *pending*) |

### G. Category onboarding → **Legal** (Flow A always, Flow B on the cert)
| # | Character | Market | Category | Vendor | Flow |
|---|---|---|---|---|---|
| G1 | grogu | Europe | Apparel | VND-1002 | Ineligible **only** for category → asks **Approve add category?** = `yes` → `update_vendor` → **legal fires**: liaison answers royalty (**Flow A**), then legal asks **safety cert** (**Flow B**) → `input_required` → answer **legal_safety_cert** (e.g. `UL-778812`) → contract `LC-####` |
| G2 | grogu | North America | Premium Collectibles | VND-1008 | same onboarding→legal path on a different vendor |

### H. Sourcing gate (HITL) — volume over the 25 000 cap
| # | Inputs | → Outcome / follow-up |
|---|---|---|
| H1 | F1's inputs **+ Volume = 40000** | cleared, then **sourcing choice** asked → answer `A` (split excess to addendum SC-7798-EU) or `B` (cap + cancel excess) |

### I. Orchestrator dispatch (which workflows run)
| # | Action | → Outcome |
|---|---|---|
| I1 | Any initial audit | dispatch runs **all 3** (brand_style ‖ vendor_clearance ‖ deal_pricing) |
| I2 | Re-submit changing only the market/vendor | dispatch **re-runs only the affected** workflow(s), reuses the rest (see the `__plan__`) |

> In the mesh **brand_style** returns `needs_input` (no real image travels over A2A) and
> **deal_pricing** audits the agreed price (royalty + advance + MG) — both appear on every audit alongside vendor_clearance.

### Registry reference (from `mcp_licensing/data.py`)
- **Vendors** — 1001 Shenzhen (APAC/NA · Vinyl/Action/BlindBox), 1002 Bavaria (EU/NA ·
  Resin/Premium), 1003 Guadalajara (NA/LatAm · Action/Plush/Vinyl), 1004 Osaka (APAC ·
  Vinyl/BlindBox/Sofubi), **1005 Istanbul (EU/MEA · Apparel — SUSPENDED)**, 1006 Kraków
  (EU/NA · Vinyl/Action), 1007 Maple/CA (NA · Vinyl/Plush/Action), 1008 Liberty/US (NA/LatAm ·
  Action/Vinyl/Resin), 1009 Amazônia/BR (LatAm/NA · Plush/Vinyl/Novelty), 1010 Andina/CO
  (LatAm · Action/Apparel/Accessories), **1011 Pampas/AR (LatAm · Resin/Premium —
  PENDING_REVIEW)**, 1012 Taipei (APAC/NA · Vinyl/BlindBox/Action).
- **Active exclusivity** — grogu·NA·Vinyl/Action (Hasbro), gremlins·NA·Action (NECA),
  gremlins·EU·Vinyl (Super7), et·EU·BlindBox (Funko), stitch·APAC·Vinyl (Bandai),
  minions·NA·Plush (Mattel). **Expired** — grogu·EU·BlindBox (Funko), lgm·NA·Action (Mattel).
- **Trademark caveats** — grogu & lgm are *pending* in Latin America, *unregistered* in
  Middle East & Africa (→ trademark_customs warnings); stitch/gremlins/minions registered
  everywhere.
- **Characters**: `grogu`, `gremlins`, `et`, `stitch`, `little_green_men`, `minions`.
  The **Character/trademark field is a registry-driven dropdown** — the frontend fetches
  `GET /api/trademarks` (app → `mcp_licensing.list_trademarks`) so you pick a valid id
  and can't mistype it (e.g. "Minion" ≠ `minions`, which silently misses the trademark
  AND exclusivity records). The follow-up form the agent shows for a missing character is
  the same dropdown. Add a trademark to the registry → it appears automatically.

---

## 7. Live workflow graph (right pane)

The frontend is split: **chat on the left, a live workflow graph on the right** (SVG,
`WorkflowGraph` in `ChatAudit.jsx`). It builds as the run goes, lights each node up, and
shows status — driven by structured **`graph` SSE events** the app emits alongside the
A2UI panels (`_stream_audit`):

```
{event:"graph", op:"plan",   nodes:[{id,label,run}]}          // all workflows (run + reused)
{event:"graph", op:"status", id, status}                      // per node, as its panel fills
{event:"graph", op:"status", id:"legal", parent:"vendor_clearance_agent", status}  // legal sub-node
```

Graph shape: `Orchestrator → (each workflow)`, plus `vendor_clearance → Legal` when the
legal agent acts. Node colors: running (blue, pulsing) · cleared/compliant
(green) · blocked (red) · needs_input (amber) · reused (dashed grey). It's **plan-driven**
like the panels — adding a workflow to `_AGENTS` makes it appear with no frontend change.
Verified: plan builds the nodes, each lights up as its agent returns, and the `legal`
node appears under vendor_clearance on the onboarding path.

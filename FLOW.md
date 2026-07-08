# Vendor & Licensing Clearance — flow

How an audit flows through the mesh, with a focus on the `vendor_clearance` agent and
the `legal` agent it hands off to.

---

## 1. Mesh topology (who calls whom)

The orchestrator fans out to **brand_style ‖ vendor_clearance ‖ deal_pricing**. The
`legal` agent is **not** dispatched by the orchestrator and is **not** in readiness — it's
a standalone agent that, **in this demo, only `vendor_clearance` hands off to** (only that
service is given `LEGAL_A2A_URL`), though any agent could.

**Contract finalization**: the orchestrator's `contract_finalize` node (after
`generate_report`, the step that closes every run) owns the *decision* that a fully-passed audit must end with an executed
licensing contract — but it *delegates* the execution: it re-invokes `vendor_clearance`
with a `FINALIZE-CONTRACT` brief, and `vendor_clearance` hands off to its private legal
agent exactly as it does for onboarding (legal never gets a second caller). If onboarding
already papered a contract in this audit chain, the orchestrator reuses that LC-####
instead. Result → `aggregate["contract"]` → the final clearance report + audit history.

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
reconstructing the steps + the one fact it must ask for, and reconciling contradictions
(e.g. the 2022 risk memo's $5M insurance supersedes the 2019 SOP's $2M). The licensee
**safety-certification id does NOT block**: if the brief provides a real one it's used,
otherwise legal **generates a PROVISIONAL id** (`PROV-<STD>-<YYYYMMDD>-<serial>`, per the
documented format — real cert due within 30 days) and reports which one it used. It
replies with ONE JSON object — `ask_vendor` or `done` (a bare `done` without the real
`contract_id` from `upsert_contract` is invalid and gets re-briefed):

```
   receive {vendor, character, category, territory, (royalty tier?), (safety cert?)}
        │
        ├─ no royalty tier in brief   →  {status:"ask_vendor", question}   (Flow A, see §5)
        └─ have the tier  →  loop until nothing pending:
             draft_license_amendment ──► LA-####
             verify_certifications ──► request_certification (each missing) ─► cleared
             assign_customs_hs_code ──► HS code + recordation
             set_royalty_rate ──► rate %
             verify_liability_insurance ──► request_insurance_rider ─► cleared
             safety cert: use the provided one, else GENERATE PROV-<STD>-<date>-<serial>
             upsert_contract(...) ──► LC-#### (REAL write to mcp_licensing._CONTRACTS)
                  │
                  ▼
             {status:"done", contract_id:"LC-####", safety_cert, summary}
```

---

## 4. The legal hand-off — how it works

**`vendor_clearance` is a declarative ADK 2.0 graph; the app never touches legal.** Each
step is its own node (so `legal_clearance` shows up distinctly in the Agent Platform /
ADK trace):

```
  START → clearance → legal_clearance → finalize

  clearance (@node):        ctx.run_node(clearance_reasoner)  # conversational LLM (no output_schema)
                            → emit ClearanceReport (+ state finalize_requested, from the
                              deterministic FINALIZE-CONTRACT marker in the brief)
  legal_clearance (@node):  runs on onboarding / finalize / resume (see below);
                            _call_legal(brief)  # plain A2A message/send in a FRESH context
                            # ▲ vendor_clearance → legal directly; the app is NOT involved
                            legal: self-loop ─► upsert_contract ─► PASS/FAIL + LC-####
                            → merge legal's pass/fail into the report (fail-closed: no
                              LC-#### after MAX rounds → blocked, never silent success)
  finalize:                 emit the final report (content = what A2A returns to the orchestrator)
```

(History: this began as a blocking `AgentTool` inside one reasoner turn — too long, the
final report malformed — then one `clear_and_legal` node, then three nodes for
observability. The legal call itself was later changed from `ctx.run_node(RemoteA2aAgent)`
to a **fresh-context A2A `message/send`**: forwarding the workflow's session history made
legal intermittently ECHO the clearance report back as its own reply, and the hop's event
relabeling made the reply unreliable to read back. A clean per-call context removed both.)

**How the node knows legal is needed (no guessing):** it does NOT rely on the reasoner
emitting a signal or on string-matching `add_category_approved`. It runs legal when:
- a **fact in the event log** says a vendor was onboarded for a category — the reasoner
  actually called **`create_vendor`** (a NEW vendor) or **`update_vendor`** (a NEW
  category) and the vendor came back `cleared`; or
- the **orchestrator requested contract finalization** — its `contract_finalize` node
  re-invokes this agent with a brief starting with the literal `FINALIZE-CONTRACT`
  marker (see §1) after every workflow passed; or
- we're **resuming a legal Q&A** (a `legal_safety_cert` was echoed into the report —
  a legacy Flow-B path, see §5).

Params (vendor/character/category/territory) are read from the reasoner's real
`check_vendor_eligibility` call args. A normal cleared result (no onboarding, no
finalize request, no pending answer) never triggers legal.

Notes:
- A remote-agent workflow node's **`node_input` and `ctx.state` are unreliable** (state
  doesn't propagate over A2A; node_input is often empty). What DOES work is **LlmAgent
  state templates** — the reasoner resolves `{vendor?}`, `{add_category_approved?}` etc.
  from the orchestrator-seeded state. Values the graph code needs are **echoed by the
  reasoner into its report**, and the nodes read them from there.
- `mcp_licensing`'s **vendors are Firestore-backed** (collection `vendors` when
  `FIRESTORE_DATABASE` is set — the compose default): onboarded vendors/categories
  SURVIVE restarts; reset demo state with `RESET_VENDORS=1 python
  deploy/seed_firestore.py`. Trademarks/exclusivity/contracts remain in-memory
  (reset by restarting `mcp_licensing` + its dependents).

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

**Flow B — legal → user (LEGACY for the safety cert; the channel remains):** legal used
to block on the licensee safety-certification id with a `needs_user` reply that rode the
existing needs_input path up to the user and back (`legal_safety_cert` field →
`/api/audit/resume` → reasoner echoes it → legal resumes). **Since 2026-07-07 the cert no
longer blocks** — legal generates a provisional `PROV-…` id when none is provided (skill
v4) — so this path doesn't fire in the demo anymore. The plumbing (the `legal_safety_cert`
token, the resume trigger in §4) is kept: it's the generic pattern for any future fact
only the user holds, and a real cert id supplied up-front is still used verbatim.

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

### F. Fully cleared (happy path — no *onboarding* legal; if brand + pricing also pass, the orchestrator's `contract_finalize` still ends the audit with an executed contract)
| # | Character | Market | Category | Vendor | Note |
|---|---|---|---|---|---|
| F1 | grogu | Europe | Resin Statues | VND-1002 | active, in-territory, native category, no exclusivity |
| F2 | stitch | Latin America | Plush | VND-1009 | clean clear (stitch registered everywhere, no exclusivity in LatAm/Plush) |
| F3 | grogu | Latin America | Vinyl Figures | VND-1003 | cleared **+ trademark_customs warning** (grogu LatAm = *pending*) |

### G. Category onboarding → **Legal** (Flow A royalty Q&A; cert self-generated)
| # | Character | Market | Category | Vendor | Flow |
|---|---|---|---|---|---|
| G1 | grogu | Europe | Apparel | VND-1002 | Ineligible **only** for category → asks **Approve add category?** = `yes` → `update_vendor` → **legal fires**: liaison answers royalty (**Flow A**), legal **generates a provisional safety cert** (`PROV-…`, no user ask) → contract `LC-####` in the report |
| G2 | grogu | North America | Premium Collectibles | VND-1008 | same onboarding→legal path on a different vendor |

### H. Volume over the 25 000 cap → sourcing decision (HITL, inside `generate_report`)
| # | Inputs | → Outcome / follow-up |
|---|---|---|
| H1 | F1's inputs **+ Volume = 40000** | cleared, then **sourcing choice** asked → answer `A` (split excess to addendum SC-7798-EU) or `B` (cap + cancel excess) |

### I. Orchestrator dispatch (which workflows run) + contract finalization
| # | Action | → Outcome |
|---|---|---|
| I1 | Any initial audit | dispatch runs **all 3** (brand_style ‖ vendor_clearance ‖ deal_pricing) |
| I2 | Re-submit changing only the market/vendor | dispatch **re-runs only the affected** workflow(s), reuses the rest (see the `__plan__`) |
| I3 | Re-submit changing only the **pricing terms** or adding a **note** about a workflow's domain | dispatch re-runs just that workflow (the note is *considered*, never obeyed — rules can't be waived by a note) |
| I4 | Every workflow **passes** (cleared/compliant, volume within cap) | orchestrator `contract_finalize` → vendor_clearance → legal execute the contract → **📜 Final Clearance Report** card with the full contract + saved to the **Audit History** tab |

> **deal_pricing** audits the agreed price (royalty + advance + MG) against the rate card
> (cards exist for `grogu`, `minions`, `stitch`, `gremlins` — `et` / `little_green_men`
> have none, which triggers the "no rate card found" path);
> **brand_style** first verifies the artwork DEPICTS the character under audit (e.g.
> claim `minions` with a Grogu mockup → `rejected` + critical `character_mismatch`,
> audit blocked until a correct image is supplied), then classifies the product medium
> from the image (an explicit medium in the form overrides — e.g. `shot glass` triggers
> the unapproved-medium path).

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

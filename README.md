# Global Merchandising License Verification & IP Infringement Counterfeit Audit

A modern, multi-agent workspace utilizing Google **ADK 2.0** for agent orchestration, **A2UI (Agent-to-User Interface)** for visual component painting, and independent, domain-grouped **Model Context Protocol (MCP)** servers to verify IP licensing and audit physical product prototypes in real time.

---

> 📖 **New here?** Start with **[`docs/`](docs/README.md)** — [the story](docs/01-the-story.md)
> (what Vibeflix licenses and why the process still needs human reasoning) and
> [the architecture](docs/02-architecture.md) (how the ten-service mesh is wired). This
> README stays lean; the narrative lives there.

> 🚀 **Deploying this?** Read **[`deploy/docs/GOTCHAS.md`](deploy/docs/GOTCHAS.md)** first — the single
> source of truth for the rules that will otherwise cost you a day. Every one of them fails
> *silently*: the deploy exits 0, the console looks right, and the mesh misbehaves in a way
> that points somewhere else. Then follow [`deploy/docs/instruction-sre.md`](deploy/docs/instruction-sre.md)
> (automated) or [`deploy/docs/instruction-dev.md`](deploy/docs/instruction-dev.md) (command by command),
> and verify each step with `./deploy/verify_deployment.sh <step>`.

## 🏗️ Architecture Design

The workspace decouples analytical logic from rendering layers to ensure clean design:

1. **Vite React Frontend**: A conversational adaptive canvas workspace styling system where users drop image prototypes or send instructions. Emits user action telemetry. Renders complex, interactive layout forms and parallel execution graphs.
2. **ADK 2.0 Python Agents**: A mesh of independent Python agents:
   - **Sourcing Orchestrator (Router)**: Captures uploads, checks parameters, coordinates state, and invokes display layouts.
   - **Brand Style Compliance Agent (Designer)**: Analyzes logo, fonts, hex swatches, and typographical compliance.
   - **Vendor & Licensing Clearance Agent (Counsel)**: Verifies exclusivity collisions (e.g. an exclusive partner vendor holding a territory lock), trademark/customs registration, and marketplace leaks — AND recommends approved manufacturing vendors eligible for the territory + product category.
   - **Deal Pricing Auditor (Cost)**: Audits the vendor's AGREED total consideration (royalty + advance + minimum guarantee) for using the IP against the licensor's rate card — an internal **evaluate→validate→iterate** loop reconciles each component and rules APPROVED / NEEDS-ADJUSTMENT / UNDERPRICED.
   - **Legal Clearance Agent**: A standalone A2A agent — **in this demo only Vendor & Licensing hands off to it, but any agent could**. It clears the legal work (license amendment, certifications, customs/tariff, royalties, insurance) and executes the licensing contract — **reconstructing the process via RAG** over scattered "tribal knowledge" docs (see *Data sources & schemas → Legal knowledge base*). It asks Vendor Clearance for the royalty tier; the licensee safety cert never blocks (it **generates a provisional `PROV-…` id** when none is on file and reports it). It fires on vendor/category **onboarding**, and on the orchestrator's **contract finalization**: when every workflow passes, the orchestrator's `contract_finalize` node re-invokes Vendor Clearance with a `FINALIZE-CONTRACT` brief so the audit always ends with an executed `LC-####` — rendered in the **📜 Final Clearance Report** and archived in the **Audit History** tab.
3. **Decoupled MCP Servers**: Structured as independent, containerizable domain servers:
   - `mcp_licensing`: Vendor registry, exclusivity contracts, and trademark records (see *Data sources & schemas*).
   - `mcp_market`: Global e-commerce scraper intelligence, Ledger capacity checkers, Governance telemetry logging.
4. **Shared A2A Task Store**: every A2A call is `POST message:send` then `GET /a2a/v1/tasks/{id}` polled to completion — so the *task* is the unit of state the whole mesh runs on. Agent Runtime scales each engine to several replicas behind a load balancer with **no session affinity**, and the A2A server's default store is a dict **private to one replica**: the `POST` lands on replica *A*, the `GET` is balanced to *B*, and you get `404 Task not found` on **86.8% of polls** (measured: 1,228 / 1,415). That one fact was the hidden cause of most of what looked broken elsewhere — slow runs, ~1,900 "error" spans, a chat blocked for 7 minutes, and `recovery` re-running agents that had never failed. So the engines keep their tasks **outside** the replicas, in a store hosted by the app (`vibeflix_common/task_store.py` → `/api/taskstore/{id}`, wired via `A2aAgent(task_store_builder=…)`). Any replica can now serve any task: misses → **0**, a full audit **5m01s → 1m44s**.

   Why *behind the app* and not the engines hitting a database directly: the Agent Gateway governs **HTTP** egress and cannot match a gRPC channel or a raw TCP socket, which rules out the *engines* reaching Cloud SQL/Postgres or Redis ([G8](deploy/docs/GOTCHAS.md#g8--the-agent-gateway-governs-http-egress-only)). The **app**, though, backs these endpoints with **Firestore** (collection `a2a_tasks`), running each op in a worker thread — so the shared store is **durable** across a restart and no longer split-brains across app replicas. The endpoints stay gated by a shared secret (`TASK_STORE_KEY`) because the app is deliberately public; if the app is ever unreachable the engines degrade to per-replica memory with a loud warning rather than failing the run. (The app is still one instance ([G5](deploy/docs/GOTCHAS.md#g5--the-app-must-be---min-instances1---max-instances1)) for its *other* in-memory state, not the task store.)

### 10-service distributed mesh

**The orchestrator is an independent agent, not a library inside the app.** The app is a
*thin client*: it calls `orchestrator` over A2A exactly the way it calls `ui_renderer`, and
the orchestrator fans out to the three domain agents **under its own agent identity** — so
the gateway's A2A egress policies are genuinely in the path. Each agent talks to its MCP
server(s) over **streamable-HTTP**. A standalone **`legal` agent** (:8005) sits behind
Vendor Clearance — in this demo only vendor_clearance hands off to it (any agent could),
and it's not in the orchestrator's fan-out. Every box is its own container/instance.

```
                    ┌─────────── app container (:8000) ───────────┐
  browser ◄──SSE───►│  React (static, streaming A2UI renderer)  +  │
   (live A2UI)      │  FastAPI /api/*     ⟵ THIN CLIENT           │
                    │  + shared A2A task store (/api/taskstore/*)  │
                    └──────┬─────────────────────────────┬────────┘
                       A2A │                         A2A │ (paint)
                 ┌─────────▼──────────┐            ┌─────▼───────┐
                 │    orchestrator    │            │ ui_renderer │
                 │  :8006 (Workflow)  │            │   :8004     │
                 └──┬───────┬───────┬─┘            │ (A2UI LLM)  │
               A2A  │  A2A  │  A2A  │              └─────────────┘
        ┌───────────▼──┐ ┌──▼───────────────┐ ┌────▼─────┐
        │  brand_style │ │ vendor_clearance │ │ pricing  │
        │     :8001    │ │      :8002       │ │  :8003   │
        └──┬───────────┘ └──┬───────────┬───┘ └────┬─────┘
   HTTP/MCP│        HTTP/MCP │           │ HTTP/MCP │
    ┌──────▼──────┐ ┌────────▼─────┐ ┌───▼──────────▼┐
    │mcp_brand_   │ │mcp_licensing │ │  mcp_market   │
    │style  :9004 │ │    :9002     │ │    :9003      │  (streamable-HTTP)
    └─────────────┘ └──────────────┘ └───────────────┘

   vendor_clearance ──A2A──►┌─────────────────────────────┐
   (on vendor/category      │          legal  :8005        │  standalone A2A agent —
    onboarding, and on the  │   (A2A server · RAG over     │  NOT in the orchestrator
    orchestrator's          │    resource/legal/docs)      │  fan-out; only vendor_
    contract_finalize)      │  executes the LC-#### deal    │  clearance hands off to it.
                            └─────────────────────────────┘
  brand_style → mcp_brand_style · vendor_clearance → mcp_licensing + mcp_market
```

### A2A transport — the stock ADK client, and the two places it needs help

Agent-to-agent calls use ADK's own **`RemoteA2aAgent`**, wrapped as
`VibeflixRemoteA2aAgent` (`vibeflix_common/remote_agent.py`). The wrapper is a subclass, so
every call site is idiomatic ADK — `ctx.run_node(agent, brief)` — and the two workarounds it
carries are invisible to callers. Both exist for reasons **measured in production, from inside a
gateway-attached engine** (2026-08-02):

| Override | Why it is unavoidable |
|---|---|
| `_resolve_agent_card` → repoint at `.mtls` | The `A2aAgent` template **hardcodes the plain aiplatform host** into the card it serves (`templates/a2a.py:328`), overwriting whatever the deployer set — there is no flag. The Agent Gateway authorizes only the `.mtls` host: measured against three peer agents, plain → `403 Egress request is not authorized`, mtls → `200`. Standard clients follow `card.url`, so without this every A2A call from an engine is refused. |
| `_construct_message_parts_from_session` → send the brief | Stock builds its outgoing message from `ctx.session.events` and never sees the brief passed to `ctx.run_node` (ADK's `run_node` hands `node_input` to the scheduler, not into the session). Without it, a hop silently receives session history instead of the brief — a plausible-looking wrong answer. |

**Fast hops run the stock transport; long hops poll.** The stock client sends
`blocking: true` — one long HTTP request — and Agent Runtime kills that at **~180s** with
`400 FAILED_PRECONDITION` ("Reasoning Engine Execution failed", *Error Details empty*) **while
the callee is still working normally**. The same `message:send` *without* blocking returns in
0.9s with a task id, and polling `tasks/{id}` retrieves the completed result. So:

```python
brand_style = VibeflixRemoteA2aAgent("brand_style_compliance_agent", BRAND_URL)
legal       = VibeflixRemoteA2aAgent("legal", LEGAL_URL, long_running=True)   # sends + polls
```

`long_running=True` changes only the pacing — same protocol, same card handling, same auth.
Hops that can exceed the ceiling (`legal`, `contract_finalize`, `app → orchestrator`) set it;
the fast dispatch agents (~9-20s) deliberately do not, so the demo exercises the prebuilt client.
Full evidence and the upstream report: [`eng-report/UPSTREAM-FR-a2a-client-gaps.md`](eng-report/UPSTREAM-FR-a2a-client-gaps.md).

### The shared A2A task store (and why it exists)

**Every A2A call is `POST message:send` then `GET /a2a/v1/tasks/{id}` until the task
finishes.** In cloud, Agent Runtime runs each engine as **several replicas behind a load
balancer with no session affinity**, and the A2A server's default `InMemoryTaskStore` is a
dict **private to one replica**. So the `POST` creates the task on replica *A*, and the
`GET` is balanced to replica *B*, which has never heard of it:

```
POST /a2a/v1/message:send   → task created on replica [17]
GET  /a2a/v1/tasks/{id}     → balanced to [19] → 404 Task not found
```

Measured on a real run: **1,228 misses / 1,415 polls = 86.8%** — and it's not even a fair
coin, because the replica that *owns* the task is the one busy executing it, so the balancer
routes away from precisely the replica you need. Nearly every problem we chased came out of
this one fact: multi-minute runs that were mostly the client losing coin flips; ~1,900
"error" spans (26% of **all** spans) that were just 404 polls; the console's chat blocked
for 7 minutes behind a form-designer task; and `recovery` re-running agents that had never
failed.

**Fix:** keep the tasks *outside* the replicas. `vertexai`'s `A2aAgent` template accepts a
`task_store_builder`, so every engine now shares one store hosted by the app
(`vibeflix_common/task_store.py` → `PUT/GET/DELETE /api/taskstore/{id}`). Any replica can
now serve any task.

| store | why not |
|---|---|
| Cloud SQL / Postgres (the SDK's own `DatabaseTaskStore`) | Postgres is **raw TCP**, and the Agent Gateway governs **HTTP** egress — it cannot match a TCP socket to a registered endpoint. Same wall that refused the Pub/Sub **gRPC** publisher (`403 Egress request is not authorized`) until it was rewritten over REST. |
| Memorystore / Redis | TCP again, plus a VPC connector the app doesn't have. |
| Firestore | HTTPS, so it *would* pass the gateway — but A2A saves the task on **every event**, and Firestore's sustained write limit is ~1/sec **on the same document**. |
| **the app (chosen)** | Plain HTTPS to a Cloud Run service — the engines already reach Cloud Run this way (it's how they call the MCP servers), so the auth story is already solved. |

**⚠️ Two constraints that are load-bearing, not tuning knobs:**

1. **The app must run as exactly one instance** (`--min-instances=1 --max-instances=1`). The
   store is a dict in the app process; two app instances would split-brain it and recreate
   the identical bug one layer up. (Bonus: one instance also fixes the mesh graph, since the
   Pub/Sub telemetry subscription is a *competing-consumer* queue — with 2+ app instances the
   events get split and the graph renders only partially.)
2. **The endpoints carry a shared secret** (`TASK_STORE_KEY`, `X-Task-Store-Key`). The app is
   **public** (`allUsers`/`run.invoker`, so the browser can load the console), so without it
   the agents' task state would be world-readable and world-writable. Cloud Run IAM can't be
   used here — locking the service down would lock out the frontend.

Nothing in the store needs to survive a restart: it's demo state, not a system of record. If
the app is unreachable, `RemoteTaskStore` logs loudly and falls back to the per-replica
store — i.e. exactly as broken as before, never worse.

Plus a standalone **`legal` agent (:8005)** — **in this demo only `vendor_clearance` hands
off to it (any agent could)**. It clears + executes the licensing contract for a
newly-onboarded vendor×category and RAGs its process from `resource/legal/docs/`. It's not
in the orchestrator fan-out or the readiness gate. See **[FLOW.md](FLOW.md)** for the full
vendor_clearance → legal flow.

The audit **streams**: `POST /api/audit/stream` (SSE) pushes A2UI `surfaceUpdate`
messages as the graph runs — the plan appears instantly, then each panel fills in as its
workflow returns (see *A2UI streaming* below). Alongside the panels, the app emits
structured **`graph` events** that drive a **live workflow graph in the right pane** —
`Orchestrator → each workflow`, plus **`⚖️ Legal Clearance`** under Vendor Clearance when
legal fires — each node lighting up with its status (running · cleared · blocked ·
needs-input · failed). See **[FLOW.md](FLOW.md) §7**.

See **[deploy/docs/README.md](deploy/docs/README.md)** for the env contract and Cloud Run / Agent Engine deployment.

---

## 📂 Project Structure

```
vibeflix/
├── frontend/                   # React app (A2UI renderer + live workflow graph)
├── agents/                     # ADK 2.0 agents (app container + 5 A2A services)
│   ├── app.py                  # FastAPI: frontend + orchestrator/ui_renderer A2A client + SSE stream
│   ├── a2ui_surface.py         # App-side A2UI assembly (panels → surface) + streaming builders + fallback
│   ├── orchestrator/           # Sourcing Orchestrator — deterministic Workflow graph (raw reports out)
│   ├── ui_renderer/            # A2UI presenter A2A service (:8004) — skills/render-a2ui/ (reports → panels)
│   ├── brand_style/            # Brand Style agent (A2A server) — skills/brand-compliance-audit/
│   ├── vendor_clearance/       # Vendor & Licensing Clearance agent — skills/vendor-clearance/
│   ├── deal_pricing/           # Deal Pricing Auditor (Workflow, loop) — skills/deal-pricing-audit/
│   └── legal/                  # Legal Clearance agent (:8005) — skills/legal-clearance/
│                               #   + legal_kb.py (search_legal_docs: local / Vertex RAG)
│                               #   (each agent's procedure = a versioned ADK Skill / SKILL.md)
├── resource/legal/docs/        # 10 scattered "tribal knowledge" legal docs (the RAG corpus source)
├── mcp_servers/                # Decoupled MCP servers (one running instance each)
│   ├── mcp_brand_style/        # Brand compliance checks (typo, printed-medium, asset-source)
│   ├── mcp_licensing/          # Vendor + trademark + exclusivity registry (in-memory, CRUD)
│   └── mcp_market/             # Scrapers, ledger limits, governance logs
├── packages/
│   └── vibeflix-common/        # Shared package (installed by every service, so each
│                               # agent/MCP image is self-contained & independently
│                               # deployable): mcp_clients, schema_guard, image_input,
│                               # memory, serve_a2a, registry. Extras: [agents] / [mcp].
├── deploy/                     # Dockerfiles (app/agent/mcp) + Cloud Run / Agent Engine guide
│                               #   + setup_legal_rag.py (provision the legal RAG corpus)
├── docker-compose.yml          # Local 10-service topology (+ legal :8005)
└── run_local.sh                # compose wrapper (up / down / smoke / logs / frontend / mesh)
```

---

## 🗄️ Data sources & schemas

Every "fact" the mesh checks lives inside an MCP server. Most are self-contained
Python data (seeded, so the demo runs with **no external database**); a few can be
overridden from Firestore when `FIRESTORE_DATABASE` is set.

| Data source | Server | Storage | Writable | Holds |
|---|---|---|---|---|
| **Vendors** | `mcp_licensing` | in-memory dict | ✅ create / update | approved manufacturing partners |
| **Trademarks** | `mcp_licensing` | in-memory dict | seed | IP/trademark registration per character |
| **Exclusivity contracts** | `mcp_licensing` | in-memory dict | seed | category × territory exclusivity locks |
| **Brand allowlist / printed media / approved asset sources** | `mcp_brand_style` | canned defaults, Firestore-overridable (`brand_style_registry`) | via Firestore | brand-compliance reference lists |
| **Sourcing caps** | `mcp_market` | canned default, Firestore-overridable (`market_policy/sourcing_caps`) | via Firestore | primary-vendor volume ceiling (25,000) |
| **Marketplace scan / audit map** | `mcp_market` | simulated | — | e-com leak scan, telemetry log |
| **Audit results** | app | Firestore `audit_history` (always); cross-audit recall in the **orchestrator's** Memory Bank (auto, via `ORCHESTRATOR_A2A_URL`) | ✅ | persisted audit runs |

> **In-memory caveat:** `mcp_licensing`'s stores are per-process, single-instance, and
> reset on restart — deliberately, so create/update are trivial for the demo. Behind the
> same tool surface, production would back them with Firestore/Postgres. *(Operational
> note: restarting an MCP server invalidates its agents' open MCP sessions — restart the
> dependent agent containers too, or they lose their tools until they reconnect.)*

### `mcp_licensing` schemas

**Vendor** — `get_vendor` · `find_vendors(territory, category, status)` · `create_vendor` · `update_vendor`:
```jsonc
{
  "vendor_id": "VND-1001",                 // assigned (VND-####) if omitted on create; immutable
  "legal_name": "Shenzhen Apex Collectibles Ltd.",   // required
  "dba": "Apex Toys",
  "hq_country": "China",                   // required
  "operating_territories": ["Asia-Pacific", "North America"],
  "product_categories": ["Vinyl Figures", "Action Figures", "Blind Box"],
  "manufacturing_capabilities": ["injection_molding", "hand_painting", "packaging"],
  "license_tier": "Tier 1 - Approved",     // Tier 1 - Approved | Tier 2 - Conditional | Tier 3 - Probation
  "status": "active",                      // active | suspended | pending_review
  "annual_capacity_units": 4500000,
  "moq": 3000,                             // minimum order quantity
  "lead_time_days": 55,
  "certifications": ["ISO 9001", "ICTI Ethical Toy", "ASTM F963"],
  "compliance_rating": "A",                // A | B | C | D
  "last_audit": "2025-11-02",
  "contact": { "name": "...", "email": "...", "phone": "..." },
  "onboarded": "2021-03-14",
  "notes": "..."
}
```

**Trademark** — `verify_trademark_record(character_id, territory?)`:
```jsonc
{
  "mark": "GROGU", "character_id": "grogu", "owner": "Lucasfilm Ltd. LLC",
  "registration_number": "US-88765432",
  "nice_classes": ["Class 28 — Toys & Games", "Class 25 — Apparel"],
  "jurisdictions": { "North America": "registered", "Latin America": "pending", "…": "unregistered" },
  "registration_status": "Valid",
  "customs_recordation": { "US_CBP": true, "EU_customs": true },
  "filed": "2020-01-10", "renewal_date": "2030-01-10", "status": "active"
}
```

**Exclusivity contract** — `scan_global_exclusivity_clauses(character_id, territory)`:
```jsonc
{
  "contract_id": "EXC-4471", "partner": "Liberty Figure Works LLC", "character_id": "grogu",
  "category": "Stylized Vinyl Figurines / Action Figures",
  "territory": "North America", "type": "exclusive",
  "effective": "2023-01-01", "expiration": "2028-12-31",
  "status": "active"                       // only ACTIVE + unexpired contracts block a release
}
```

`check_vendor_eligibility(vendor_id, territory, category)` composes all three: a vendor
is eligible only when it is `active`, cleared to operate in the territory, makes the
category, **and** no active exclusivity contract locks that category × territory.

**Seeded data** (edit `mcp_servers/mcp_licensing/server.py` to change):
- **12 vendors** (`VND-1001`–`1012`) across China, Germany, Mexico, Japan, Türkiye,
  Poland, Canada, USA, Brazil, Colombia, Argentina, Taiwan — mixed tiers/statuses.
- **6 trademarks**: Grogu (Lucasfilm), Gremlins (Warner Bros.), E.T. (Universal),
  Stitch (Disney), Little Green Men (Disney/Pixar), Minions (Universal).
- **4 exclusivity contracts** — one per region, each held by a REGISTRY vendor:
  Liberty Figure Works/VND-1008 (Grogu vinyl, NA), Kraków Vinyl Studio/VND-1006
  (Gremlins vinyl, EU), Osaka Craft Works/VND-1004 (Stitch vinyl, APAC), and
  Amazônia Brinquedos/VND-1009 (Minions plush, LatAm).

### Legal knowledge base — RAG over "tribal knowledge" (`resource/legal/docs`)

The Legal Clearance agent models a **common enterprise problem**: there is *no* official,
defined legal workflow. The process lives scattered across documents written by different
people over years — a stale wiki, a contradictory email thread, meeting notes, a Slack
export, a departing employee's brain dump. No single document has the whole picture. The
agent has to **reconstruct the process via RAG** (Vertex AI RAG Engine) instead of
following a hardcoded checklist.

The 10 seed documents in `resource/legal/docs/` (deliberately messy, overlapping, and
partly out-of-date):

| doc | format | what it (partially) reveals |
|------------------------------------|-------------------------------|--------------------------------------------------------------------|
| confluence-licensing-onboarding.md | wiki WIP                      | the 6 steps, but "ask Priya", TODOs, stale                         |
| email-thread-cert-requirements.txt | email chain                   | certs per category (plush vs vinyl vs apparel), contradictions     |
| q3-legal-sync-notes.md             | meeting notes                 | $5M insurance, "ask for royalty tier", the safety-cert action item |
| slack-export-licensing-ops.txt     | Slack                         | royalty tiers 12/10/8%, +2% premium, "query clearance for tier"    |
| insurance-risk-memo.md             | formal memo                   | $5M rule, rider process, supersedes the SOP                        |
| logistics-hs-codes.md              | spreadsheet                   | HS codes per category, recordation                                 |
| royalty-rate-card.md               | rate card v3                  | tier table + modifiers, "don't default to 12%"                     |
| SOP-license-amendments-2019.md     | outdated SOP                  | the sequence, but $2M (wrong), Schedule B "never attached"         |
| janes-onboarding-checklist.md      | personal notes                | the closest thing to a full workflow, incomplete                   |
| legal-stuff-dont-lose-this.txt     | departing-employee brain dump | ties it all together + the two "must ask" facts                    |

The legal agent queries these via a **`search_legal_docs`** tool (an in-agent
`FunctionTool` in `agents/legal/legal_kb.py` — legal is the only consumer, so no separate
MCP server is needed). Two retrievers, chosen by env:

- **default (offline):** a self-contained keyword retriever over the mounted docs — works
  in CI / locally with zero cloud setup.
- **`RAG_CORPUS` set:** **Vertex AI RAG Engine** `:retrieveContexts` via a **direct REST
  call** signed with ADC (`google.auth` only — no SDK/`pandas` in the agent image),
  against a corpus backed by the **RAG-managed Vertex AI Vector Search** store.

Provision the corpus with **`deploy/setup_legal_rag.sh`** (wraps `setup_legal_rag.py`):
it stages the docs to GCS, creates the corpus (`rag_managed_vertex_vector_search` +
`text-embedding-005`), imports them, and prints the `RAG_CORPUS` to set on the legal
agent. Flipping from the local retriever to Vertex is a config change, not a code change.

---

## 🚀 Running Locally

The system is **distributed**: 9 services (frontend+orchestrator, **4** A2A agents —
brand_style/vendor_clearance/deal_pricing/**ui_renderer** — and 4 MCP servers) wired together
with docker compose. The orchestrator + app talk to the agents over **A2A**; the
domain agents talk to the MCP servers over **streamable-HTTP**.

```bash
gcloud auth application-default login     # agents call Gemini on Vertex AI
./run_local.sh up                         # build + start all 9 services
# open http://localhost:8000  →  click "Run Live Audit (Backend)"
```

`./run_local.sh smoke` brings the mesh up and POSTs a sample audit;
`./run_local.sh down` tears it down. The app container builds the React frontend
and FastAPI serves it on the same origin as `/api/*` (port `8000`).

**Frontend dev loop (optional):** with the mesh running, `./run_local.sh
frontend` starts Vite on `:3000` against the app API (`VITE_API_URL`).

### First-time setup: Python venv (for `adk web`, `test-agent`, and the RAG scripts)

The non-Docker paths below — single-agent `adk web`, `./run_local.sh mcp` / `test-agent`,
and `deploy/setup_legal_rag.py` / `deploy/rebuild_legal_rag.sh` — run against a local
`.venv`. Build it with **`uv`** (Python 3.14's bundled pip self-upgrade is fragile; `uv`
is reliable):

```bash
cd ~/work/vibeflix-audit          # your real repo (venv bakes in absolute paths, so build it HERE)

# 1) create the venv — uv handles Python 3.14 reliably (pip self-upgrade is fragile here)
uv venv .venv

# 2) agent/backend deps (ADK 2.0 is pre-GA -> prereleases allowed)
uv pip install --python .venv/bin/python --prerelease=allow -r agents/requirements.txt

# 3) the shared package — NON-editable (editable installs break on py3.14 + uv)
uv pip install --python .venv/bin/python ./packages/vibeflix-common --no-deps

# 4) RAG provisioning deps — needed for setup_legal_rag.py / rebuild_legal_rag.sh
uv pip install --python .venv/bin/python --prerelease=allow -r deploy/requirements-legal-rag.txt

# 5) activate
source .venv/bin/activate
```

Steps 1-3 are enough for `adk web` and `test-agent`; step 4 is only needed for the RAG
scripts. A copied venv (e.g. restored from a backup) won't work — it stores absolute paths,
so always rebuild it in place.

### Test one agent in isolation (no Docker)

To iterate on a single agent without bringing up the whole A2A mesh, start the
MCP servers locally and run the agent in-process. In one shell:

```bash
./run_local.sh mcp        # starts mcp_licensing:9002, mcp_market:9003, mcp_brand_style:9004
```

In another shell:

```bash
./run_local.sh test-agent vendor_clearance --market "North America"
./run_local.sh test-agent brand_style
./run_local.sh test-agent deal_pricing --volume 40000
```

`agents/test_agent.py` runs that single agent in-process (no A2A layer), seeds the
session state it reads, defaults the `MCP_*_URL`s to the local servers, prints
every tool call, and dumps the structured report. For example, `vendor_clearance`
against North America calls its `mcp_licensing` + `mcp_market` tools over HTTP and
returns the real `ClearanceReport`:

```
→ scan_global_exclusivity_clauses(grogu, North America)   → Liberty Figure Works lock (EXC-4471)
→ verify_trademark_record(grogu, North America)           → registered
→ find_vendors(North America, Vinyl Figures, active)      → VND-1001, VND-1003
→ check_vendor_eligibility(VND-1001, North America, …)    → ineligible (exclusivity lock)
→ scan_ecom_marketplaces(grogu, North America)            → secure
status: "blocked" · exclusivity_collision (critical) · 2 vendors, both ineligible
```

> This confirms ADK 2.3 lets an agent call MCP tools **and** emit its
> `output_schema` (it injects a `set_model_response` finalizer) — tools and
> structured output coexist.

#### Testing Brand Style Agent

To poke at a single agent in the ADK web UI, start its MCP server(s) (shell 1:
`./run_local.sh mcp` — this also installs the shared `vibeflix-common` package
that the agents import; if you built the venv by hand, run `uv pip install
./packages/vibeflix-common --no-deps` too), then point `adk web` at that agent's
folder with the MCP URLs exported:

```bash
cd ~/work/vibeflix-audit
source .venv/bin/activate
export MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp
adk web agents/brand_style
```

Open http://127.0.0.1:8000, pick **brand_style**, and chat to watch the tool
calls and report in the trace view. The **agent** does the extraction itself (its
own vision on the image via the link — `gs://` by reference, `http(s)` downloaded
+ inlined), then calls **one** deterministic tool on `mcp_brand_style`,
`run_brand_audit(text, medium, image_uri)`, which runs the whole fixed pipeline in
code — the agent does **not** orchestrate the individual checks. No MCP server uses
an LLM. `run_brand_audit` **gates on the asset source**: an unapproved image link
short-circuits to `status: rejected` (content checks skipped). Output is one
`output_schema` (`BrandStyleReport`), `status` ∈ `needs_input` | `rejected` |
`flagged` | `compliant`, with a `question` for the first two.

- *"run a brand compliance audit"* (no image) → the agent **asks** for the image
  and its link — it will **not** fabricate inputs or call the tool without them.
- attach/link an **unapproved** image (e.g. a random CDN URL) → `run_brand_audit`
  returns `rejected`; the agent asks you to supply an **approved** image
  (`gs://vibeflix-approved-assets/…`).
- attach an image from an approved source → the agent extracts its text/medium via
  vision and reports the merged findings.

Export only the `MCP_*_URL`s that agent uses: brand_style needs
`MCP_BRAND_STYLE_URL`; `vendor_clearance` needs `MCP_LICENSING_URL` +
`MCP_MARKET_URL`; `deal_pricing` needs `MCP_LICENSING_URL` (for the rate card). Point `adk web` at the **single agent
folder** (not the
whole `agents/` dir, which would also try to load the orchestrator and its A2A
URLs).

#### Testing Vendor Clearance Agent

`vendor_clearance` uses `mcp_licensing` (vendors + trademarks + exclusivity) and
`mcp_market` (marketplace scan). Start the MCP servers (shell 1: `./run_local.sh mcp`),
then point `adk web` at the agent with just those two URLs exported:

```bash
cd ~/work/vibeflix-audit
source .venv/bin/activate
export MCP_LICENSING_URL=http://127.0.0.1:9002/mcp
export MCP_MARKET_URL=http://127.0.0.1:9003/mcp
adk web agents/vendor_clearance
```

Open http://127.0.0.1:8000, pick **vendor_clearance**, and try:

- *"clear grogu for North America"* → runs the exclusivity + trademark checks, finds
  Vinyl-Figure vendors, and returns the `ClearanceReport` — **blocked** by the Liberty Figure Works
  lock, with every matching vendor marked ineligible.
- *"clear grogu for Asia-Pacific"* → **cleared**, with eligible vendors (China / Japan /
  Taiwan).
- *"which active vendors can make Plush in Latin America?"* → `find_vendors`.
- *"is Gremlins locked for action figures in North America?"* → `scan_global_exclusivity_clauses`
  (Kraków Vinyl Studio holds the EU vinyl lock).
- *"onboard a vendor: Hanoi Figure Co in Vietnam, makes Vinyl Figures, operates in
  Asia-Pacific"* → `create_vendor`; *"suspend VND-1003"* → `update_vendor`.

Because every tool parameter is described in its schema (allowed territories,
categories, statuses, character IDs, and the `create_vendor` JSON shape), the agent
knows exactly what to pass for each call.

#### Testing the Legal Agent

In this demo `legal` is only called by `vendor_clearance` (though any agent could hand off
to it), but you can also drive it directly with `adk web`. It RAGs the (undefined) process from `resource/legal/docs/` via its
`search_legal_docs` tool and executes the contract via `mcp_licensing.upsert_contract`.
Start `mcp_licensing` (shell 1: `./run_local.sh mcp`), then:

```bash
cd ~/work/vibeflix-audit
source .venv/bin/activate
export MCP_LICENSING_URL=http://127.0.0.1:9002/mcp
# search_legal_docs retriever: unset RAG_CORPUS → local keyword search over the docs;
# set it (from deploy/setup_legal_rag.py) → Vertex AI RAG Engine.
export LEGAL_DOCS_DIR="$PWD/resource/legal/docs"
# export RAG_CORPUS=projects/…/locations/us-central1/ragCorpora/…   # optional: use Vertex
adk web agents/legal
```

Open http://127.0.0.1:8000, pick **legal**. Because there's no vendor_clearance to answer
its `ask_vendor` question, state the royalty tier in your prompt:

- *"What certifications does Apparel need, and what's the insurance minimum?"* → the agent
  calls `search_legal_docs` and reconstructs the answer from the scattered docs
  (reconciling the $5M risk memo vs the 2019 SOP's $2M).
- *"Run legal clearance for vendor VND-1002, character grogu, category Apparel, territory
  Europe. Royalty tier: Tier 2."* → it runs the checklist (amendment → certs → customs →
  royalty → insurance), **generates a provisional safety cert** (`PROV-…`, since none was
  given) and `upsert_contract` → returns
  `{"status":"done","contract_id":"LC-####","safety_cert":"PROV-…"}`.
- Omit the royalty tier → it returns `{"status":"ask_vendor", …}` — the same hand-off it
  uses inside the mesh (the liaison answers it there). Supply a real safety-cert id and
  it uses that verbatim instead of a provisional one.

#### Test the orchestrator with `adk web` (no Docker)

The orchestrator is a graph whose nodes are `RemoteA2aAgent` references, so it
needs the agent services running. Bring up the full backend mesh (4 MCP + 3 A2A
agent services) in one shell, then point `adk web` at the orchestrator in another.

```bash
# shell 1 — full backend mesh (Ctrl-C stops all)
gcloud auth application-default login    # agents call Vertex
./run_local.sh mesh                      # MCP :9001-:9004, agent cards :8001-:8004 (incl. ui_renderer)
```

```bash
# shell 2 — adk web on the orchestrator
cd ~/work/vibeflix-audit
source .venv/bin/activate
export BRAND_STYLE_A2A_URL=http://127.0.0.1:8001 \
       VENDOR_CLEARANCE_A2A_URL=http://127.0.0.1:8002 \
       DEAL_PRICING_A2A_URL=http://127.0.0.1:8003
adk web agents/orchestrator              # open http://127.0.0.1:8000, pick "orchestrator"
```

You'll see the workflow graph and the fan-out to the live A2A agents in the trace.
`ingest` parses your message (JSON or **plain English**), so just describe the
request and include the image link, e.g.:

```
Vendor submitted gs://vibeflix-approved-assets/vendor_request.jpg for North America, 40000 units
```
It pulls out the `gs://`/`https` link, the market (say "North America" / "Europe" /
"Asia"), and the volume (a number):
- `North America` → `vendor_clearance` returns the Liberty Figure Works **blocked** exclusivity collision.
- `40000` (> 25,000 cap) → **`generate_report`** asks for a split/cap sourcing decision
  (a collected field, Option A/B); `Europe` + `15000` → clean pass.

(A JSON payload also works: `{"target_market": "North America", "volume": 40000}`.)

Notes:
- **brand_style shows `needs_input`** here — no real image travels through the A2A
  workflow to it, so it honestly asks for one (vendor_clearance / deal_pricing are the
  meaningful nodes to watch in the mesh).
- `compile_ui` recovers each agent's report from the session events by author
  (`RemoteA2aAgent` nodes don't surface their output to the JoinNode).

**Workflow graph (in the orchestrator):**
`START → ingest → dispatch → (guard_brand ‖ guard_ip ‖ guard_story) → merge →
recovery → compile_ui → generate_report → contract_finalize → finalize`. Each guard wraps a `RemoteA2aAgent`
(an `LlmAgent` that calls its MCP server(s) as tools) and either runs it or reuses its
prior report, per the `dispatch` decision (see *Incremental re-run* below). The orchestrator is **deterministic** — it emits only the raw reports (+
the volume-cap outcome); it makes no LLM calls. `generate_report` closes the run;
when volume exceeds the vendor cap (25,000) it emits `sourcing.status = needs_choice` (a field the app
collects), rather than interrupting the graph.

**Two-layer reliability.** Gemini occasionally drops a report (a malformed
`set_model_response`, worst on vendor_clearance). Rather than a blunt whole-audit re-run:
- **Workflow layer — the `recovery` node.** The orchestrator reasons over its own
  state: a report with no `status` is a failure, so it re-runs **only** those agents
  in place (`ctx.run_node`, up to `MAX_RECOVERY` passes) and hands the healed set to
  `compile_ui`. Selective, coordinator-owned self-heal — not "always run all three".
- **Tool layer — `ReflectAndRetryToolPlugin`.** Every domain agent is served (via
  `serve_a2a`) with this plugin, so when an actual **MCP tool** call errors, the model
  reflects and retries that tool in place — shrinking how often the recovery node
  even has to fire.

**Incremental re-run (reasoned in a skill, not mapped).** The orchestrator's dispatch
decision — *which workflows to run this request* — lives in a versioned skill
(`agents/orchestrator/skills/workflow-dispatch/SKILL.md`). The `dispatch` node consults
a skill-driven `workflow_dispatcher` LlmAgent that reasons: an **initial request** runs
all workflows; a **re-run** compares the prior inputs to the new ones and runs only the
workflows a changed input affects (judged from each workflow's self-description), plus
any that were incomplete. The app threads the prior audit's reports + inputs back into
the graph via a `run_token`; the guards run the dispatched workflows and **reuse** the
rest (the UI tags reused panels *↺ Reused*). E.g. supplying a missing medium re-runs
only `brand_style`; `vendor_clearance`/`deal_pricing` replay from cache. No hardcoded
input→workflow map and no if/else in a function — the rules are in the skill and the
reasoning is done by the model. Changed **pricing terms** and a new/changed operator
**note** are dispatch inputs too: a note about a workflow's domain re-runs that workflow
so it can *address* the note (a note can never waive a rule — overrides go through the
exception process).

### 📜 Contract finalization, final report & audit history

A fully-passed audit doesn't just end with panels — the orchestrator's
**`contract_finalize`** node (after `generate_report`) makes sure it ends with an
**executed licensing contract**: it reuses the `LC-####` if onboarding already papered
one this chain, else it re-invokes **vendor_clearance** with a `FINALIZE-CONTRACT` brief
and vendor_clearance hands off to its private **legal** agent as usual. The stream then
closes with a **📜 Final Clearance Report** card (per-workflow results, the volume-cap
outcome, and the
full contract record fetched from `mcp_licensing`). Every completed run is appended to
`data/app/audit_history.jsonl` (survives rebuilds) and browsable in the console's
**Audit History** tab (`GET /api/audits`) — inputs, statuses, full reports, and the
executed contract, exportable as PDF.

### 🎨 A2UI rendering & streaming

> Full write-up: **[A2UI.md](A2UI.md)** — the flow end to end, the wire format, the SDK's role,
> the healing/validation rules, and the safety net.

Presentation is decoupled from the orchestrator. The **ui_renderer** agent (:8004, its own
A2A service) **emits the A2UI itself** — a versioned skill (`skills/render-a2ui/`) says what
to build, and the official **`a2ui-agent-sdk`** supplies the contract it must build within;
`agents/a2ui_surface.py` slots each rendered panel into the console surface and streams it,
and the official **`@a2ui/react`** renderer patches it in live. (The wire uses the
`surfaceUpdate`/`beginRendering` message names — A2UI v0.8, what the renderer speaks; the
protocol's current release renamed them to `updateComponents`/`createSurface`.) It's
**generic** — one panel per `*_report`, so adding a workflow needs no render change. If
ui_renderer is unreachable *or its A2UI fails validation*, a rule-based fallback
(`panels_fallback`) keeps the UI working.

#### How A2UI is used — three layers

A2UI ships an official client renderer AND an official Python agent SDK; the mesh uses both,
and hand-writes only what is genuinely ours (the surface scaffold and the panel layout).

```
ui_renderer (LLM, :8004)  ──A2A──►  <a2ui-json> surfaceUpdate {components} # the AGENT emits A2UI
                                          │
app.py ─► vibeflix_common/a2ui_format.py ─► heal + VALIDATE (a2ui-agent-sdk)  # spec-checked
       └► agents/a2ui_surface.py         ─► slot into card{i} + stream (SSE)  # ids namespaced
                                          │
browser ──► @a2ui/react + @a2ui/web_core ──► rendered panels                  # official RENDERER
```

- **Agent (`ui_renderer`) — emits A2UI.** Its instruction is *generated* by
  `a2ui-agent-sdk` from the spec assets: the response rules, the `<a2ui-json>` block
  contract, and the real component/message JSON schema (pruned to
  `Text`/`Card`/`Column`/`Divider`). We supply only the role + the layout procedure. No
  `output_schema`: A2UI blocks are a text format, and the model is given the schema in the
  prompt instead.
- **Server (app) — validates, does not author.** `vibeflix_common/a2ui_format.py` wraps the
  SDK: unwrap the blocks, heal damaged JSON, and validate against the spec (unknown
  components, bad `usageHint`, dangling id references all rejected → fallback).
  `agents/a2ui_surface.py` then owns only what is the app's business: the surface scaffold
  (header, pending card slots, divider, final-report slot), namespacing a panel's ids into
  its slot, and the deterministic closing/final report cards.
- **Client (frontend) — uses A2UI's library.** `@a2ui/react` + `@a2ui/web_core`
  (`A2UIProvider` / `A2UIRenderer` / `useA2UI().processMessages`) render the surfaces.

*Previously* the agent returned a small `Presentation` schema (title/status/lines) and
`a2ui_surface` built the A2UI — the concern being that a large id-referenced structured
output would trigger Gemini's `set_model_response` "malformed function call". Emitting A2UI
as *text* under the SDK's prompt sidesteps that failure mode entirely, and validation +
`panels_fallback` cover the rest: the model now decides the **layout**, not just the words.

Two paths:
- **`POST /api/audit`** — runs the graph once (the orchestrator's `recovery` node
  handles reliability now), returns the finished surface. Non-streaming.
- **`POST /api/audit/stream`** — **Server-Sent Events** carrying incremental A2UI
  messages: the plan (`⏳ pending` panels + `beginRendering`) is pushed instantly,
  then each panel is patched in place (merge-by-id) as its workflow returns — so the
  UI fills in live, in completion order. The console uses this path. `needs_input`
  ends the stream; the client re-streams with the added field. *(A panel fills on a
  valid report and re-patches if the `recovery` node re-runs that workflow — pending →
  ✅ self-heal, live.)*

The `/api/audit/resume` endpoint (`{session_id, values}`) still backs the
non-streaming collect loop.

> ADK 2.0 (pre-GA, Python ≥ 3.11) is pinned with the `[a2a]` extra; images
> install it with `--pre`. See **[deploy/docs/README.md](deploy/docs/README.md)** for the
> environment contract and **Cloud Run / Agent Engine** deployment.

---

## ☁️ Deploying to Google Cloud

Cloud rollout is phased; everything lives in **`deploy/`** (scripts + Terraform)
with the full guide in **[`deploy/docs/README.md`](deploy/docs/README.md)**.

**Phase 1 — MCP servers → Cloud Run** (done, repeatable):

```bash
# project + region are variables — set them in deploy/.env, or per-run:
PROJECT=pokedemo-test REGION=us-central1 ./deploy/deploy_mcp_cloudrun.sh
```

Builds the 3 images with Cloud Build and applies `deploy/terraform/mcp/`
(IAM-gated Cloud Run services + least-privilege runtime service accounts).
See deploy/docs/README.md § "Cloud phase 1" for prerequisites, verification, and teardown.

Next phases: agents → Agent Runtime, registry + Agent Gateway.

### Three ways to deploy an agent to Agent Runtime — and why we use the A2A template

| | `adk deploy agent_engine` (ADK CLI) | **A2A template** (`deploy/deploy_agents_a2a.py`) ✅ ours | `agents-cli deploy` (agent-starter-pack) |
|---|---|---|---|
| Delivery | agent FOLDER + generated Dockerfile → container | pickled `A2aAgent` object (SDK, source-based) | scaffolded `deploy.py` + `AdkApp` (source tarball) |
| Serves platform A2A (`/a2a/v1/*`) | ❌ container only implements the streamQuery contract — specs can advertise A2A but calls 404 (verified live) | ✅ the template registers AND implements the A2A methods | ✅ when scaffolded as an A2A agent (`is_a2a` metadata) |
| Agent identity | post-deploy v1beta1 update | ✅ at create (`identity_type` in config) | ✅ `--agent-identity` flag |
| Fits this repo | yes (folder-based) | yes (works on our monorepo layout) | needs the starter-pack project structure — one scaffolded project per agent |
| Risk profile | battle-tested packaging, broken A2A | pickle-based packaging (imports must resolve in-engine), correct A2A | Google-maintained pipeline, but a repo restructure |

The CLI path is fine for query-only engines; our orchestrator fans out over
A2A, so the template path is required. `agents-cli` is the long-term managed
equivalent if the repo is ever restructured per agent.

## 🎭 Interactive Flow Walkthrough

- **Step 1: Ingest Image / Presets**: Choose a preset scenario or type a prompt commands to start. Sourcing Orchestrator initiates parallel checks across all 3 agents (Brand Style, Vendor & Licensing, Deal Pricing).
- **Step 2: Style & Exclusivity Collision (Scenario 2)**: The Style Agent flags uncertified font family `SpaceGrotesk` for the text `THE CHILD`. The Vendor & Licensing Clearance Agent flags a North American exclusive distribution conflict with the exclusive partner vendor (Liberty Figure Works) (and marks the matching vendors ineligible). Warning overlays are drawn over the product box.
- **Step 3: Autonomous Mesh Resolution / User Remediation**: In Scenario 2, agents negotiate and resolve checks automatically. Otherwise, user manually swaps the market dropdown to **Europe**, re-running verification checks and clearing the blocks.
- **Step 4: Human-in-the-Loop Sourcing Cap Override (Scenario 3)**: In Scenario 3, procurement volume (40,000) exceeds the primary vendor limit (25,000). Sourcing freezes, presenting a choices card. The user must explicitly choose **Option A** (Split excess 15k units to secondary Addendum Contract SC-7798-EU) or **Option B** (Strictly cap volume at 25k and cancel excess) before they can finalize the release.

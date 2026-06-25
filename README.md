# Global Merchandising License Verification & IP Infringement Counterfeit Audit

A modern, multi-agent workspace utilizing Google **ADK 2.0** for agent orchestration, **A2UI (Agent-to-User Interface)** for visual component painting, and independent, domain-grouped **Model Context Protocol (MCP)** servers to verify IP licensing and audit physical product prototypes in real time.

---

## 🏗️ Architecture Design

The workspace decouples analytical logic from rendering layers to ensure clean design:

1. **Vite React Frontend**: A conversational adaptive canvas workspace styling system where users drop image prototypes or send instructions. Emits user action telemetry. Renders complex, interactive layout forms and parallel execution graphs.
2. **ADK 2.0 Python Agents**: A mesh of independent Python agents:
   - **Sourcing Orchestrator (Router)**: Captures uploads, checks parameters, coordinates state, and invokes display layouts.
   - **Brand Style Compliance Agent (Designer)**: Analyzes logo, fonts, hex swatches, and typographical compliance.
   - **Global Market Clearance & IP Counsel Agent (Counsel)**: Verifies region contracts, exclusivity collisions (e.g. Hasbro), and customs trademark registrations.
   - **Franchise Storyline & Lore Agent (Lore)**: Checks script databases, lore canon compliance, and screens for script leak/spoiler threats.
3. **Decoupled MCP Servers**: Structured as 3 independent, containerizable domain servers:
   - `mcp_vision_ui`: Vision Analyzer & UI Rendering tools.
   - `mcp_legal`: IP style rules registry, Exclusivity contracts, Customs trademark checkers.
   - `mcp_market`: Global e-commerce scraper intelligence, Ledger capacity checkers, Governance telemetry logging.

---

## 📂 Project Structure

```
vibeflix/
├── frontend/                   # React app (A2UI renderer & sandbox dashboard)
├── agents/                     # Independent Python agents (ADK 2.0 + FastAPI Server)
│   ├── app.py                  # FastAPI proxy backend
│   ├── orchestrator/           # Sourcing Orchestrator folder (agent.py)
│   ├── brand_style/            # Brand Style Compliance Agent folder (agent.py)
│   ├── ip_counsel/             # Global Market Clearance Agent folder (agent.py)
│   └── storyline/              # Franchise Storyline & Lore Agent folder (agent.py)
└── mcp_servers/                # Decoupled MCP servers grouped by function
    ├── mcp_vision_ui/          # Vision analyzer & UI renderer
    ├── mcp_legal/              # IP guidelines, exclusivity contracts, customs registry
    └── mcp_market/             # Scrapers, ledger limits, governance logs
```

---

## 🚀 Running Locally

### 1. Frontend (React UI)

Enter the frontend directory, install dependencies, and spin up Vite:

```bash
cd frontend
npm install
npm run dev
```

The UI sandbox will be active at [http://localhost:3000](http://localhost:3000).

### 2. Multi-Agent Backend (Python/FastAPI + ADK 2.0)

The agents are built on the **ADK 2.0 graph Workflow API**, which is pre-GA, so
dependencies must be installed with prereleases allowed. ADK 2.0 requires
**Python ≥ 3.11**. Set up a virtual environment, install requirements, and run
the server **from the repository root** (the backend uses absolute `agents.*`
package imports):

```bash
python3 -m venv venv
source venv/bin/activate
uv pip install --prerelease=allow -r agents/requirements.txt || pip install --pre -r agents/requirements.txt
python -m agents.app
```

Runs on port `8000`. Gemini-backed agents need credentials — set
`GOOGLE_API_KEY` (AI Studio) or `GOOGLE_GENAI_USE_VERTEXAI=1` with
`GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` (Vertex AI) in the environment.

**Workflow graph:** `START → ingest → (brand_style ‖ ip_counsel ‖ storyline) →
merge → compile_ui → sourcing_gate (HITL) → finalize`. Each domain agent is an
`LlmAgent` that calls its MCP server(s) as tools. When production volume exceeds
the vendor cap (25,000), `sourcing_gate` interrupts; resolve it via
`POST /api/audit/resume` with `{"session_id": ..., "choice": "A"|"B"}`.

### 3. MCP Servers

Each group can be executed or run independently via FastMCP or Python:

```bash
cd ../mcp_servers/mcp_vision_ui
python3 -m venv venv && source venv/bin/activate
uv pip install -r requirements.txt || pip install -r requirements.txt
python server.py
```

---

## 🎭 Interactive Flow Walkthrough

- **Step 1: Ingest Image / Presets**: Choose a preset scenario or type a prompt commands to start. Sourcing Orchestrator initiates parallel checks across all 3 agents (Style, Legal, Storyline).
- **Step 2: Style & Exclusivity Collision (Scenario 2)**: The Style Agent flags uncertified font family `SpaceGrotesk` for the text `THE CHILD`. The IP Counsel Agent flags a North American exclusive distribution conflict with Hasbro. Warning overlays are drawn over the product box.
- **Step 3: Autonomous Mesh Resolution / User Remediation**: In Scenario 2, agents negotiate and resolve checks automatically. Otherwise, user manually swaps the market dropdown to **Europe**, re-running verification checks and clearing the blocks.
- **Step 4: Human-in-the-Loop Sourcing Cap Override (Scenario 3)**: In Scenario 3, procurement volume (40,000) exceeds the primary vendor limit (25,000). Sourcing freezes, presenting a choices card. The user must explicitly choose **Option A** (Split excess 15k units to secondary Addendum Contract SC-7798-EU) or **Option B** (Strictly cap volume at 25k and cancel excess) before they can finalize the release.

#!/usr/bin/env bash
#
# run_local.sh — drive the Vibeflix audit mesh locally via docker compose.
#
# The system is distributed-only: the orchestrator calls the three agents over
# A2A, and the agents call the MCP servers over HTTP. There is no single-process
# mode — use docker compose to bring up all 7 services.
#
# Usage:
#   ./run_local.sh up                Build + start all 7 services (app on :8000)
#   ./run_local.sh down              Stop and remove the services
#   ./run_local.sh logs              Tail logs from all services
#   ./run_local.sh smoke             Start, wait for health, POST /api/audit, print result
#   ./run_local.sh frontend          Run the Vite dev server against a running app (:8000)
#
#   --- local (no Docker) ---
#   ./run_local.sh console           The whole product from .venv: MCP + agents +
#                                    orchestrator + the console app on :8000.
#                                    Same as `up`, without the seven image builds.
#   ./run_local.sh mcp               Start all 4 MCP servers locally (Ctrl-C stops all)
#   ./run_local.sh mesh              Start the full backend (4 MCP + 3 A2A agents) for
#                                    testing the orchestrator, e.g. via `adk web`
#   ./run_local.sh test-agent NAME   Run one agent in isolation against the local MCP servers
#                                    NAME = brand_style | vendor_clearance | deal_pricing
#
# Prereqs: Docker (mesh), or .venv (local mcp/test-agent). Agents call Vertex,
# so run `gcloud auth application-default login` first.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

API_BASE="${API_BASE:-http://localhost:8000}"
VENV="$ROOT/.venv"
# group -> local streamable-http port
MCP_PORTS=("mcp_licensing:9002" "mcp_market:9003" "mcp_brand_style:9004")

c_info() { printf "\033[1;36m[run_local]\033[0m %s\n" "$*"; }
c_warn() { printf "\033[1;33m[run_local]\033[0m %s\n" "$*"; }
c_err()  { printf "\033[1;31m[run_local]\033[0m %s\n" "$*" >&2; }

compose() {
  if docker compose version >/dev/null 2>&1; then docker compose "$@";
  elif command -v docker-compose >/dev/null 2>&1; then docker-compose "$@";
  else c_err "docker compose not found. Install Docker Desktop / the compose plugin."; exit 1; fi
}

check_adc() {
  if [ ! -f "${HOME}/.config/gcloud/application_default_credentials.json" ]; then
    c_warn "No Application Default Credentials found — agents' Vertex calls will fail."
    c_warn "Run: gcloud auth application-default login"
  fi
}

ensure_venv() {
  if [ ! -x "$VENV/bin/python" ]; then
    c_err "No .venv found. Create it and install backend deps, e.g.:"
    c_err "  uv venv .venv && uv pip install --python .venv/bin/python --prerelease=allow -r agents/requirements.txt"
    exit 1
  fi
  # Install/refresh the shared package (non-editable — py3.14+uv .pth editable is
  # unreliable). Cheap no-op when unchanged.
  uv pip install --python "$VENV/bin/python" "$ROOT/packages/vibeflix-common" --no-deps >/dev/null 2>&1 || true
}

start_mcp_servers() {
  ensure_venv
  MCP_PIDS=()
  for entry in "${MCP_PORTS[@]}"; do
    group="${entry%%:*}"; port="${entry##*:}"
    c_info "Starting $group on http://127.0.0.1:$port/mcp  (log: /tmp/$group.log)"
    MCP_TRANSPORT=streamable-http HOST=127.0.0.1 PORT="$port" \
      "$VENV/bin/python" "mcp_servers/$group/server.py" >"/tmp/$group.log" 2>&1 &
    MCP_PIDS+=("$!")
  done
}

# Local A2A agent services (brand_style:8001, vendor_clearance:8002, deal_pricing:8003,
# ui_renderer:8004, legal:8005). Each gets only the MCP URLs it uses; Vertex config comes from
# the agent's .env (ui_renderer needs Vertex for its Gemini call, no MCP).
start_a2a_agents() {
  ensure_venv
  A2A_PIDS=()
  A2A_AGENT=brand_style A2A_HOST=127.0.0.1 A2A_PROTOCOL=http PORT=8001 \
    MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp \
    "$VENV/bin/python" -m vibeflix_common.a2a.serve >/tmp/a2a_brand_style.log 2>&1 &
  A2A_PIDS+=("$!")
  A2A_AGENT=vendor_clearance A2A_HOST=127.0.0.1 A2A_PROTOCOL=http PORT=8002 \
    MCP_LICENSING_URL=http://127.0.0.1:9002/mcp MCP_MARKET_URL=http://127.0.0.1:9003/mcp \
    LEGAL_A2A_URL=http://127.0.0.1:8005 \
    "$VENV/bin/python" -m vibeflix_common.a2a.serve >/tmp/a2a_vendor_clearance.log 2>&1 &
  A2A_PIDS+=("$!")
  A2A_AGENT=deal_pricing A2A_HOST=127.0.0.1 A2A_PROTOCOL=http PORT=8003 MCP_LICENSING_URL=http://127.0.0.1:9002/mcp \
    "$VENV/bin/python" -m vibeflix_common.a2a.serve >/tmp/a2a_deal_pricing.log 2>&1 &
  A2A_PIDS+=("$!")
  A2A_AGENT=ui_renderer A2A_HOST=127.0.0.1 A2A_PROTOCOL=http PORT=8004 \
    "$VENV/bin/python" -m vibeflix_common.a2a.serve >/tmp/a2a_ui_renderer.log 2>&1 &
  A2A_PIDS+=("$!")
  # Legal Clearance agent — independent + private to vendor_clearance.
  A2A_AGENT=legal A2A_HOST=127.0.0.1 A2A_PROTOCOL=http PORT=8005 \
    MCP_LICENSING_URL=http://127.0.0.1:9002/mcp \
    "$VENV/bin/python" -m vibeflix_common.a2a.serve >/tmp/a2a_legal.log 2>&1 &
  A2A_PIDS+=("$!")
  # Report each agent as it comes up. This loop used to wait silently, so a mesh with a DEAD
  # agent looked identical to a healthy one — you only found out when a call to it failed.
  for entry in "brand_style:8001" "vendor_clearance:8002" "deal_pricing:8003" \
               "ui_renderer:8004" "legal:8005"; do
    name="${entry%%:*}"; port="${entry##*:}"; ready=""
    for _ in $(seq 1 40); do
      curl -sf "http://127.0.0.1:$port/.well-known/agent-card.json" >/dev/null 2>&1 && { ready=1; break; }
      sleep 0.5
    done
    if [ -n "$ready" ]; then c_info "  ✓ $name  → http://127.0.0.1:$port"
    else c_warn "  ✗ $name did NOT start on :$port (see /tmp/a2a_$name.log)"; fi
  done
}

# The orchestrator, as an A2A service like the rest of the mesh. `mesh` leaves it
# out because you usually drive it from `adk web`; the console needs it running.
start_orchestrator() {
  A2A_AGENT=orchestrator A2A_HOST=127.0.0.1 A2A_PROTOCOL=http PORT=8006 \
    BRAND_STYLE_A2A_URL=http://127.0.0.1:8001 \
    VENDOR_CLEARANCE_A2A_URL=http://127.0.0.1:8002 \
    DEAL_PRICING_A2A_URL=http://127.0.0.1:8003 \
    MCP_LICENSING_URL=http://127.0.0.1:9002/mcp \
    "$VENV/bin/python" -m vibeflix_common.a2a.serve >/tmp/a2a_orchestrator.log 2>&1 &
  ORCH_PID="$!"
  for _ in $(seq 1 40); do
    curl -sf "http://127.0.0.1:8006/.well-known/agent-card.json" >/dev/null 2>&1 && {
      c_info "  ✓ orchestrator  → http://127.0.0.1:8006"; return; }
    sleep 0.5
  done
  c_warn "  ✗ orchestrator did NOT start on :8006 (see /tmp/a2a_orchestrator.log)"
}

# The console: FastAPI + the built frontend, as a thin client over the local mesh.
# Same wiring as the `app` service in docker-compose.yml, pointed at 127.0.0.1.
start_app() {
  if [ ! -d "$ROOT/frontend/dist" ]; then
    c_warn "frontend/dist missing — building it once (npm run build)…"
    (cd "$ROOT/frontend" && npm ci --silent && npm run build)
  fi
  PORT=8000 \
    ORCHESTRATOR_A2A_URL=http://127.0.0.1:8006 \
    BRAND_STYLE_A2A_URL=http://127.0.0.1:8001 \
    VENDOR_CLEARANCE_A2A_URL=http://127.0.0.1:8002 \
    DEAL_PRICING_A2A_URL=http://127.0.0.1:8003 \
    UI_RENDERER_A2A_URL=http://127.0.0.1:8004 \
    MCP_LICENSING_URL=http://127.0.0.1:9002/mcp \
    MCP_MARKET_URL=http://127.0.0.1:9003/mcp \
    MCP_BRAND_STYLE_URL=http://127.0.0.1:9004/mcp \
    FRONTEND_DIST="$ROOT/frontend/dist" \
    AUDIT_HISTORY_DIR="$ROOT/data/app" \
    "$VENV/bin/python" -m uvicorn agents.app:app --host 127.0.0.1 --port 8000 \
    >/tmp/app.log 2>&1 &
  APP_PID="$!"
  for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:8000/api/ready" >/dev/null 2>&1 && {
      c_info "  ✓ console       → http://127.0.0.1:8000"; return; }
    sleep 0.5
  done
  c_warn "  ✗ console did NOT start on :8000 (see /tmp/app.log)"
}


case "${1:-up}" in
  up)
    check_adc
    c_info "Building and starting all 7 services (app → $API_BASE)…"
    compose up --build
    ;;
  down)
    compose down
    ;;
  logs)
    compose logs -f --tail=80
    ;;
  smoke)
    check_adc
    c_info "Starting services in the background…"
    compose up --build -d
    c_info "Waiting for $API_BASE/api/health …"
    ok=""
    for _ in $(seq 1 60); do
      if curl -sf "$API_BASE/api/health" >/dev/null 2>&1; then ok=1; break; fi
      sleep 1
    done
    [ -n "$ok" ] || { c_err "app did not become healthy"; compose logs --tail=40 app; exit 1; }
    c_info "POST /api/audit (North America / 15000 — expect Hasbro exclusivity block) →"
    curl -s -X POST "$API_BASE/api/audit" \
      -H 'Content-Type: application/json' \
      -d '{"image_path":"grogu_mockup_box.png","target_market":"North America","volume":15000}' \
      | (python3 -m json.tool 2>/dev/null || cat)
    echo
    c_info "Services still running. Stop with: ./run_local.sh down"
    ;;
  frontend)
    c_info "Vite dev server (proxying API to $API_BASE)…"
    VITE_API_URL="$API_BASE" npm run dev --prefix "$ROOT/frontend"
    ;;
  console)
    # The whole product, WITHOUT Docker: the mesh you already know, plus the
    # orchestrator and the console app. `up` does the same thing in containers,
    # but pays for seven image builds first — this reuses .venv and starts in
    # seconds. Same processes, same ports the lab has used all along.
    check_adc
    start_mcp_servers
    start_a2a_agents
    start_orchestrator
    start_app
    trap 'c_info "Stopping console…"; kill "${MCP_PIDS[@]}" "${A2A_PIDS[@]}" "$ORCH_PID" "$APP_PID" 2>/dev/null || true' EXIT INT TERM
    c_info "Console up on http://127.0.0.1:8000 — open it via Web Preview (port 8000)."
    c_info "Ctrl-C to stop everything."
    wait
    ;;
  mesh)
    # Full backend (3 MCP + 5 A2A agent services) for testing the orchestrator
    # locally without Docker — e.g. via `adk web agents/orchestrator`.
    check_adc
    start_mcp_servers
    start_a2a_agents
    trap 'c_info "Stopping mesh…"; kill "${MCP_PIDS[@]}" "${A2A_PIDS[@]}" 2>/dev/null || true' EXIT INT TERM
    c_info "Mesh up: MCP :9002-:9004, agents :8001-:8005 (legal is :8005 — vendor_clearance calls it there)."
    c_info "Test the orchestrator in another shell:"
    c_info "  export BRAND_STYLE_A2A_URL=http://127.0.0.1:8001 \\"
    c_info "         VENDOR_CLEARANCE_A2A_URL=http://127.0.0.1:8002 \\"
    c_info "         DEAL_PRICING_A2A_URL=http://127.0.0.1:8003"
    c_info "  adk web agents/orchestrator      # then open http://127.0.0.1:8000"
    c_info "Ctrl-C to stop the mesh."
    wait
    ;;
  mcp)
    start_mcp_servers
    trap 'c_info "Stopping MCP servers…"; kill "${MCP_PIDS[@]}" 2>/dev/null || true' EXIT INT TERM
    c_info "All MCP servers running. Test an agent against them in another shell:"
    c_info "  ./run_local.sh test-agent vendor_clearance --market 'North America'"
    c_info "Ctrl-C to stop."
    wait
    ;;
  test-agent)
    ensure_venv
    check_adc
    shift
    [ "$#" -ge 1 ] || { c_err "Usage: ./run_local.sh test-agent <brand_style|vendor_clearance|deal_pricing> [--market M] [--volume N] [--image F]"; exit 1; }
    "$VENV/bin/python" -m agents.test_agent "$@"
    ;;
  *)
    c_err "Unknown command: $1"; sed -n '9,21p' "$0"; exit 1 ;;
esac

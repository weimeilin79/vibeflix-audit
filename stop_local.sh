#!/usr/bin/env bash
#
# stop_local.sh — stop everything ./run_local.sh may have started, then verify the ports are free.
#
#     ./stop_local.sh
#
# Why this exists: run_local.sh kills its children from an EXIT trap, but a run that dies while
# starting up (or a tab closed with the window) leaves orphans behind — and an orphaned uvicorn
# that never finished booting holds nothing in `ss` yet still fights the next run for :8000. Two
# app processes then coexist and NEITHER ends up listening, which looks like "the console won't
# start" rather than "something is already running".
#
# So this kills by PATTERN first (catches processes that never got as far as binding) and only
# then sweeps the ports. Safe to run when nothing is up: it just reports a clean slate.
set -uo pipefail

c_info() { printf "\033[1;36m[stop_local]\033[0m %s\n" "$*"; }
c_warn() { printf "\033[1;33m[stop_local]\033[0m %s\n" "$*"; }

# Command-line patterns for everything run_local.sh starts. Specific enough not to match an
# editor, a shell, or this script.
PATTERNS=(
  "uvicorn agents.app:app"                 # the console app
  "vibeflix_common.a2a.serve"              # the six A2A agent services
  "mcp_servers/.*/server.py"               # the three MCP servers
)
PORTS=(8000 8001 8002 8003 8004 8005 8006 9002 9003 9004)

# pids_on_port <port> — lsof where available (macOS + most Linux), else ss.
pids_on_port() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:$1" 2>/dev/null
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnpH "sport = :$1" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p'
  fi
}

found=0

# 1) by pattern — catches half-started processes that hold no port yet.
for pat in "${PATTERNS[@]}"; do
  pids=$(pgrep -f "$pat" 2>/dev/null || true)
  for pid in $pids; do
    [ "$pid" = "$$" ] && continue
    c_info "stopping pid $pid  ($pat)"
    kill "$pid" 2>/dev/null && found=$((found + 1))
  done
done

# 2) give them a moment to exit cleanly, then insist.
if [ "$found" -gt 0 ]; then
  sleep 2
  for pat in "${PATTERNS[@]}"; do
    for pid in $(pgrep -f "$pat" 2>/dev/null || true); do
      [ "$pid" = "$$" ] && continue
      c_warn "pid $pid ignored SIGTERM — sending SIGKILL"
      kill -9 "$pid" 2>/dev/null || true
    done
  done
fi

# 3) sweep anything still holding a port we need (e.g. an `adk web` left running on :8000).
for port in "${PORTS[@]}"; do
  for pid in $(pids_on_port "$port"); do
    [ "$pid" = "$$" ] && continue
    c_warn "port $port still held by pid $pid — stopping it"
    kill -9 "$pid" 2>/dev/null || true
    found=$((found + 1))
  done
done

# 4) report the result rather than assuming it worked.
sleep 1
busy=""
for port in "${PORTS[@]}"; do
  [ -n "$(pids_on_port "$port")" ] && busy="$busy $port"
done
if [ -n "$busy" ]; then
  c_warn "still in use:$busy — something outside this project is holding them"
  exit 1
fi
[ "$found" -gt 0 ] && c_info "stopped $found process(es); ports 8000-8006 + 9002-9004 are free." \
                   || c_info "nothing was running; ports 8000-8006 + 9002-9004 are free."
exit 0

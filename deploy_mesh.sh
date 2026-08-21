#!/usr/bin/env bash
#
# deploy_mesh.sh — build the entire Vibeflix mesh, init.sh through the gateway, in one command.
#
#     ./deploy_mesh.sh                  # everything, on a fresh project
#     ./deploy_mesh.sh --from legal     # resume from a phase (see --list)
#     ./deploy_mesh.sh --only app       # run exactly one phase
#     ./deploy_mesh.sh --list           # what the phases are
#     ./deploy_mesh.sh --skip-gateway   # stop after the app (Steps 1-6)
#     ./deploy_mesh.sh --no-verify      # skip the verify/step*.sh checkpoints (not advised)
#
# This is the workshop lab (workshop/lab.en.md) with the prose removed — same scripts, same
# order. The lab remains the source of truth for WHY; this file exists so a second service can
# stand the mesh up unattended, without re-deriving the order by trial and error.
#
# ─── The ordering rules encoded here, and what breaks without them ──────────────────────────
#
# 1. collect_agent_identities.py runs after EVERY deploy, not once at the end.
#    Each agent's env is baked at deploy time from the addresses of the agents it calls, which
#    are only knowable after those agents exist. Deploy vendor_clearance before collecting
#    legal's identity and LEGAL_A2A_URL is unset at build time — the handoff node is then a
#    no-op in a deployed engine you cannot inspect. deploy_agents_a2a.py now exits 1 rather
#    than skipping silently, but the fix is to collect, not to retry.
#
# 2. setup_legal_rag.sh runs BEFORE legal deploys.
#    It writes RAG_CORPUS into deploy/.env, and legal's engine env is baked from that file.
#    Reverse the two and legal deploys with no corpus: it answers every question from the
#    keyword fallback, plausibly and wrongly, and only verify/step4.sh notices.
#
# 3. setup_app_iam.sh runs BEFORE deploy_app.sh.
#    deploy_app.sh runs the service AS that SA. If it does not exist yet the deploy fails; if
#    it exists but is missing run.invoker on the MCP servers, the console draws three red boxes
#    and says nothing.
#
# 4. The gateway phase REDEPLOYS all six engines.
#    Attaching an engine to the gateway is part of its deployment config, so setup_gateway.sh
#    alone changes nothing about engines that already exist. The redeploy is the attach.
#
# 5. Verify runs with retries, not once.
#    IAM is eventually consistent — a grant made seconds ago routinely reads back as absent for
#    a minute or more. A single verify pass right after a grant produces a failure that is
#    indistinguishable from a real misconfiguration, and sends you chasing a bug that fixed
#    itself while you looked. Each checkpoint retries before it believes a negative.
#
# Every phase is idempotent: re-running is the normal way to recover from a failure.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"

PHASES=(init foundations brand pricing legal orchestrator app gateway)
DESC_init="init.sh — CLI checks, venv + pinned deps, terraform, deploy/.env"
DESC_foundations="Firestore + buckets + Pub/Sub + the 3 MCP servers + agent registry"
DESC_brand="brand_style: deploy, collect, grant"
DESC_pricing="deal_pricing: deploy, collect, grant"
DESC_legal="legal RAG corpus, then legal + vendor_clearance (collect between them)"
DESC_orchestrator="orchestrator: deploy, collect, grant"
DESC_app="ui_renderer, app IAM, app deploy"
DESC_gateway="registry + gateway + egress policy, then redeploy all six to attach"

SKIP_GATEWAY=0; VERIFY=1; FROM=""; ONLY=""; RESUME=0
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="${2:?--from needs a phase}"; shift 2 ;;
    --only) ONLY="${2:?--only needs a phase}"; shift 2 ;;
    --skip-gateway) SKIP_GATEWAY=1; shift ;;
    --resume) RESUME=1; shift ;;
    --no-verify) VERIFY=0; shift ;;
    --list)
      echo "phases, in order:"
      for p in "${PHASES[@]}"; do d="DESC_$p"; printf "  %-14s %s\n" "$p" "${!d}"; done
      exit 0 ;;
    -h|--help) sed -n '3,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1  (try --help)" >&2; exit 2 ;;
  esac
done

# The project we were ASKED to build into, captured before anything sources deploy/.env —
# which exports PROJECT and would otherwise overwrite the answer we are trying to check.
INTENDED_PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"

c_step() { printf "\n\033[1;36m━━━ %s\033[0m  %s\n" "$1" "${2:-}"; }
c_ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
c_warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }
c_die()  { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

# ── logging ────────────────────────────────────────────────────────────────────────────────
# One log FILE per phase, not one wall of text. A backgrounded run (nohup) is otherwise close
# to undebuggable: the failure is thousands of lines up, interleaved with five other things,
# and you cannot tell which phase it belonged to. Here each phase writes its own small file,
# and a failure reprints the tail of that file at the very END of the output — where you look
# first when you reconnect and find the job stopped.
LOG_DIR="$ROOT/logs"; mkdir -p "$LOG_DIR"
STATE_FILE="$ROOT/.mesh_state"
PHASE_NAME="startup"; PHASE_LOG="$LOG_DIR/00-startup.log"; PHASE_START=$SECONDS
: > "$PHASE_LOG"

start_phase() {   # start_phase <nn> <name> <description>
  PHASE_NAME="$2"; PHASE_LOG="$LOG_DIR/$1-$2.log"; PHASE_START=$SECONDS
  : > "$PHASE_LOG"
  c_step "$2" "$3"
  printf "    log: %s\n" "${PHASE_LOG#$ROOT/}"
}

fail_phase() {    # fail_phase <what failed> <exit code>
  printf "\n\033[1;31m✗ phase '%s' FAILED\033[0m — %s (exit %s)\n" "$PHASE_NAME" "$1" "$2" >&2
  printf "\n── last 40 lines of %s ──\n" "${PHASE_LOG#$ROOT/}" >&2
  tail -40 "$PHASE_LOG" >&2
  printf -- "──\n\n" >&2
  printf "full log : %s\n" "$PHASE_LOG" >&2
  printf "resume   : ./deploy_mesh.sh --from %s\n" "$PHASE_NAME" >&2
  exit 1
}

run() {           # run <command…> — stream to the console AND the phase log; die with context
  set +e
  "$@" 2>&1 | tee -a "$PHASE_LOG"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -eq 0 ] || fail_phase "$*" "$rc"
}

end_phase() {
  echo "$PHASE_NAME" > "$STATE_FILE"
  local d=$((SECONDS - PHASE_START))
  c_ok "$PHASE_NAME complete in $((d / 60))m$((d % 60))s"
}

valid() { local p; for p in "${PHASES[@]}"; do [ "$p" = "$1" ] && return 0; done; return 1; }
# --resume: pick up at the phase AFTER the last one that completed. Re-running the completed
# phase would also be safe (they are all idempotent), just slower.
if [ "$RESUME" = 1 ]; then
  [ -s "$STATE_FILE" ] || c_die "nothing to resume — no $STATE_FILE from a previous run."
  _last="$(cat "$STATE_FILE")"
  for _i in "${!PHASES[@]}"; do
    [ "${PHASES[$_i]}" = "$_last" ] && FROM="${PHASES[$((_i + 1))]:-}"
  done
  [ -n "$FROM" ] && echo "resuming after '$_last' → starting at '$FROM'" \
                 || { c_ok "all phases already completed (last: $_last)"; exit 0; }
fi
[ -n "$FROM" ] && { valid "$FROM" || c_die "no such phase '$FROM' — see --list"; }
[ -n "$ONLY" ] && { valid "$ONLY" || c_die "no such phase '$ONLY' — see --list"; }

# want <phase> — is this phase in scope for this run?
STARTED=0
want() {
  [ -n "$ONLY" ] && { [ "$ONLY" = "$1" ]; return; }
  [ -z "$FROM" ] && return 0
  [ "$STARTED" = 1 ] && return 0
  [ "$FROM" = "$1" ] && { STARTED=1; return 0; }
  return 1
}

# reload_env — source env.sh into THIS shell. Anything that writes deploy/.env (init.sh,
# setup_legal_rag.sh) is invisible to the rest of the run until we re-read it, and a stale
# RAG_CORPUS/PROJECT here is baked into the next engine we deploy.
reload_env() {
  # shellcheck disable=SC1091
  . ./env.sh >/dev/null || c_die "env.sh failed — run ./init.sh by hand and read its output"
}

assert_project() {
  # ── deploying into the WRONG project is silent, so check it explicitly ─────────────────────
  # init.sh deliberately does not clobber an existing deploy/.env. That is right for a re-run and
  # wrong for a re-USE: point an old clone at a new project and every script here still reads the
  # OLD project from .env, builds the mesh there, and reports success. Nothing errors, because
  # nothing is broken — it is just the wrong account.
  if [ -n "$INTENDED_PROJECT" ] && [ "$INTENDED_PROJECT" != "$PROJECT" ]; then
    c_die "project mismatch — refusing to guess.
     you asked for : $INTENDED_PROJECT   (gcloud config / \$PROJECT)
     deploy/.env says: $PROJECT
     For a NEW project, regenerate the config from scratch:
         rm deploy/.env deploy/agent_identities.json
         rm -rf deploy/terraform/*/.terraform deploy/terraform/*/terraform.tfstate*
         PROJECT=$INTENDED_PROJECT ./deploy_mesh.sh
     To keep building the existing one, unset PROJECT and set gcloud to $PROJECT."
  fi

  # The address book is per-project too: every engine id in it belongs to the project it was
  # collected from. Left in place, the first deploy bakes ANOTHER project's engine URLs into the
  # new agents' env — they deploy clean and then call across projects at runtime, where it shows
  # up as a 403 that looks like a permissions bug in the project you are standing in.
  IDS="deploy/agent_identities.json"
  if [ -s "$IDS" ] && ! grep -q "/$PROJECT/\|/${PROJECT_NUMBER:-__none__}/" "$IDS" 2>/dev/null; then
    c_die "$IDS holds identities from a DIFFERENT project.
     Delete it and let this run rebuild it:   rm $IDS"
  fi
}

# verify <script> [attempts] — a verify checkpoint that tolerates IAM propagation (rule 5).
verify() {
  [ "$VERIFY" = 1 ] || { c_warn "skipping $1 (--no-verify)"; return 0; }
  local script="deploy/verify/$1" attempts="${2:-3}" n=1
  [ -x "$script" ] || { c_warn "$script not found — skipping"; return 0; }
  while :; do
    set +e; "$script" 2>&1 | tee -a "$PHASE_LOG"; local rc=${PIPESTATUS[0]}; set -e
    if [ "$rc" -eq 0 ]; then c_ok "$1 passed"; return 0; fi
    [ "$n" -ge "$attempts" ] && c_die "$1 failed after $n attempts — read the ✗ lines above.
   Fix the cause, then resume with:  ./deploy_mesh.sh --from <phase>"
    c_warn "$1 failed (attempt $n/$attempts) — IAM may still be propagating; retrying in 45s"
    sleep 45; n=$((n + 1))
  done
}

# deploy_agent <dir> <hyphen-name> — deploy, collect, grant. The collect is INSIDE this function
# precisely so it cannot be forgotten (rule 1).
deploy_agent() {
  local dir="$1" name="$2"
  run python deploy/deploy_agents_a2a.py "$dir"
  run python deploy/collect_agent_identities.py
  run ./deploy/grant_agent_access.sh "$name"
}

START_TS=$SECONDS

# ── init ───────────────────────────────────────────────────────────────────────────────────
if want init; then
  start_phase 01 init "$DESC_init"
  # init.sh PROMPTS for a project id if it cannot resolve one. That would hang an unattended
  # run forever, so establish it here instead and fail fast with an instruction.
  if [ -z "${PROJECT:-}" ] && [ -z "$(gcloud config get-value project 2>/dev/null | grep -v '^(unset)$')" ]; then
    c_die "no project set. Run:  gcloud config set project <your-project-id>
   (or:  PROJECT=<your-project-id> ./deploy_mesh.sh )"
  fi
  run ./init.sh
  reload_env
  assert_project    # before anything below spends a call on the wrong project

  # ── brand-new project: the two things that are true only the first time ──────────────────
  #
  # BILLING. Without it `gcloud services enable run.googleapis.com` fails with a quota/permission
  # error that names neither billing nor the project, and every later phase fails downstream of
  # it. Checking costs one call and turns a 20-minute confusion into one line. The check itself
  # needs permission we may not have, so an UNREADABLE answer is a warning; only a definite
  # "false" is fatal.
  BILLED="$(gcloud billing projects describe "${PROJECT:-$(gcloud config get-value project)}" \
              --format='value(billingEnabled)' 2>/dev/null || true)"
  case "$BILLED" in
    True|true) c_ok "billing is enabled" ;;
    False|false) c_die "project ${PROJECT} has NO billing account linked.
   Link one in the console (Billing → Link a billing account), then re-run.
   Everything past this point needs it: Cloud Run, Cloud Build, Vertex AI." ;;
    *) c_warn "could not read billing status (needs roles/billing.viewer) — continuing.
   If the next phase fails while enabling APIs, an unlinked billing account is the first thing
   to check." ;;
  esac

  # SERVICE AGENTS. Enabling an API does not create the service agent that API acts as; that
  # happens lazily on first use. Any grant made to one before it exists fails with "Service
  # account does not exist", and the scripts that make those grants are (correctly) tolerant of
  # failure — so on a fresh project they warn and continue, and the missing permission surfaces
  # much later as a 403 inside an agent report. Force them into existence up front.
  # Idempotent: on an existing project each call is a no-op that returns the same address.
  for API in aiplatform.googleapis.com cloudbuild.googleapis.com run.googleapis.com; do
    gcloud services enable "$API" --project="$PROJECT" >/dev/null 2>&1 || true
    gcloud beta services identity create --service="$API" --project="$PROJECT" >/dev/null 2>&1 || true
  done
  c_ok "service agents materialised (Vertex AI, Cloud Build, Cloud Run)"
fi
reload_env
: "${PROJECT:?deploy/.env has no PROJECT — run ./init.sh}"
assert_project

c_ok "project=$PROJECT region=${REGION:-us-central1}"

# ── foundations ────────────────────────────────────────────────────────────────────────────
if want foundations; then
  start_phase 02 foundations "$DESC_foundations"
  run ./workshop/setup.sh
  reload_env
  verify step1.sh
  end_phase
fi

# ── brand_style ────────────────────────────────────────────────────────────────────────────
if want brand; then
  start_phase 03 brand "$DESC_brand"
  deploy_agent brand_style brand-style
  verify step2.sh
  end_phase
fi

# ── deal_pricing ───────────────────────────────────────────────────────────────────────────
if want pricing; then
  start_phase 04 pricing "$DESC_pricing"
  deploy_agent deal_pricing deal-pricing
  verify step3.sh
  end_phase
fi

# ── legal + vendor_clearance ───────────────────────────────────────────────────────────────
if want legal; then
  start_phase 05 legal "$DESC_legal"
  # Corpus FIRST (rule 2) — it writes RAG_CORPUS into deploy/.env, which legal's engine env is
  # baked from. Then re-read .env before deploying anything.
  run ./deploy/setup_legal_rag.sh
  reload_env
  [ -n "${RAG_CORPUS:-}" ] || c_die "setup_legal_rag.sh did not write RAG_CORPUS to deploy/.env.
   Deploying legal now would ship an agent that silently answers from the keyword fallback."
  c_ok "RAG_CORPUS=${RAG_CORPUS##*/}"

  deploy_agent legal legal
  # vendor_clearance's env needs LEGAL_A2A_URL, which deploy_agent's collect just wrote.
  deploy_agent vendor_clearance vendor-clearance
  verify step4.sh
  end_phase
fi

# ── orchestrator ───────────────────────────────────────────────────────────────────────────
if want orchestrator; then
  start_phase 06 orchestrator "$DESC_orchestrator"
  deploy_agent orchestrator orchestrator
  verify step5.sh
  end_phase
fi

# ── ui_renderer + the app ──────────────────────────────────────────────────────────────────
if want app; then
  start_phase 07 app "$DESC_app"
  deploy_agent ui_renderer ui-renderer
  # App IAM before the app itself (rule 3) — deploy_app.sh runs the service as this SA, and this
  # is where the app gets run.invoker on the three MCP servers.
  run ./deploy/setup_app_iam.sh
  run ./deploy/deploy_app.sh
  verify step6.sh
  end_phase
fi

# ── gateway ────────────────────────────────────────────────────────────────────────────────
if want gateway && [ "$SKIP_GATEWAY" = 0 ]; then
  start_phase 08 gateway "$DESC_gateway"
  run ./deploy/setup_gateway.sh
  # The attach IS a redeploy (rule 4). No argument = all six engines.
  run python deploy/deploy_agents_a2a.py
  run python deploy/collect_agent_identities.py
  verify step7.sh
  end_phase
elif [ "$SKIP_GATEWAY" = 1 ]; then
  c_warn "gateway phase skipped (--skip-gateway) — engines run WITHOUT governed egress."
fi

# ── done ───────────────────────────────────────────────────────────────────────────────────
MINS=$(( (SECONDS - START_TS) / 60 ))
c_step "done" "in ${MINS}m"
APP_URL="$(gcloud run services describe vibeflix-app --region "${REGION:-us-central1}" \
             --project "$PROJECT" --format 'value(status.url)' 2>/dev/null || true)"
[ -n "$APP_URL" ] && c_ok "console: $APP_URL" || c_warn "no vibeflix-app service yet (app phase not run?)"
echo
echo "Next: open the console, pick an image + character + vendor + category, and Run."
echo "If something looks wrong, the per-step checks are in deploy/verify/step*.sh."

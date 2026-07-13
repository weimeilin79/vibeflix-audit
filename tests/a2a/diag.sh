#!/usr/bin/env bash
# A2A hop diagnostics (deploy/a2a-test-plan.md). Sourced or called per-command.
#   ./deploy/a2a_diag.sh probe <display> "<text>"
#   ./deploy/a2a_diag.sh grant_a2a <principal-or-@sa> <target-display>
#   ./deploy/a2a_diag.sh check_grant <target-display>
#   ./deploy/a2a_diag.sh errs <display>
set -uo pipefail
P="${PROJECT:-pokedemo-test}"; R="${REGION:-us-central1}"
B="https://$R-aiplatform.googleapis.com/v1beta1"
TOK() { gcloud auth print-access-token; }

_engine() {  # display → engine resource name
  curl -s -H "Authorization: Bearer $(TOK)" "$B/projects/$P/locations/$R/reasoningEngines" \
    | jq -r --arg n "$1" '[.reasoningEngines[]|select(.displayName==$n)][0].name'
}
_agent_reg() {  # display → agent registry resource id (agentregistry-…)
  gcloud alpha agent-registry services describe "${1}-agent" --project=$P --location=$R \
    --format='value(registryResource)' 2>/dev/null | xargs -r basename
}

probe() {  # $1 display  $2 text
  local E TID T ST
  E=$(_engine "$1")
  local resp; resp=$(curl -s -X POST -H "Authorization: Bearer $(TOK)" -H "Content-Type: application/json" \
    "$B/$E/a2a/v1/message:send" \
    -d "$(jq -nc --arg t "$2" '{message:{role:"ROLE_USER",messageId:"diag",content:[{text:$t}]}}')")
  TID=$(jq -r '.task.id // empty' <<<"$resp")
  [ -z "$TID" ] && { echo "  ❌ send failed: $(jq -c '.error.message // .' <<<"$resp" | head -c 200)"; return 1; }
  echo "  task $TID — polling…"
  for i in $(seq 1 18); do
    sleep 15
    T=$(curl -s -H "Authorization: Bearer $(TOK)" "$B/$E/a2a/v1/tasks/$TID")
    ST=$(jq -r '.status.state // .task.status.state // empty' <<<"$T")
    case "$ST" in TASK_STATE_COMPLETED|TASK_STATE_FAILED) break;; esac
  done
  echo "  state: $ST"
  jq -r '(.artifacts // .task.artifacts // [])[0].parts[0].text // (.status.message.content[0].text // empty) // empty' <<<"$T" | head -c 800
  echo
}

grant_a2a() {  # $1 member (principal:// or serviceAccount:…)  $2 target display
  local RR; RR=$(_agent_reg "$2")
  [ -z "$RR" ] && { echo "  ❌ no registry entry for $2-agent"; return 1; }
  gcloud alpha iap web add-iam-policy-binding \
    --resource-type=agent-registry --endpoint="$RR" --region=$R --project=$P \
    --member="$1" --role=roles/iap.egressor 2>&1 | tail -1
}

check_grant() {  # $1 target display
  local RR; RR=$(_agent_reg "$1")
  echo "  agent resource: $RR"
  gcloud alpha iap web get-iam-policy --resource-type=agent-registry --endpoint="$RR" \
    --region=$R --project=$P --format=json 2>/dev/null \
    | jq -r '.bindings[]?|select(.role=="roles/iap.egressor")|.members[]' | sed 's/^/    egressor: /'
}

errs() {  # $1 display
  local E; E=$(_engine "$1"); local ID; ID=$(basename "$E")
  gcloud logging read "resource.type=\"aiplatform.googleapis.com/ReasoningEngine\" AND resource.labels.reasoning_engine_id=\"$ID\"" \
    --project $P --limit 40 --format 'value(textPayload)' --freshness 5m 2>/dev/null \
    | grep -iE "403|egress|not author|unregist|error|exception|no report|denied|url:" | grep -v "ready\]" | head -12
}

"$@"

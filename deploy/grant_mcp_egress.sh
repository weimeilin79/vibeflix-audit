#!/usr/bin/env bash
#
# grant_mcp_egress.sh — apply deploy/policies.yaml as IAP egress grants (4c-iii).
#
# Each policy row → one roles/iap.egressor binding:
#   member    = the caller — an agent's identity principal (agent_identities.json)
#               or serviceAccount:vibeflix-app@… for the console app
#   condition = CEL on mcp.toolName (the tool allowlist)
#
# SCOPE — two forms (default = resource-scoped, so grants show in the console):
#   resource-scoped (DEFAULT): bound to the MCP server's Agent-Registry entry
#     (--resource-type=agent-registry --endpoint=<id>). Appears on the console's
#     Agent-Platform → Policies page, associated with that server. ⚠️ PREVIEW
#     surface — if your gcloud rejects --resource-type=agent-registry, use:
#   project-scoped (fallback): ./deploy/grant_mcp_egress.sh --project-scope
#     bound to the project iap_web root. Enforces identically but is NOT shown
#     in the console (this was the original form).
#
# Prereqs: agents deployed w/ identity (agent_identities.json), MCP servers
# REGISTERED (step 4a — resource scope needs their registry endpoint ids), the
# gateway + IAP authz extension bound (4c-i/ii).
#   ./deploy/grant_mcp_egress.sh                 # resource-scoped, apply
#   ./deploy/grant_mcp_egress.sh --dry-run       # print, don't apply
#   ./deploy/grant_mcp_egress.sh --project-scope # console-invisible fallback
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"; REGION="${REGION:-us-central1}"
MODE="${1:-}"
[ "$MODE" = "--project-scope" ] && SCOPE=project || SCOPE=resource
[ "$MODE" = "--dry-run" ] && DRY=1 || DRY=""

# Resolve an MCP server's Agent-Registry endpoint id (resource scope). The
# registered service's `name` last segment is the endpoint id IAP binds to.
# (Plain function — macOS bash 3.2 has no `declare -A`. Cached in temp files.)
_EP_CACHE="$(mktemp -d)"
# The MCP server's Agent-Registry resource id (registryResource basename =
# agentregistry-XXXX) — this is what `--mcp-server` binds the IAP policy to.
endpoint_for() {
  local srv="$1" f="$_EP_CACHE/$1"
  [ -f "$f" ] && { cat "$f"; return; }
  gcloud alpha agent-registry services describe "$srv" \
    --project="$PROJECT" --location="$REGION" --format='value(registryResource)' 2>/dev/null \
    | xargs -r basename | tee "$f"
}

"$ROOT/.venv/bin/python" - <<'PYEOF' | while IFS='|' read -r CALLER MEMBER SERVER TOOLS; do
import json, pathlib, sys, os, subprocess
try:
    import yaml
except ImportError:
    sys.exit("pyyaml missing: uv pip install --python .venv/bin/python pyyaml")
here = pathlib.Path("deploy")
policies = yaml.safe_load((here / "policies.yaml").read_text())["policies"]
idents = json.loads((here / "agent_identities.json").read_text())
project = os.environ["PROJECT"]
for row in policies:
    caller, server, tools = row["caller"], row["mcp_server"], row.get("allow_tools") or []
    if caller == "vibeflix-app":
        sa = f"vibeflix-app@{project}.iam.gserviceaccount.com"
        if subprocess.run(["gcloud","iam","service-accounts","describe",sa],
                          capture_output=True).returncode != 0:
            print(f"SKIP vibeflix-app: SA not created yet (step 5a) — re-run after", file=sys.stderr); continue
        member = f"serviceAccount:{sa}"
    else:
        entry = idents.get(caller)
        if not entry:
            print(f"SKIP: no identity for {caller} in agent_identities.json", file=sys.stderr); continue
        member = entry["principal"]
    print(f"{caller}|{member}|{server}|{','.join(tools)}")
PYEOF
  COND="$(mktemp -d)/cond.yaml"
  # mcp.toolName (codelab-verbatim camelCase). Tool names are unique across the
  # 3 servers, so tool-name scoping alone is precise; the SERVER scope comes from
  # the resource binding (resource mode) rather than a CEL clause.
  TOOL_LIST="$(echo "$TOOLS" | sed "s/,/', '/g")"
  cat > "$COND" <<EOF
expression: >-
  api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['$TOOL_LIST']
title: ${CALLER}-${SERVER}
EOF
  echo "── $CALLER → $SERVER [$TOOLS]  (scope=$SCOPE)"
  if [ -n "$DRY" ]; then
    sed 's/^/    /' "$COND"; echo "    member: $MEMBER"; continue
  fi
  if [ "$SCOPE" = resource ]; then
    EID="$(endpoint_for "$SERVER")"
    if [ -z "$EID" ]; then
      echo "    ⚠️ no registry endpoint for $SERVER — is it registered (4a)? skipping"; continue
    fi
    # ALPHA track; --mcp-server binds to the server's registry resource (console-visible).
    gcloud alpha iap web add-iam-policy-binding \
      --resource-type=agent-registry --mcp-server="$EID" --region="$REGION" --project="$PROJECT" \
      --member="$MEMBER" --role=roles/iap.egressor --condition-from-file="$COND" >/dev/null \
      && echo "    granted (mcp-server: $SERVER → $EID)" \
      || echo "    ⚠️ failed — re-run with --project-scope for the console-invisible fallback"
  else
    gcloud iap web add-iam-policy-binding --project="$PROJECT" \
      --member="$MEMBER" --role=roles/iap.egressor --condition-from-file="$COND" >/dev/null \
      && echo "    granted (project scope — NOT shown in console)" || echo "    ⚠️ failed"
  fi
done
echo "[grant_mcp_egress] done (scope=$SCOPE)."

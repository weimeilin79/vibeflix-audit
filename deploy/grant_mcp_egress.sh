#!/usr/bin/env bash
#
# grant_mcp_egress.sh — apply deploy/policies.yaml as IAP egress grants (4c-iii).
#
# One grant per policy row:
#   member    = the caller — an agent's identity principal (deploy/agent_identities.json)
#               or serviceAccount:vibeflix-app@… for the console app
#   role      = roles/iap.egressor
#   condition = CEL scoping to the row's MCP server + tool allowlist
#
# Prereqs: agents deployed w/ identity (agent_identities.json exists), the
# gateway + IAP authz extension bound (4c-i/ii). Usage:
#   ./deploy/grant_mcp_egress.sh            # apply every row
#   ./deploy/grant_mcp_egress.sh --dry-run  # print without applying
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
PROJECT="${PROJECT:?set PROJECT in deploy/.env}"
DRY="${1:-}"

"$ROOT/.venv/bin/python" - <<'PYEOF' | while IFS='|' read -r CALLER MEMBER SERVER TOOLS; do
import json, pathlib, sys
try:
    import yaml
except ImportError:
    sys.exit("pyyaml missing: uv pip install --python .venv/bin/python pyyaml")

here = pathlib.Path("deploy")
policies = yaml.safe_load((here / "policies.yaml").read_text())["policies"]
idents = json.loads((here / "agent_identities.json").read_text())

import os
project = os.environ["PROJECT"]
for row in policies:
    caller, server = row["caller"], row["mcp_server"]
    tools = row.get("allow_tools") or []
    if caller == "vibeflix-app":
        member = f"serviceAccount:vibeflix-app@{project}.iam.gserviceaccount.com"
    else:
        entry = idents.get(caller)
        if not entry:
            print(f"SKIP: no identity for {caller} in agent_identities.json", file=sys.stderr)
            continue
        member = entry["principal"]
    print(f"{caller}|{member}|{server}|{','.join(tools)}")
PYEOF
  COND="$(mktemp -d)/cond.yaml"
  # server scope + tool allowlist in one expression. NOTE: the tool-name
  # attribute key follows the codelab's mcp.tool.* pattern (isReadOnly was the
  # documented one) — if the gateway logs an unknown-attribute error, check the
  # live attribute list and adjust here once.
  TOOL_LIST="$(echo "$TOOLS" | sed "s/,/', '/g")"
  cat > "$COND" <<EOF
expression: >-
  api.getAttribute('iap.googleapis.com/mcp.server', '') == '$SERVER'
  && api.getAttribute('iap.googleapis.com/mcp.tool.name', '') in ['$TOOL_LIST']
title: ${CALLER}-${SERVER}
EOF
  echo "── $CALLER → $SERVER [$TOOLS]"
  if [ "$DRY" = "--dry-run" ]; then
    sed 's/^/    /' "$COND"; echo "    member: $MEMBER"
  else
    gcloud iap web add-iam-policy-binding --project="$PROJECT" \
      --member="$MEMBER" --role=roles/iap.egressor \
      --condition-from-file="$COND" >/dev/null \
      && echo "    granted" || echo "    ⚠️ failed — see error above"
  fi
done
echo "[grant_mcp_egress] done."

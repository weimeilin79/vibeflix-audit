#!/usr/bin/env bash
#
# rebuild_legal_rag.sh — CLEAN reload of the legal RAG corpus.
#
# setup_legal_rag.py REUSES a corpus by display name, and re-importing does NOT reliably
# UPDATE edited docs. So to reload changed docs cleanly, this:
#   1) DELETEs the existing corpus (matched by CORPUS_DISPLAY_NAME — never a hardcoded id)
#   2) clears the GCS staging (so removed/renamed docs don't linger)
#   3) re-stages docs + creates a FRESH corpus + imports   (via setup_legal_rag.py)
#   4) writes the new RAG_CORPUS into agents/legal/.env
#
# ALL config (project, region, bucket, corpus display name) is READ FROM deploy/.env —
# nothing is hardcoded here. Real shell env vars override the file.
#
# Usage:
#   ./deploy/rebuild_legal_rag.sh          # asks for confirmation before deleting
#   ./deploy/rebuild_legal_rag.sh -y       # skip the confirmation (or FORCE=1)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

# --- config: read from deploy/.env (the SAME file setup_legal_rag.py loads) ---
ENV_FILE="$HERE/.env"
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
else
  echo "WARN: $ENV_FILE not found — relying on shell env vars." >&2
fi

# resolve exactly like setup_legal_rag.py (no hardcoded project/region/corpus)
PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-vibeflix-artifacts}"
DISPLAY="${CORPUS_DISPLAY_NAME:-vibeflix-legal-kb}"
GCS="gs://${BUCKET}/legal-docs"

[ -n "$PROJECT" ] || { echo "ERROR: PROJECT not set — add PROJECT=... to deploy/.env" >&2; exit 1; }

# activate the project venv if present
[ -f "$ROOT/.venv/bin/activate" ] && . "$ROOT/.venv/bin/activate"

echo "==> config from deploy/.env: project=$PROJECT region=$REGION bucket=$BUCKET corpus='$DISPLAY'"

# --- confirm (destructive) ---
if [ "${1:-}" != "-y" ] && [ "${FORCE:-}" != "1" ]; then
  read -r -p "This DELETES corpus '$DISPLAY' in $PROJECT/$REGION and re-imports. Continue? [y/N] " ans
  case "$ans" in y|Y) ;; *) echo "aborted."; exit 1;; esac
fi

# --- 1) delete existing corpus/corpora with that display name ---
echo "==> [1/4] deleting existing corpus (display_name='$DISPLAY')…"
PROJECT="$PROJECT" REGION="$REGION" CORPUS_DISPLAY_NAME="$DISPLAY" python - <<'PY'
import os, agentplatform
project = os.environ["PROJECT"]; region = os.environ["REGION"]; display = os.environ["CORPUS_DISPLAY_NAME"]
client = agentplatform.Client(project=project, location=region)
found = 0
for item in client.rag.list_corpora():
    corp = item[0] if isinstance(item, tuple) else item
    if getattr(corp, "display_name", None) == display and getattr(corp, "name", None):
        client.rag.delete_corpus(name=corp.name)
        print(f"    deleted {corp.name}")
        found += 1
print("    (no matching corpus — nothing to delete)" if not found else f"    ({found} corpus/corpora deleted)")
PY

# --- 2) clear GCS staging ---
echo "==> [2/4] clearing GCS staging $GCS/ …"
gcloud storage rm -r "$GCS/" --project "$PROJECT" 2>/dev/null || echo "    (already empty)"

# --- 3) re-stage docs + create fresh corpus + import; capture the printed RAG_CORPUS ---
echo "==> [3/4] re-staging docs + creating fresh corpus + importing…"
TMP_OUT="$(mktemp)"
python deploy/setup_legal_rag.py | tee "$TMP_OUT"
NEW_CORPUS="$(grep -oE 'projects/[^[:space:]]+/ragCorpora/[0-9]+' "$TMP_OUT" | tail -1 || true)"
rm -f "$TMP_OUT"

# --- 4) write the new RAG_CORPUS into agents/legal/.env (with a backup) ---
LEGAL_ENV="$ROOT/agents/legal/.env"
if [ -n "$NEW_CORPUS" ] && [ -f "$LEGAL_ENV" ]; then
  echo "==> [4/4] updating $LEGAL_ENV → RAG_CORPUS=$NEW_CORPUS"
  cp "$LEGAL_ENV" "$LEGAL_ENV.bak"
  NEW_CORPUS="$NEW_CORPUS" REGION="$REGION" LEGAL_ENV="$LEGAL_ENV" python - <<'PY'
import os, re, pathlib
p = pathlib.Path(os.environ["LEGAL_ENV"]); new = os.environ["NEW_CORPUS"]; region = os.environ["REGION"]
s = p.read_text()
s = re.sub(r'(?m)^RAG_CORPUS=.*$', f'RAG_CORPUS={new}', s) if re.search(r'(?m)^RAG_CORPUS=', s) else s + f'\nRAG_CORPUS={new}\n'
if not re.search(r'(?m)^RAG_LOCATION=', s):
    s += f'RAG_LOCATION={region}\n'
p.write_text(s)
print("    wrote RAG_CORPUS + RAG_LOCATION")
PY
  echo "    backup: $LEGAL_ENV.bak"
else
  echo "==> [4/4] set RAG_CORPUS manually (couldn't auto-write agents/legal/.env):"
  echo "    RAG_CORPUS=${NEW_CORPUS:-<see output above>}"
fi

echo
echo "DONE. Restart the legal agent to pick up the new corpus:"
echo "  • adk web:      restart 'adk web agents/legal'"
echo "  • docker mesh:  update RAG_CORPUS on the 'legal' service, then: docker compose up -d legal"

#!/usr/bin/env python3
"""setup_legal_rag.py — provision the Legal knowledge-base RAG corpus (Agent Platform 2.0).

Ingests `resource/legal/docs/` into a Vertex AI RAG Engine corpus backed by the
**RAG-managed Vertex AI Vector Search** store (`rag_managed_vertex_vector_search`), using
the 2.0 `agentplatform` client. Steps:

  1. stage the docs to GCS   (gs://$BUCKET/legal-docs/)
  2. create (or reuse) the corpus  (managed Vertex Vector Search + text-embedding-005)
  3. import the staged files

Prints `RAG_CORPUS` — set it (plus `RAG_LOCATION`) wherever `search_legal_docs` runs
(i.e. on the legal agent). Re-running re-imports (handy after editing a doc).

Prereqs (run in a venv that has them):
    pip install -r deploy/requirements-legal-rag.txt   # the 2.0 SDK (provisioning only)
    gcloud auth application-default login              # ADC for the Vertex + GCS calls

Usage:
    PROJECT=<your-project> REGION=us-central1 BUCKET=vibeflix-artifacts \\
        python deploy/setup_legal_rag.py
"""

import os
import sys
import glob
import subprocess

from dotenv import load_dotenv

# Load deploy/.env (if present) so PROJECT/REGION/BUCKET/etc. can live in a file for local
# testing instead of the shell. Real shell env vars still take precedence (override=False).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

PROJECT = os.environ.get("PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
if not PROJECT:
    raise SystemExit(
        "✗ PROJECT / GOOGLE_CLOUD_PROJECT is not set. Refusing to guess.\n"
        "  This used to default to a hardcoded project, so forgetting to export it\n"
        "  silently pointed the script at SOMEONE ELSE'S project.\n"
        "  Run:  export PROJECT=<your-project> REGION=<your-region>")

# ⚠️ RAG Engine is REGIONAL — use us-central1 (same as Memory Bank), NOT "global".
REGION = os.environ.get("REGION", "us-central1")
BUCKET = os.environ.get("BUCKET", "vibeflix-artifacts")
DISPLAY = os.environ.get("CORPUS_DISPLAY_NAME", "vibeflix-legal-kb")
# Embedding model for the corpus (text-embedding-005 is a solid default).
EMBED = os.environ.get("EMBEDDING_MODEL", "publishers/google/models/text-embedding-005")

_HERE = os.path.dirname(os.path.abspath(__file__))
_DOCS = os.path.join(_HERE, "..", "resource", "legal", "docs")
_GCS = f"gs://{BUCKET}/legal-docs"


def main() -> None:
    files = sorted(f for f in glob.glob(os.path.join(_DOCS, "*")) if os.path.isfile(f))
    if not files:
        sys.exit(f"[legal-rag] no docs found in {_DOCS}")
    print(f"[legal-rag] project={PROJECT} region={REGION} bucket={BUCKET} · {len(files)} docs")

    # 1) stage the docs to GCS
    print(f"[legal-rag] 1/3 staging docs → {_GCS}/ …")
    subprocess.run(
        ["gcloud", "storage", "cp", "-r", os.path.join(_DOCS, "."), _GCS + "/", "--project", PROJECT],
        check=True,
    )

    # 2) the RAG-managed Vertex Vector Search backend uses the Vector Search API.
    print("[legal-rag] 2/3 enabling Vector Search API…")
    subprocess.run(["gcloud", "services", "enable", "vectorsearch.googleapis.com",
                    "--project", PROJECT], check=True)

    try:
        import agentplatform
        from agentplatform._genai.types import common as C
    except ImportError:
        sys.exit("[legal-rag] missing SDK. Run: pip install -r deploy/requirements-legal-rag.txt")
    client = agentplatform.Client(project=PROJECT, location=REGION)

    # Put the project's RAG managed-DB into SERVERLESS mode BEFORE creating the corpus.
    # A FRESH project defaults to SPANNER mode, which is capacity-restricted in some
    # regions (e.g. us-central1) → corpus creation fails `400 INVALID_ARGUMENT`. This is a
    # PROJECT-level config, separate from the corpus's vector backend below. Best-effort +
    # idempotent; if it can't be set, corpus creation will surface the real error.
    try:
        import json as _json, urllib.request
        import google.auth, google.auth.transport.requests as _grt
        _creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        _creds.refresh(_grt.Request())
        _req = urllib.request.Request(
            f"https://{REGION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT}"
            f"/locations/{REGION}/ragEngineConfig?updateMask=rag_managed_db_config",
            method="PATCH",
            data=_json.dumps({"ragManagedDbConfig": {"serverless": {}}}).encode(),
            headers={"Authorization": f"Bearer {_creds.token}", "Content-Type": "application/json"})
        urllib.request.urlopen(_req, timeout=90).read()
        print("[legal-rag] ragEngineConfig → serverless (avoids the Spanner capacity limit on new projects)")
    except Exception as _e:  # noqa: BLE001
        print(f"[legal-rag] ⚠️ could not set serverless RAG mode ({type(_e).__name__}: {_e}). "
              f"If corpus creation 400s on Spanner capacity, PATCH …/ragEngineConfig with "
              f'{{"ragManagedDbConfig": {{"serverless": {{}}}}}} manually.')

    # 3) reuse-or-create the corpus. IMPORTANT: use the TYPED
    #    RagManagedVertexVectorSearch object — an empty dict {} is silently ignored and
    #    falls back to RagManagedDb (which defaults to the Spanner mode that's
    #    capacity-restricted for new projects). This backend is independent of the
    #    Spanner/Serverless managed-DB mode.
    def _display(item):
        for cand in (item, *(item if isinstance(item, (tuple, list)) else ())):
            if hasattr(cand, "display_name"):
                return cand
        return None
    corpus = None
    for item in client.rag.list_corpora():
        cand = _display(item)
        if cand is not None and cand.display_name == DISPLAY:
            corpus = cand
            print(f"[legal-rag] 3/3 reusing corpus: {corpus.name}")
            break
    if corpus is None:
        print(f"[legal-rag] 3/3 creating corpus '{DISPLAY}' (RagManagedVertexVectorSearch)…")
        corpus = client.rag.create_corpus(rag_corpus=C.RagCorpus(
            display_name=DISPLAY,
            description="Vibeflix legal 'tribal knowledge' — scattered process docs.",
            vector_db_config=C.RagVectorDbConfig(
                rag_managed_vertex_vector_search=C.RagVectorDbConfigRagManagedVertexVectorSearch(),
            ),
        ))
        print(f"[legal-rag]      created: {corpus.name}")

    # import the staged files into the corpus
    print(f"[legal-rag]      importing {len(files)} files from {_GCS}/ …")
    client.rag.import_files(name=corpus.name, import_config={"gcs_source": {"uris": [_GCS + "/"]}})

    print("\n=== Legal RAG corpus ready ===")
    print("RAG_CORPUS :", corpus.name)
    print("\nSet these wherever search_legal_docs runs (the legal agent's env):")
    print(f"  RAG_CORPUS={corpus.name}")
    print(f"  RAG_LOCATION={REGION}")


if __name__ == "__main__":
    main()

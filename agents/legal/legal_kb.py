"""Legal knowledge base — RAG over scattered "tribal knowledge".

The Legal Clearance agent has NO officially defined workflow. The real process is
scattered across the documents in `resource/legal/docs/` (a stale wiki, a contradictory
email thread, meeting notes, a Slack export, a rate card, a risk memo, an outdated SOP,
a departing employee's brain dump). This module lets the agent RECONSTRUCT the process
by searching those docs — exposed to the agent as the `search_legal_docs` FunctionTool.

Two retrievers, chosen by env (no code change to flip):
  * `RAG_CORPUS` set → Vertex AI RAG Engine `:retrieveContexts` via a **direct REST call**
    signed with ADC (`google.auth` only — no SDK / pandas at runtime), against a corpus
    backed by the RAG-managed Vertex AI Vector Search store. Provision it once with
    `deploy/setup_legal_rag.py` (that's where the SDK is used).
  * otherwise → a self-contained local keyword retriever over `LEGAL_DOCS_DIR`, so the
    agent works offline / in CI with zero Vertex setup.
"""

import os
import re
import glob
import json

_RAG_CORPUS = os.environ.get("RAG_CORPUS", "").strip()
_RAG_LOCATION = os.environ.get("RAG_LOCATION", "us-central1")
_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()


def _docs_dir() -> str:
    here = os.path.dirname(__file__)
    for c in (os.environ.get("LEGAL_DOCS_DIR"),
              "/app/legal-docs",
              os.path.join(here, "..", "..", "resource", "legal", "docs")):
        if c and os.path.isdir(c):
            return c
    return ""


# ---- Local keyword retriever (default; stdlib only) ------------------------
_STOP = set("the a an of to for and or is are be in on at by with from as it this that we "
            "you they i our your their but if so not no yes do does can will would should "
            "there here what when where which who how".split())


def _tokens(s: str) -> list:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _STOP and len(t) > 1]


def _load_chunks() -> list:
    chunks = []
    for path in sorted(glob.glob(os.path.join(_docs_dir(), "*"))):
        if not os.path.isfile(path):
            continue
        name = os.path.basename(path)
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if len(para) >= 25:
                chunks.append({"source": name, "text": para})
    return chunks


def _local_search(query: str, top_k: int) -> list:
    qset = set(_tokens(query))
    if not qset:
        return []
    scored = []
    for ch in _load_chunks():
        toks = _tokens(ch["text"])
        overlap = qset & set(toks)
        if not overlap:
            continue
        score = sum(toks.count(t) for t in overlap) + 2 * len(overlap)
        scored.append((score, ch))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"source": ch["source"], "text": ch["text"], "score": round(float(s), 2)}
            for s, ch in scored[:top_k]]


# ---- Vertex AI RAG Engine retriever — direct REST (no SDK needed) ----------
# retrieveContexts is a single POST, so we sign it with ADC (the same credentials the
# agent already uses for Gemini) and call the endpoint directly. No google-cloud-aiplatform
# / pandas at runtime — only `google.auth`, which is already present. The heavy SDK lives
# only in the provisioning script (deploy/setup_legal_rag.py).
def _vertex_search(query: str, top_k: int) -> list:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, adc_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    project = _PROJECT or adc_project
    url = (f"https://{_RAG_LOCATION}-aiplatform.googleapis.com/v1/"
           f"projects/{project}/locations/{_RAG_LOCATION}:retrieveContexts")
    body = {
        "vertex_rag_store": {"rag_resources": {"rag_corpus": _RAG_CORPUS}},
        "query": {"text": query, "rag_retrieval_config": {"top_k": top_k}},
    }
    resp = AuthorizedSession(creds).post(url, json=body, timeout=30)
    resp.raise_for_status()
    contexts = (resp.json().get("contexts") or {}).get("contexts") or []
    out = []
    for ctx in contexts:
        src = ctx.get("sourceDisplayName") or ctx.get("sourceUri") or "corpus"
        out.append({"source": os.path.basename(src), "text": ctx.get("text", "") or "",
                    "score": round(float(ctx.get("score") or ctx.get("distance") or 0.0), 4)})
    return out


def search_legal_docs(query: str, top_k: int = 5) -> str:
    """Search the scattered legal 'tribal knowledge' documents and return the most
    relevant excerpts, each with its source document. The legal process is NOT defined in
    one place — use this to piece it together: certification rules per category, royalty
    tiers, the insurance minimum, customs/HS codes, the license-amendment and
    contract-execution steps, and the two facts you must go ASK for (the vendor's royalty
    tier → from vendor clearance; the licensee's safety-certification id → from the user).

    Args:
        query: A natural-language question, e.g. "what certifications does Apparel need",
            "how is the royalty tier decided", "minimum product liability insurance",
            "what must the licensee provide before we can execute the contract".
        top_k: How many document excerpts to return (1–12, default 5).
    """
    top_k = max(1, min(int(top_k or 5), 12))
    print(f"[legal_kb] search_legal_docs({query!r}) via {'vertex_rag' if _RAG_CORPUS else 'local_keyword'}", flush=True)
    try:
        hits = _vertex_search(query, top_k) if _RAG_CORPUS else _local_search(query, top_k)
    except Exception as e:
        # Vertex misconfigured / unreachable → fall back to local so the agent still works.
        print(f"[legal_kb] retrieval error ({type(e).__name__}: {e}); using local retriever", flush=True)
        hits = _local_search(query, top_k)
    return json.dumps({
        "query": query,
        "retriever": "vertex_rag" if _RAG_CORPUS else "local_keyword",
        "results": hits,
    })

"""Google-credential plumbing for the CLOUD deployment, gated by RUN_LOCAL.

In the local compose mesh every hop is plain http between containers — no
credentials anywhere. In the cloud the same hops are IAM-gated:

    agents / app ── MCP ──► Agent Gateway / Cloud Run   (ID token, audience=origin)
    orchestrator ── A2A ──► Agent Runtime engines       (OAuth access token)

RUN_LOCAL decides which world we're in:

    unset            → AUTO-DETECT: deployed on GCP (Cloud Run / Agent Runtime /
                       GCE — K_SERVICE or metadata server) → auth ON; else local
    RUN_LOCAL=true   → force local (no auth), even on GCP
    RUN_LOCAL=false  → force cloud auth, even off GCP (laptop → cloud services)

Token choice is by host: ``*.googleapis.com`` → OAuth access token (Vertex /
Agent Runtime APIs); anything else (``*.run.app``, gateway domains) → OIDC ID
token with audience = scheme://host. Works on user ADC locally (gcloud ADC's
refresh returns an id_token) and on service accounts / metadata servers in the
cloud (``fetch_id_token``). Tokens are cached and re-minted before expiry —
attach-per-request, so long-lived processes never hold a stale credential.
"""

import os
import time
import threading
from urllib.parse import urlsplit

import httpx


_AUTO_DETECTED: bool | None = None


def _on_gcp() -> bool:
    """Are we running ON Google Cloud? Cloud Run / Functions set K_SERVICE; for
    everything else (Agent Runtime, GCE) the metadata server is the canonical
    tell — reachable only inside GCP."""
    if os.environ.get("K_SERVICE") or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
        return True
    import socket
    try:
        with socket.create_connection(("metadata.google.internal", 80), timeout=0.5):
            return True
    except OSError:
        return False


def run_local() -> bool:
    """Deployed to gcloud = not local — detected automatically. RUN_LOCAL, when
    set, is an explicit OVERRIDE in either direction:

        RUN_LOCAL=true    force local (no auth) even on GCP
        RUN_LOCAL=false   force cloud auth even off GCP (e.g. laptop → cloud MCPs)
        unset             auto-detect (on GCP → auth on; otherwise local)
    """
    v = os.environ.get("RUN_LOCAL", "").strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    global _AUTO_DETECTED
    if _AUTO_DETECTED is None:
        _AUTO_DETECTED = not _on_gcp()
    return _AUTO_DETECTED


class _TokenMinter:
    """Lazily-initialized ADC token source: one access token + per-audience ID tokens."""

    def __init__(self):
        self._lock = threading.Lock()
        self._access_creds = None
        self._id_tokens: dict[str, tuple[str, float]] = {}

    @staticmethod
    def _request():
        import google.auth.transport.requests
        return google.auth.transport.requests.Request()

    def access_token(self) -> str:
        import google.auth
        with self._lock:
            if self._access_creds is None:
                self._access_creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            if not self._access_creds.valid:
                self._access_creds.refresh(self._request())
            return self._access_creds.token

    def id_token(self, audience: str) -> str:
        with self._lock:
            cached = self._id_tokens.get(audience)
            if cached and cached[1] > time.time():
                return cached[0]
        try:
            # Service accounts / metadata server (Cloud Run, Agent Runtime).
            from google.oauth2 import id_token as _idt
            token = _idt.fetch_id_token(self._request(), audience)
        except Exception:
            # User ADC (local dev against cloud services): gcloud ADC includes the
            # openid scope, so a refresh carries an id_token. NOTE: not audience-
            # bound — Cloud Run accepts it for user principals.
            import google.auth
            creds, _ = google.auth.default()
            creds.refresh(self._request())
            token = getattr(creds, "id_token", None)
            if not token:
                raise RuntimeError(
                    "RUN_LOCAL=false but no ID token available — run "
                    "`gcloud auth application-default login` or use a service account."
                )
        with self._lock:
            self._id_tokens[audience] = (token, time.time() + 45 * 60)
        return token


_MINTER = _TokenMinter()


def token_for(url: str) -> str:
    """The right bearer token for this URL (access token for googleapis, else ID token)."""
    parts = urlsplit(url)
    if parts.hostname and parts.hostname.endswith("googleapis.com"):
        return _MINTER.access_token()
    return _MINTER.id_token(f"{parts.scheme}://{parts.hostname}")


class GoogleAuth(httpx.Auth):
    """httpx auth hook: attach a fresh Google token per request (sync + async)."""

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {token_for(str(request.url))}"
        yield request


def maybe_auth() -> httpx.Auth | None:
    """Drop-in for httpx clients: `httpx.AsyncClient(auth=maybe_auth())`."""
    return None if run_local() else GoogleAuth()


def auth_headers(url: str) -> dict:
    """One-shot headers for short-lived connections (`streamablehttp_client(url, headers=…)`)."""
    return {} if run_local() else {"Authorization": f"Bearer {token_for(url)}"}


def mcp_httpx_factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
    """`httpx_client_factory` for StreamableHTTPConnectionParams — every MCP
    connection the toolset opens carries per-request Google auth."""
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout if timeout is not None else httpx.Timeout(30.0),
        auth=GoogleAuth(),
        follow_redirects=True,
    )


def a2a_httpx_client(timeout: float = 600.0) -> httpx.AsyncClient | None:
    """Long-lived client for RemoteA2aAgent(httpx_client=…); None when local."""
    if run_local():
        return None
    return httpx.AsyncClient(auth=GoogleAuth(), timeout=timeout)


# ---------------------------------------------------------------------------
# A2A endpoint shapes differ between worlds:
#   local serve_a2a:  card GET  {base}/.well-known/agent-card.json · rpc POST {base}/
#   Agent Runtime:    card GET  {base}/a2a/v1/card                 · rpc POST <card.url>
# ---------------------------------------------------------------------------

def is_engine_url(base: str) -> bool:
    """True when the A2A base points at a Vertex Agent Runtime engine."""
    host = urlsplit(base).hostname or ""
    return host.endswith("aiplatform.googleapis.com")


def a2a_card_url(base: str) -> str:
    base = base.rstrip("/")
    if is_engine_url(base):
        return f"{base}/a2a/v1/card"
    return f"{base}/.well-known/agent-card.json"


_RPC_URL_CACHE: dict[str, str] = {}


async def resolve_a2a_rpc_url(base: str) -> str:
    """Where to POST raw JSON-RPC (message/send). Local: the service root.
    Engines: the url advertised by the agent card (fetched once, cached)."""
    base = base.rstrip("/")
    if not is_engine_url(base):
        return f"{base}/"
    if base in _RPC_URL_CACHE:
        return _RPC_URL_CACHE[base]
    async with httpx.AsyncClient(timeout=20, auth=GoogleAuth()) as client:
        resp = await client.get(a2a_card_url(base))
        resp.raise_for_status()
        url = (resp.json().get("url") or "").rstrip("/") or f"{base}/a2a/v1"
    _RPC_URL_CACHE[base] = url
    return url

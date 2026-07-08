"""Google-credential plumbing for the CLOUD deployment, gated by RUN_LOCAL.

In the local compose mesh every hop is plain http between containers — no
credentials anywhere. In the cloud the same hops are IAM-gated:

    agents / app ── MCP ──► Agent Gateway / Cloud Run   (ID token, audience=origin)
    orchestrator ── A2A ──► Agent Runtime engines       (OAuth access token)

RUN_LOCAL decides which world we're in:

    RUN_LOCAL=true   (or unset — the DEFAULT) → no auth attached; local behavior
    RUN_LOCAL=false  → every helper below mints the right Google token per request

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


def run_local() -> bool:
    """True unless RUN_LOCAL is explicitly false/0/no — local is the safe default."""
    return os.environ.get("RUN_LOCAL", "true").strip().lower() not in ("false", "0", "no")


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

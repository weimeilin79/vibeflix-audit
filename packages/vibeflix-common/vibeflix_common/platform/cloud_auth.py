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


def _peek_jwt(token: str) -> str:
    """Decode a JWT's payload (NO signature check) to report aud + seconds-to-expiry.

    Diagnostic only: the MCP 401 ('access token could not be verified') can mean the ID
    token is EXPIRED (stale 45-min cache outliving the real token) or WRONG-AUDIENCE
    (aud != the MCP server URL). This surfaces both from the token itself. Never logs the
    token — only its claims.
    """
    try:
        import base64
        import json
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # restore base64url padding
        claims = json.loads(base64.urlsafe_b64decode(payload))
        aud = claims.get("aud", "?")
        exp = claims.get("exp")
        left = int(exp - time.time()) if exp else "?"
        return f"aud={aud} exp_in={left}s type={'id' if aud else 'access?'}"
    except Exception as e:  # noqa: BLE001 — diagnostics must never break auth
        return f"(unparseable: {type(e).__name__})"


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

    def access_token(self, force: bool = False) -> str:
        """`force=True` re-mints even when the cached credential still looks valid.

        `creds.valid` is a PREDICTION: the metadata server can hand back a token carrying only
        its remaining lifetime (see the note in a2a/engine.py), so a token can pass this check,
        travel, and be rejected on arrival. When the target says 401 there is no point asking
        the same cached object again — force a fresh mint.
        """
        import google.auth
        with self._lock:
            if self._access_creds is None:
                self._access_creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            if force or not self._access_creds.valid:
                self._access_creds.refresh(self._request())
            return self._access_creds.token

    def _id_token_via_impersonation(self, audience: str, sa: str | None = None) -> str:
        """Mint an audience-bound OIDC token by impersonating MCP_INVOKER_SA.

        An AGENT_IDENTITY engine runs as `principal://…/reasoningEngines/<id>` with
        NO service account behind the metadata server, so `fetch_id_token` cannot
        work — and Cloud Run rejects everything except an audience-bound ID token
        (verified: access token -> 401 "could not be verified", ID token -> 200,
        no token -> 403). The engine CAN mint an access token, and an access token
        is enough to call iamcredentials, so we bootstrap the ID token from there.

        Requires: the agent principal holds roles/iam.serviceAccountTokenCreator on
        MCP_INVOKER_SA, and (gateway is default-deny) iap.egressor on the registered
        gcp-iamcredentials endpoints.
        """
        import google.auth
        from google.auth import impersonated_credentials

        sa = sa or os.environ.get("MCP_INVOKER_SA")
        if not sa:
            raise RuntimeError(
                "MCP_INVOKER_SA not set — an agent-identity engine cannot mint an "
                "ID token for a Cloud Run backend without an SA to impersonate."
            )
        source_creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        target = impersonated_credentials.Credentials(
            source_credentials=source_creds,
            target_principal=sa,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
            lifetime=3600,
        )
        id_creds = impersonated_credentials.IDTokenCredentials(
            target_credentials=target,
            target_audience=audience,
            include_email=True,
        )
        id_creds.refresh(self._request())
        return id_creds.token

    def _current_sa_email(self) -> str | None:
        """The service account THIS process runs as, or None if we're a human.

        Used to mint an ID token by impersonating ourselves — see the Cloud Build note in
        id_token(). google.auth reports "default" for metadata-server credentials, so fall
        through to the metadata /email endpoint, which works even where /identity does not.
        """
        try:
            import google.auth
            creds, _ = google.auth.default()
            email = getattr(creds, "service_account_email", None)
            if email and email != "default":
                return email
            from google.auth.compute_engine import _metadata
            return _metadata.get(self._request(), "instance/service-accounts/default/email")
        except Exception:
            return None

    def id_token(self, audience: str, force: bool = False) -> str:
        with self._lock:
            if force:
                # The 45-min cache TTL below can outlive the token's REAL exp (see the
                # diagnostic on the next line), so a 401 must invalidate, not re-read.
                self._id_tokens.pop(audience, None)
            cached = self._id_tokens.get(audience)
            if cached and cached[1] > time.time():
                # DIAGNOSTIC: a cache HIT still 401s if the token's REAL exp is past —
                # our 45-min cache TTL can outlive the token. exp_in<0 here = the bug.
                print(f"[idtoken] {audience} CACHE-HIT {_peek_jwt(cached[0])} "
                      f"cache_left={int(cached[1]-time.time())}s", flush=True)
                return cached[0]
        try:
            if os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
                # Agent Runtime + AGENT_IDENTITY: metadata server has no SA, and the
                # ADC fallback below returns a token Cloud Run can't verify (401).
                token = self._id_token_via_impersonation(audience)
                print(f"[idtoken] {audience} MINTED via impersonation "
                      f"{_peek_jwt(token)}", flush=True)
            else:
                # Service accounts / metadata server (Cloud Run, GCE).
                from google.oauth2 import id_token as _idt
                token = _idt.fetch_id_token(self._request(), audience)
        except Exception as _imp_exc:
            # DIAGNOSTIC: impersonation FAILED — this is the silently-swallowed path.
            # In an agent-identity engine the ADC fallback yields a token Cloud Run
            # CANNOT verify (→ 401), so a failure here is very likely the 401 we chase.
            print(f"[idtoken] {audience} ⚠️ impersonation FAILED "
                  f"({type(_imp_exc).__name__}: {str(_imp_exc)[:120]}) → ADC fallback",
                  flush=True)
            token = None
            # CLOUD BUILD (and anything whose metadata server serves access tokens but NOT
            # `/identity` — it 404s with "please provide a user-specified service account",
            # even when the build runs as a user-specified SA). We are a service account with
            # no way to fetch an ID token directly, but an ACCESS token is enough to call
            # iamcredentials, so mint the audience-bound ID token by impersonating OURSELVES.
            # Requires roles/iam.serviceAccountTokenCreator on our own service account.
            self_sa = self._current_sa_email()
            if self_sa:
                try:
                    token = self._id_token_via_impersonation(audience, sa=self_sa)
                    print(f"[idtoken] {audience} MINTED via SELF-impersonation as {self_sa} "
                          f"{_peek_jwt(token)}", flush=True)
                except Exception as _self_exc:
                    print(f"[idtoken] {audience} ⚠️ self-impersonation as {self_sa} FAILED "
                          f"({type(_self_exc).__name__}: {str(_self_exc)[:160]})", flush=True)

            if not token:
                # User ADC (local dev against cloud services): gcloud ADC includes the
                # openid scope, so a refresh carries an id_token. NOTE: not audience-
                # bound — Cloud Run accepts it for user principals.
                import google.auth
                creds, _ = google.auth.default()
                creds.refresh(self._request())
                token = getattr(creds, "id_token", None)
            if not token:
                raise RuntimeError(
                    "RUN_LOCAL=false but no ID token available.\n"
                    "  • as a human: run `gcloud auth application-default login`\n"
                    f"  • as a service account ({self_sa or 'unknown'}): it needs\n"
                    "    roles/iam.serviceAccountTokenCreator ON ITSELF, so it can mint an\n"
                    "    audience-bound ID token via iamcredentials. Cloud Build's metadata\n"
                    "    server cannot issue one directly."
                )
            print(f"[idtoken] {audience} ADC-fallback token {_peek_jwt(token)} "
                  f"(NOT audience-bound — Cloud Run will 401 an agent identity)", flush=True)
        with self._lock:
            self._id_tokens[audience] = (token, time.time() + 45 * 60)
        return token


_MINTER = _TokenMinter()


def prewarm_id_token(url: str) -> None:
    """Mint (and cache) the ID token for ``url`` NOW, at import, best-effort.

    An agent-identity engine mints its MCP token by impersonating MCP_INVOKER_SA —
    two extra round trips, themselves routed through the governed gateway. Paying
    that on the first MCP handshake blew ADK's 5s connect budget and surfaced as an
    opaque TaskGroup TimeoutError. Warming the cache here moves the cost to process
    start, where nothing is waiting on it. Never fatal: if it fails we let the real
    request produce the real error.
    """
    parts = urlsplit(url)
    if not parts.hostname:
        return
    try:
        _MINTER.id_token(f"{parts.scheme}://{parts.hostname}")
    except Exception:
        pass


def mcp_auth_header(url: str) -> dict:
    """`header_provider` for McpToolset — pre-set OUR audience-bound ID token.

    ROOT CAUSE this fixes: ADK's mcp_session_manager builds an mTLS transport whenever
    GOOGLE_API_USE_CLIENT_CERTIFICATE != "false" (its default is "true", and we keep it UNSET
    because the SESSION service needs it for bound tokens). That transport's `before_request`
    injects `google.auth.default().token` — the AGENT'S ACCESS TOKEN — and REPLACES our
    httpx_client_factory, so our two-header ID-token logic never runs for MCP (measured: 0
    auth_flow hits for MCP vs 170 for the task store). Cloud Run must REMOTELY verify an access
    token (token introspection), which flakes under the concurrent fan-out → the intermittent
    `401 "access token could not be verified"`. An ID token is verified LOCALLY (signature), so
    it can't flake that way.
    ADK's before_request skips if `Authorization` is already present, so pre-setting it to our
    ID token here makes ADK leave it alone. Fresh per session-creation (the minter caches +
    refreshes), and it does NOT touch the USE_CLIENT_CERTIFICATE flag, so the session fix stays.
    """
    if run_local():
        return {}
    parts = urlsplit(url)
    if not parts.hostname:
        return {}
    try:
        tok = _MINTER.id_token(f"{parts.scheme}://{parts.hostname}")
        print(f"[mcp-hdr] inject ID token for {parts.hostname} {_peek_jwt(tok)}", flush=True)
        return {"Authorization": f"Bearer {tok}"}
    except Exception as e:  # noqa: BLE001 — never break the connection; let ADK fall back
        print(f"[mcp-hdr] ⚠️ could not mint ID token for {parts.hostname}: "
              f"{type(e).__name__}: {e}", flush=True)
        return {}


def token_for(url: str, force: bool = False) -> str:
    """The right bearer token for this URL (access token for googleapis, else ID token).

    `force=True` skips every cache — used by GoogleAuth's retry after a 401.
    """
    parts = urlsplit(url)
    if parts.hostname and parts.hostname.endswith("googleapis.com"):
        return _MINTER.access_token(force=force)
    return _MINTER.id_token(f"{parts.scheme}://{parts.hostname}", force=force)


class GoogleAuth(httpx.Auth):
    """httpx auth hook: attach a fresh Google token per request (sync + async)."""

    def auth_flow(self, request):
        """Attach Google credentials, and retry ONCE if the target rejects them.

        Why the retry: tokens here can expire *in flight* — the cached credential passes
        `creds.valid`, the request travels, and the endpoint answers 401. Every caller then
        pays for it differently: the A2A poll surfaces the 401, while RemoteTaskStore swallows
        it and falls back to local memory, so the engine answers "task not found" (404) for a
        task that exists. One forced re-mint here fixes all of them at once, because every
        client built with maybe_auth() shares this flow.
        """
        for _attempt in (0, 1):
            force = _attempt == 1
            url = str(request.url)
            parts = urlsplit(url)
            host = parts.hostname or ""
        
            # If running inside a Reasoning Engine (Agent Runtime):
            if os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
                access_tok = _MINTER.access_token(force=force)
                # If the destination is a non-Google endpoint or mtls.googleapis.com (gateway-routed):
                if "googleapis.com" not in host or "mtls.googleapis.com" in host:
                    # Egress goes through the gateway. Put the access token in Proxy-Authorization.
                    request.headers["Proxy-Authorization"] = f"Bearer {access_tok}"
                    if "googleapis.com" not in host:
                        # Non-Google endpoint (e.g. Cloud Run MCP server) requires ID token
                        try:
                            aud = f"{parts.scheme}://{host}"
                            id_tok = _MINTER.id_token(aud, force=force)
                            request.headers["Authorization"] = f"Bearer {id_tok}"
                        except Exception:
                            request.headers.pop("Authorization", None)
                        # ROOT-CAUSE PROBE: log what auth THIS request actually carries, so a
                        # 401 can be correlated to the exact token sent. Cloud Run rejects
                        # ('access token could not be verified') a token it treats as an ACCESS
                        # token — so if a 401'd request shows Authorization=ID here, the token is
                        # fine and the fault is transit/gateway; if it shows NONE or an access
                        # token, it's client-side. proxy_fp vs auth_fp being equal would mean the
                        # gateway's access token leaked into Authorization.
                        _auth = request.headers.get("Authorization", "")
                        _proxy = request.headers.get("Proxy-Authorization", "")
                        _atok = _auth[7:] if _auth.startswith("Bearer ") else ""
                        _ptok = _proxy[7:] if _proxy.startswith("Bearer ") else ""
                        import hashlib as _h
                        _fp = lambda t: _h.sha256(t.encode()).hexdigest()[:8] if t else "—"
                        print(f"[mcp-auth] {request.method} {host} "
                              f"Authorization=[{_peek_jwt(_atok) if _atok else 'NONE'} fp={_fp(_atok)}] "
                              f"Proxy-Auth fp={_fp(_ptok)} "
                              f"same_token={_atok == _ptok and bool(_atok)}", flush=True)
                    elif "mtls.googleapis.com" in host:
                        # Google API endpoint via mTLS subdomain/gateway egress
                        request.headers["Authorization"] = f"Bearer {access_tok}"
                    else:
                        request.headers.pop("Authorization", None)
                else:
                    # Direct Google API call: put the access token in Authorization.
                    request.headers["Authorization"] = f"Bearer {access_tok}"
            else:
                # Local fallback (laptop running cloud services):
                request.headers["Authorization"] = f"Bearer {token_for(url, force=force)}"
            # Propagate the W3C traceparent so the callee (MCP server / app task store) joins
            # THIS engine's trace — that is what lets the console's Agent Platform → Topology
            # page draw the agent→MCP edge (it "builds edges from cross-service trace
            # connections"; without it: "No recent trace connections detected"). The MCP servers
            # are OTel-instrumented (instrument_fastmcp) and will honour the parent. Mirrors
            # a2a_engine.py: gated on the SAME A2A_TRACE_PROPAGATION flag, and only when the
            # current context is valid AND sampled — a bare inject of an UNSAMPLED context makes
            # the callee drop its own spans (measured there: 68-span traces collapsed to 2).
            if os.environ.get("A2A_TRACE_PROPAGATION", "").lower() == "on":
                try:
                    from opentelemetry import trace as _ot
                    from opentelemetry.propagate import inject as _inject
                    _sc = _ot.get_current_span().get_span_context()
                    if _sc.is_valid and _sc.trace_flags.sampled:
                        _inject(request.headers)
                except Exception:  # noqa: BLE001 — tracing must never break the request
                    pass
            response = yield request
            if response.status_code != 401 or _attempt == 1:
                return
            print(f"[auth] 401 from {request.url.host} — forcing a fresh token, retrying once",
                  flush=True)


def maybe_auth() -> httpx.Auth | None:
    """Drop-in for httpx clients: `httpx.AsyncClient(auth=maybe_auth())`."""
    return None if run_local() else GoogleAuth()


def auth_headers(url: str) -> dict:
    """One-shot headers for short-lived connections (`streamablehttp_client(url, headers=…)`)."""
    if run_local():
        return {}
    parts = urlsplit(url)
    host = parts.hostname or ""
    if os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
        access_tok = _MINTER.access_token()
        if "googleapis.com" not in host or "mtls.googleapis.com" in host:
            hdrs = {"Proxy-Authorization": f"Bearer {access_tok}"}
            if "googleapis.com" not in host:
                try:
                    aud = f"{parts.scheme}://{host}"
                    id_tok = _MINTER.id_token(aud)
                    hdrs["Authorization"] = f"Bearer {id_tok}"
                except Exception:
                    pass
            elif "mtls.googleapis.com" in host:
                hdrs["Authorization"] = f"Bearer {access_tok}"
            return hdrs
        return {"Authorization": f"Bearer {access_tok}"}
    return {"Authorization": f"Bearer {token_for(url)}"}


def mcp_httpx_factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
    """`httpx_client_factory` for StreamableHTTPConnectionParams — every MCP
    connection the toolset opens carries per-request Google auth.

    ⚠️ Do NOT add `transport=httpx.AsyncHTTPTransport(retries=N)` here. It was tried as a
    hedge against the transient `ConnectionError: Failed to create MCP session` and it
    made things WORSE — MCP failures jumped ~12× per run (measured 2026-07-15: 1 failure
    across 2 runs without it vs 6 in one run with it). Transport-level retries do not play
    well with MCP streamable-HTTP's long-lived session (the retry re-opens connections
    underneath the session manager). The right place to harden this is the session
    lifecycle, not the socket.
    """
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
    """True when the A2A base points at a Vertex Agent Runtime engine.

    Must match BOTH host forms:
        us-central1-aiplatform.googleapis.com        (plain)
        us-central1-aiplatform.mtls.googleapis.com   (mtls — what *_A2A_URL now uses)

    The old check was `host.endswith("aiplatform.googleapis.com")`, which the mtls host
    FAILS (it ends in `mtls.googleapis.com`). That silently sent engine URLs down the
    non-engine branch of the app's readiness probe, which then did `GET {base}/healthz`
    on an engine that has no such route → `404 Not Found` and a UI that thinks every
    agent is dead.
    """
    host = urlsplit(base).hostname or ""
    return "aiplatform" in host and host.endswith("googleapis.com")


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

"""Direct REST/proto A2A client for Agent-Runtime engines (cloud).

Registry-based resolution (AgentRegistry.get_remote_a2a_agent) fails from a
GATEWAY-ATTACHED engine: it must call agentregistry.mtls to resolve, and that
outbound is gateway-filtered → 403 (agentregistry is the gateway's own
dependency; registering+granting it doesn't help). So instead we call the
target engine's A2A endpoint DIRECTLY:

    POST <engine_base>/a2a/v1/message:send   (proto-JSON body, ADC bearer)
    GET  <engine_base>/a2a/v1/tasks/{id}      (poll to completion)

This is INBOUND to the target engine (not gateway egress), so it works for any
caller with aiplatform access — the app SA and agent identities alike. The
gateway still governs the target engine's OWN outbound (agent→MCP tool policies),
which is the governance showcase.

`engine_base` is the reasoningEngine resource URL, e.g.
https://us-central1-aiplatform.googleapis.com/v1beta1/projects/…/reasoningEngines/ID
(the value already in BRAND_STYLE_A2A_URL etc.).
"""

import asyncio


async def a2a_engine_send(engine_base: str, text: str, timeout: float = 900.0) -> str:
    """Send one message to an engine's A2A endpoint and return the reply text.
    Runs SYNC requests in a worker thread — isolates the call from the ADK/OTel
    async context (contextvars Token errors) that break an in-node httpx client."""
    return await asyncio.to_thread(_send_sync, engine_base.rstrip("/"), text, timeout)


def _send_sync(base: str, text: str, timeout: float) -> str:
    import time as _time
    import google.auth
    import google.auth.transport.requests as _gar
    import requests

    import os

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

    # ⚠️ THE TOKEN EXPIRES MID-POLL ON LONG RUNS — REFRESH IT, DON'T MINT IT ONCE.
    #
    # This used to mint ONE token here and reuse it for the whole poll loop (which can run
    # for many minutes — a legal escalation is 8+ model calls). On Cloud Run the metadata
    # server returns a CACHED token carrying only its REMAINING lifetime, which can be a
    # couple of minutes rather than the full hour, so the header goes stale in flight and
    # the endpoint answers 401. `raise_for_status()` then killed the whole A2A call and the
    # console showed:
    #     HTTPError: 401 Client Error: Unauthorized for url: …/a2a/v1/tasks/{id}
    # It looked like an IAM problem for hours; it never was. The long paths (a legal run,
    # or a 7-minute ui_renderer poll) were simply the ones that outlived their token.
    def _headers() -> dict:
        """Fresh credential every time — cheap when the token is still valid (the library
        only hits the metadata server when it is close to expiry)."""
        if not creds.valid or creds.expiry is None:
            creds.refresh(_gar.Request())
        # TWO different parties need to authenticate this one request:
        #   Proxy-Authorization → the Agent Gateway (egress authorization, agent identity)
        #   Authorization       → the TARGET engine's aiplatform endpoint
        # This used to send ONLY Proxy-Authorization inside an engine, so Google's endpoint
        # saw no credential at all and answered 401 — which we spent a long time mistaking
        # for a missing client certificate.
        h = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
            "Connection": "close",
        }
        if os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
            h["Proxy-Authorization"] = f"Bearer {creds.token}"
        return h

    def _refresh() -> dict:
        """Force a new token (used when the target says 401 — i.e. ours just expired)."""
        creds.refresh(_gar.Request())
        return _headers()

    creds.refresh(_gar.Request())
    hdr = _headers()

    # TRACE CONTEXT IS PROPAGATED — but ONLY when it is valid AND sampled. See below.
    #
    # HISTORY (so nobody "fixes" this back): a first attempt injected the W3C `traceparent`
    # unconditionally (`opentelemetry.propagate.inject(hdr)`) and made tracing far WORSE —
    # the per-engine traces collapsed from 68 spans to 2-span fragments with no agent spans
    # at all. It was reverted as "propagation doesn't work here". That diagnosis was wrong.
    #
    # ROOT CAUSE (found by enabling it on orchestrator→brand_style alone and measuring):
    # a bare inject() propagates WHATEVER context is current — including an UNSAMPLED one
    # (`traceparent: …-00`). The callee honours that sampling flag and therefore DROPS
    # nearly all of its own spans. The parent was never the problem; the sampling bit was.
    #
    # With the guard (valid + sampled only), measured on one run:
    #   ONE trace · 63 spans · 5 services (orchestrator, brand_style, vendor_clearance,
    #   deal_pricing, MCP) · 56 agent spans — RICHER than the 32-agent-span best case when
    #   every engine traced itself in isolation. Nothing collapsed.
    # This is also what lets the console's Agent Platform → Topology page draw the mesh:
    # it builds edges from cross-service trace connections, and without propagation there
    # are none ("No recent trace connections detected").

    # We call the MTLS url (BRAND_STYLE_A2A_URL etc. point there) because the agent
    # endpoints are REGISTERED with it, and the gateway only authorizes the destination it
    # has registered: a call to the PLAIN host is refused with `403 Egress request is not
    # authorized` even when that URL is added as an interface AND the caller holds
    # iap.egressor on the endpoint (measured repeatedly — not a propagation delay).
    #
    # No client certificate is needed. The engine HAS one (google-auth's Device Certificate
    # Authentication source; ~1982B cert) and we briefly presented it — but a controlled
    # test with the cert disabled passed cleanly (0 × 401/403, downstream engines ran), so
    # the 401 we were chasing was purely the missing `Authorization` header above.
    # ── OPT-IN W3C trace propagation (A2A_TRACE_PROPAGATION=on) ──────────────────────
    # Without this every engine emits its OWN trace, so Cloud Trace has no cross-service
    # edges and the console's Agent Platform → Topology page says
    # "No recent trace connections detected".
    #
    # The last attempt at this collapsed the per-engine traces from 68 spans to 2-span
    # fragments. THE LIKELY REASON — and the reason for the guard below: a bare
    # `inject(hdr)` propagates whatever context is current, INCLUDING AN UNSAMPLED ONE
    # (`flags=00`). The callee honours that flag and drops nearly all of its own spans. So
    # only propagate a context that is BOTH valid AND sampled; otherwise send nothing and
    # let the callee start its own (fully sampled) trace, exactly as it does today.
    # Injected on the POST only — the task-poll GETs are plumbing and would just add noise.
    if os.environ.get("A2A_TRACE_PROPAGATION", "").lower() == "on":
        try:
            from opentelemetry import trace as _otel_trace
            from opentelemetry.propagate import inject as _otel_inject
            _ctx = _otel_trace.get_current_span().get_span_context()
            if _ctx.is_valid and _ctx.trace_flags.sampled:
                _otel_inject(hdr)
                print(f"[a2a] traceparent → {base.rsplit('/', 1)[-1]} "
                      f"trace={format(_ctx.trace_id, '032x')} (sampled)", flush=True)
            else:
                print(f"[a2a] NOT propagating: valid={_ctx.is_valid} "
                      f"sampled={bool(_ctx.trace_flags.sampled)} — the callee keeps its own "
                      f"trace (an unsampled parent would make it DROP its spans)", flush=True)
        except Exception as _e:  # noqa: BLE001 — tracing must never break the call
            print(f"[a2a] traceparent inject failed: {type(_e).__name__}: {_e}", flush=True)

    body = {"message": {"role": "ROLE_USER", "messageId": "vibeflix",
                        "content": [{"text": text}]}}
    url = f"{base}/a2a/v1/message:send"
    while True:
        with requests.Session() as s:
            r = s.post(url, json=body, headers=hdr, timeout=60, allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            url = r.headers["Location"]
            continue
        break
    if r.status_code >= 400:
        print(f"DEBUG: message:send failed status={r.status_code} body={r.text}", flush=True)
    r.raise_for_status()
    task = (r.json().get("task") or {})
    tid = task.get("id")
    state = (task.get("status") or {}).get("state")
    deadline = timeout
    _RUNNING = ("TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", None)

    # ── Polling: a 404 means "wrong replica", NOT "not ready" ────────────────────────
    # The engine runs ~6 replicas and its A2A task store is IN-MEMORY PER REPLICA. The
    # POST created the task on ONE replica; this GET is load-balanced independently, so
    # ~5 times in 6 it asks a replica that has never heard of the task and gets a 404.
    # Measured: 1,228 misses / 1,415 polls = 86.8% (predicted 5/6 = 83.3%).
    #
    # The old loop SLEPT on a miss — sleep(2) here plus sleep(5) at the top of the loop,
    # so every miss burned 7s. That was ~64% of each agent's runtime (deal_pricing: 147s
    # of a 230s run), it produced the ~1,900 "error" spans that swamped Cloud Trace, and
    # it left the console's chat blocked for 7 MINUTES behind a form-designer task.
    #
    # A miss is not a reason to wait — RE-ISSUING the GET re-rolls the load balancer, so
    # just probe again immediately: with R replicas, P(missing M in a row) = ((R-1)/R)^M,
    # which at R=6 is ~2.6% after 20 probes and takes ~1s instead of 140s.
    #
    # And a 404 is AMBIGUOUS: it also means "this task is GONE" (its replica was replaced
    # — e.g. the engine was redeployed mid-run, which wipes the in-memory store). The old
    # loop could not tell the two apart and assumed "retry forever", so a destroyed task
    # HUNG until the 900–1800s timeout instead of failing. Consecutive misses are now
    # bounded: probe fast, then slowly, then declare the task gone with a real error.
    #
    # ⚠️ A 404 NEVER PROVES THE TASK IS GONE once we have seen it alive. The misses are
    # NOT independent coin flips: the replica that owns the task is the one BUSY EXECUTING
    # it (WEB_CONCURRENCY=1 — a single worker per replica), so the load balancer routes
    # away from precisely the replica we need. Measured on a healthy run: the first GET
    # hit the owning replica [17] and returned 200, and then 73 consecutive GETs landed on
    # [19]/[22] and 404'd — while the orchestrator carried on working (recovery →
    # compile_ui → generate_report). An earlier version of this loop concluded "task gone"
    # after 60s of misses and ABANDONED that healthy run. Never again:
    #   • seen_ok (we ever got a 200)  → the task EXISTS. Poll to the deadline, never quit.
    #   • never seen it at all         → it may genuinely not exist (its replica was
    #                                     replaced, e.g. the engine was redeployed mid-run);
    #                                     only THEN give up early, with a clear error.
    _FAST_PROBES = 20      # ~1s — resolves an honest round-robin miss
    _FAST_PAUSE = 0.05
    _SLOW_PAUSE = 1.0      # then back off; ~1 req/s is gentle and keeps re-rolling the LB
    _UNSEEN_GRACE = 60.0   # give-up budget — ONLY while the task has never been seen
    # Pause between polls of a task that is genuinely still WORKING. This was 5s, but a
    # trace of a healthy run showed 61% of the wall-clock (73.6s of 121s) is idle — the
    # orchestrator sleeping AFTER a sub-agent has already finished, repeated across ~6–8
    # sequential A2A hops. The shared RemoteTaskStore made every poll a 200 (measured
    # 49/49; the old 404 storm that justified a long sleep is gone), so polling ~1/s is
    # cheap and reclaims most of that idle time. Keep ≥ ~0.5s so a burst of hops can't
    # hammer the app store.
    _WORK_PAUSE = 1.0
    miss_since = None      # monotonic ts of the first miss in the current streak
    misses = 0
    seen_ok = False        # have we EVER successfully read this task?
    auth_retries = 0       # 401/403 → our token expired mid-poll; refresh and carry on

    while tid and state in _RUNNING and deadline > 0:
        # Manually follow redirects for GET to keep auth headers
        url = f"{base}/a2a/v1/tasks/{tid}"
        params = {"history_length": 50}
        while True:
            with requests.Session() as s:
                g = s.get(url, params=params, headers=hdr, timeout=60, allow_redirects=False)
            if g.status_code in (301, 302, 303, 307, 308):
                url = g.headers["Location"]
                params = None  # query parameters are already in the redirect URL
                continue
            break

        # 401/403 = OUR TOKEN EXPIRED, not a permissions problem. The metadata server hands
        # out a cached token with only its remaining lifetime, so a long poll (a legal
        # escalation runs many minutes) outlives it. Mint a new one and keep polling —
        # letting this raise used to kill the whole audit with a bogus "Unauthorized".
        if g.status_code in (401, 403) and auth_retries < 5:
            auth_retries += 1
            hdr = _refresh()
            _time.sleep(1); deadline -= 1
            continue

        # 400 during a run is the platform surfacing an in-progress execution error;
        # treat it like a miss and keep polling until the task reaches a terminal state
        # (FAILED), which we then report — don't silently drop it.
        if g.status_code in (400, 404):
            now = _time.monotonic()
            if miss_since is None:
                miss_since, misses = now, 0
            misses += 1
            # Give up ONLY if this task has NEVER been read successfully. If we have seen
            # it even once, it EXISTS and is running on a replica we simply cannot get
            # routed to — keep polling until the caller's own timeout. Quitting here on a
            # live task is exactly the bug this replaced: it abandoned healthy runs and,
            # inside the orchestrator, made `recovery` re-run agents that were still fine.
            if not seen_ok and now - miss_since > _UNSEEN_GRACE:
                return (f"[A2A engine execution FAILED] task {tid} was never readable on any "
                        f"replica in {_UNSEEN_GRACE:.0f}s ({misses} consecutive "
                        f"{g.status_code}s) — it was never observed alive, so the replica "
                        f"that created it is most likely gone (engine redeployed/restarted).")
            pause = _FAST_PAUSE if misses <= _FAST_PROBES else _SLOW_PAUSE
            _time.sleep(pause); deadline -= pause
            continue

        miss_since, misses = None, 0        # found the owning replica
        seen_ok = True                      # …and it's alive: never declare it gone again
        g.raise_for_status()
        task = g.json()
        state = (task.get("status") or {}).get("state")
        if state in _RUNNING:
            # Genuinely still working — THIS is the only case that deserves a wait.
            _time.sleep(_WORK_PAUSE); deadline -= _WORK_PAUSE
    if state == "TASK_STATE_FAILED":
        return f"[A2A engine execution FAILED] {_status_error(task) or '(no detail)'}"
    return _extract_reply(task)


def _status_error(task: dict) -> str:
    """Any error/message text a FAILED task carries in its status."""
    st = (task.get("status") or {})
    msg = st.get("message") or {}
    parts = msg.get("content") or msg.get("parts") or []
    txt = "".join(p.get("text", "") for p in parts).strip()
    return txt or (st.get("error") or {}).get("message", "") or st.get("state", "")


def _extract_reply(task: dict) -> str:
    """Pull the agent's reply text out of an A2A task (proto shape)."""
    for art in (task.get("artifacts") or []):
        for p in (art.get("parts") or []):
            if p.get("text"):
                return p["text"]
    # else the last non-user message in history
    for msg in reversed(task.get("history") or []):
        if msg.get("role") in ("ROLE_AGENT", "agent"):
            return "".join(p.get("text", "") for p in (msg.get("content") or msg.get("parts") or []))
    st = (task.get("status") or {}).get("message") or {}
    return "".join(p.get("text", "") for p in (st.get("content") or []))


def direct_engine_agent(name: str, description: str, engine_base: str):
    """A BaseAgent that runs a2a_engine_send and emits the reply as its event —
    so the orchestrator workflow can `ctx.run_node()` it exactly like a
    RemoteA2aAgent, but via the direct (gateway-free) path."""
    from google.adk.agents import BaseAgent
    from google.adk.events.event import Event
    from google.genai import types as _t

    class _DirectEngineAgent(BaseAgent):
        async def _run_async_impl(self, ctx):
            text = ""
            if ctx.user_content and ctx.user_content.parts:
                text = "".join(getattr(p, "text", "") or "" for p in ctx.user_content.parts)
            if not text:
                for ev in reversed(ctx.session.events):
                    c = getattr(ev, "content", None)
                    if c and getattr(c, "parts", None):
                        t = "".join(getattr(p, "text", "") or "" for p in c.parts)
                        if t and "__plan__" not in t:
                            text = t
                            break
            # NESTED WAITS — the outer deadline must OUTLIVE the inner one.
            # orchestrator ──(this call)──► vendor_clearance ──► legal (Q&A round-trip)
            # vendor_clearance's own call to legal uses the 900s default, so a caller
            # waiting on vendor_clearance must wait longer than that or it gives up while
            # the callee is still working — and `_extract_reply` then returns "" on an
            # unfinished task, which surfaces as a BLANK audit even though the work
            # completed server-side. (That is exactly what we hit: legal ran fine, the
            # orchestrator had already stopped listening.)
            reply = await a2a_engine_send(engine_base, text, timeout=1800.0)
            yield Event(author=self.name,
                        content=_t.Content(role="model", parts=[_t.Part(text=reply)]))

    return _DirectEngineAgent(name=name, description=description)

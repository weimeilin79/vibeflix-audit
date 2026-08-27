# Upstream Bug Report — intermittent mTLS handshake failures to `*-aiplatform.mtls.googleapis.com` from an agent-identity engine

**For:** Vertex AI Agent Engine / Agent Runtime team, and the `google-auth` maintainers
**Filed by:** vibeflix-audit (production ADK multi-agent mesh on Agent Engine)
**Date:** 2026-08-26, updated 2026-08-27
**Status:** OPEN. Observed continuously over four days in `vibeflix-demo`, us-central1.
**2026-08-27 update:** added per-credential evidence that the same valid token both succeeds and is
refused on the same endpoint (so the variable is the connection, not the credential), and a
client-side mechanism read from the `google-auth` source — an uncached, non-atomic certificate read
performed on every call. See *The same token...* and *Where the flakiness comes from*.
**Severity:** High — an agent fails mid-run with no actionable error; the surfaced exception
names JSON parsing, not TLS, so every user will debug the wrong layer first.

---

## Summary

An engine deployed with `identity_type=AGENT_IDENTITY` mints **certificate-bound** tokens, which
must travel over mutual TLS. Those mTLS connections to `us-central1-aiplatform.mtls.googleapis.com`
**intermittently fail the TLS handshake**, and the failure is not surfaced as a TLS error to the
caller. It reaches application code as a JSON parsing error against an empty body.

Two distinct call paths are affected, both of which the platform requires:

1. **`iamcredentials` impersonation** — an agent identity has no service account, so an
   audience-bound ID token for a Cloud Run backend can only be obtained by impersonating one.
   `google.auth.impersonated_credentials.IDTokenCredentials.refresh()` calls
   `authed_session.configure_mtls_channel()` unconditionally, so this rides mTLS.
2. **The session service** — `.../reasoningEngines/<id>/sessions/...` on the same mTLS host.

---

## Affected versions

| component | version |
|---|---|
| google-adk | 2.3.0 |
| google-auth | 2.56.3 |
| google-cloud-aiplatform | 1.164.0 |
| a2a-sdk | 0.3.26 |
| Python | 3.13 (Agent Engine runtime) |
| runtime | Vertex AI Agent Engine, us-central1, `identity_type=AGENT_IDENTITY` |
| env | `GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=true`; `USE_CLIENT_CERTIFICATE` and `USE_MTLS_ENDPOINT` unset (library defaults) |

---

## What we observe

```
requests.exceptions.SSLError: HTTPSConnectionPool(host='us-central1-aiplatform.mtls.googleapis.com',
  port=443): Max retries exceeded with url: /v1beta1/projects/<n>/locations/us-central1/reasoningEngines/<id>/...
SSLError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] ssl/tls alert handshake failure
INFO: Retrying due to aiohttp error: Failed to send request to https://us-central1-aiplatform.mtls.googleapis.com/...
ERROR: Unclosed client session
```

Rate, one project, six engines, ordinary demo traffic:

| hour (UTC) | transport failures |
|---|---|
| 12:00 | 30 |
| 13:00 | 16 |
| 14:00 | 39 |

All six engines are affected.

### The failure is per-CONNECTION, not per-certificate

Failure timestamps within a single engine, over 4.5 hours of ordinary traffic:

```
deal_pricing   12:10:28  12:12:30  12:36:38  13:11:22  14:03:56  14:27:51  14:37:23  14:46:27
ui_renderer    12:06:56 12:07:07 12:07:19 | 12:11:17 12:11:21 12:11:35 | 12:13:17 12:13:30 12:13:41 12:13:50
```

Two things follow, and together they narrow the cause considerably.

**Certificate rotation is ruled out.** `deal_pricing` fails once here and once there across four
and a half hours, with successful traffic in between. A rotated-out or expired client certificate
would fail *every* connection from that engine until it refreshed.

**Concurrency is implicated.** `ui_renderer` fails in tight bursts — three within 23s, three within
18s, four within 33s — which is the shape you get when several connections are created at the same
moment and some of them lose. Between bursts it succeeds normally.

### The same token, on the same endpoint, both succeeds and fails

Measured 2026-08-27, one engine (`vendor_clearance`), one task, one two-minute window. Every
outbound call logs the fingerprint and remaining life of the token it carries, so successes and
failures can be attributed to a specific credential:

| Proxy-Authorization fp | status | count | exp_in at call time |
|---|---|---|---|
| `c39ac628` | 200 | 43 | 974..1072s |
| `c39ac628` | 401 | 32 | 974..1072s |

One credential, 16-18 minutes of life left, 43 accepted and 32 refused — interleaved, same process,
same URL. This rules out the whole class of credential explanations: expiry, staleness, a frozen or
shared token, a key mismatch, a stale revision. What differed between an accepted call and a
refused one was the connection it travelled on.

The 401s carry the IAP body `Error code 1000`, which is what a certificate-BOUND token gets when it
arrives on a connection that is not carrying the certificate its binding names. So the refusals are
the same underlying event as the `SSLV3_ALERT_HANDSHAKE_FAILURE` above, seen from the other side:
sometimes the handshake fails outright, sometimes it completes without the client certificate and
the request is refused on arrival.

The agents that fail most are simply the ones that open the most connections: `ui_renderer` (called
repeatedly by the app) and `vendor_clearance` (two MCP servers, an A2A handoff to another engine,
plus session traffic, over the longest run). At a few-percent per-connection failure rate, the
heaviest caller loses most often. That is consistent with an SSL-context reuse fault on the client
side rather than anything about the certificate itself.

---

## Why we hit this so often (and why others may not)

Our A2A client polled `GET .../a2a/v1/tasks/{id}` once per second, opening a **new
`requests.Session` per poll** — a fresh mTLS connection, and therefore a fresh handshake, every
second per in-flight hop. A 200s audit with three specialists was performing several hundred
handshakes. At a few-percent per-connection failure rate, losing one stops being bad luck and
becomes arithmetic.

We have since hoisted the session out of the poll loop so a hop pays one handshake instead of one
per second. That is a mitigation, not a fix: the handshake still fails at the same rate, we are
simply exposed to it far less often. It also means the underlying rate is likely under-reported by
callers who already reuse connections.

---

## Where the flakiness comes from — the client-side mechanism

Read from the installed `google-auth` **2.55.2** source. The engine runs **2.56.3**; these functions
should be confirmed unchanged there before acting on this section.

**Every call re-reads the certificate and rebuilds the SSL context.** There is no cache:

```python
# google/auth/transport/requests.py — AuthorizedSession.configure_mtls_channel
use_client_cert = _mtls_helper.check_use_client_cert()
if not use_client_cert:
    return
is_mtls, cert, key = _mtls_helper.get_client_cert_and_key(client_cert_callback)
if is_mtls:
    new_adapter = _MutualTlsAdapter(cert, key)      # fresh SSL context, every time
```

`IDTokenCredentials.refresh()` calls `configure_mtls_channel()` unconditionally, so every ID-token
mint performs a fresh filesystem read plus a fresh handshake. Exposure is therefore proportional to
connection count, which is exactly what the failure distribution shows.

**The certificate and key are read non-atomically, and never checked against each other:**

```python
# google/auth/transport/_mtls_helper.py
def _read_cert_and_key_files(cert_path, key_path):
    cert_data = _read_cert_file(cert_path)   # open + read file A
    key_data  = _read_key_file(key_path)     # open + read file B, separately
    return cert_data, key_data
```

Each helper independently `open()`s its file and regex-matches a single PEM block. Nothing
synchronises the two reads, and nothing verifies that the private key corresponds to the
certificate.

The files are a SPIFFE workload credential that the platform rotates underneath the process:

```
/var/run/secrets/workload-spiffe-credentials/certificates.pem
/var/run/secrets/workload-spiffe-credentials/private_key.pem
```

The library's own comment above these constants reads *"Temporary patch to accomodate incorrect cert
config in Cloud Run prod environment"*, so this path is already known to be unsettled.

### Two candidate causes, and which the evidence favours

**A torn read racing a rotation.** If a rotation lands between the two `open()` calls, the client
gets cert generation N with key generation N+1, presents a certificate it cannot prove possession
of, and the server aborts with `SSLV3_ALERT_HANDSHAKE_FAILURE` — precisely the observed error.
Against it: the bursts are 2-6 minutes apart, and workload certificates do not rotate on that
cadence. This looks too rare to account for the observed rate on its own.

**A concurrency fault in per-connection SSL context creation.** Three failures in 23s, three in 18s,
four in 33s, with clean traffic between, tracks parallel fan-out rather than any rotation clock.
This also matches the `pyOpenSSL` *"Context has already been used to create a Connection"* failure
mode we hit when forcing mTLS on every client in the process.

The burst cadence favours the second. The two are not exclusive — concurrent reads of a rotating
file would produce both shapes — and separating them needs either a packet capture from inside the
engine or the server's view of the rejected handshakes. An Agent Engine exposes only its A2A class
methods, so we cannot run a probe inside one to settle it. That is why ask #2 below matters.

---

## The reporting defect, which is the expensive part

When the handshake fails there is no HTTP response, so the body is empty. `google-auth` then calls
`.json()` on it without checking that a response arrived, and the caller receives:

```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

`char 0` means an empty string. Nothing in that message mentions TLS, mTLS, the certificate, or the
connection. We spent two days treating it as a malformed-response problem — including removing the
`configure_mtls_channel()` call, which is *required* for bound tokens and made every mint fail with
`401 ... Error code 1000` — before the underlying `SSLError` surfaced in the logs and identified the
real layer.

**Ask:** check whether a response was received before parsing it, and propagate the transport error.
A `TransportError` naming the host and the handshake would have made this a ten-minute diagnosis.

---

## Downstream impact in a real mesh

The ID-token mint failing means the code falls back to a non-audience-bound ADC token, which Cloud
Run rejects with 401. Anything that then treats a 401 as "not found" — for example an A2A task
store falling back to per-replica memory — turns a transport blip into a multi-minute stall with no
error visible anywhere. Measured at peak: **137 of 183 mints failed in one hour**, and audits that
normally complete in 80–120s ran past 300s and were cut by the Cloud Run request timeout.

---

## What we would like

1. **Surface transport failures as transport failures.** Do not parse a body that never arrived.
2. **Explain why the handshake is failing**, or make the mTLS client resilient to it. Three
   concrete changes would each help independently:
   - **Read the certificate and key atomically, and validate the pair.** Two unsynchronised
     `open()` calls against files a rotation agent rewrites can yield a mismatched pair, and
     nothing currently detects it. Checking that the key matches the certificate before building
     the adapter would convert a confusing TLS alert into a clear, retryable local error.
   - **Cache the client certificate and the SSL context.** `configure_mtls_channel()` re-reads
     from disk and rebuilds the context on every call, so exposure scales with connection count
     for no benefit. A cache invalidated on file mtime would remove most of it.
   - **Make concurrent context creation safe**, if that is the cause (cf. the `pyOpenSSL`
     "Context has already been used to create a Connection" failure mode we hit when forcing mTLS
     on every client in the process).
3. **Let an agent identity mint an audience-bound ID token directly.** The whole impersonation
   detour — and its exposure to this bug — exists only because it cannot.

---

## Workaround in place

Every mitigation below reduces how often we are exposed. None of them makes an individual
handshake more reliable, because nothing on the client side can.

**Mint fewer tokens.** We removed every ID-token mint that was not actually required. Our console
app is deployed `--allow-unauthenticated` and gates its task-store endpoints with a shared secret
header, so the audience-bound token being minted for it was never checked by anything. Skipping it
eliminated **~99% of the exposed calls** (198 of 200 failing mints targeted that one host) and
returned audits to their normal duration.

**Open fewer connections.** Three call paths each built a new client per operation, so every call
re-rolled the handshake:

| path | before | after |
|---|---|---|
| A2A task poll (`a2a/engine.py`) | `requests.Session()` per poll, ~1/s per hop | one session per poll loop |
| A2A task store (`a2a/task_store.py`) | new `httpx.AsyncClient` per op — measured 12 calls, 12 connections | one pooled client — 12 calls, 1 connection |
| `message:send` (`a2a/engine.py`) | new session per send, no auth retry | retries 401/403 up to 5x on a fresh connection |

The poll-loop change alone took one engine from 39 handshake failures in an hour to 1.

**Retry the refusals, and throw away the bad connection.** A 401 on a bound token is usually the
connection rather than the credential, so the task store now drops its pooled client on an auth
refusal and re-handshakes rather than reusing a connection that is already being rejected. Pooling
without this would have converted an intermittent 401 into a permanent one.

The `message:send` gap was the most damaging in practice: it went straight to `raise_for_status()`,
so a single bad handshake failed the whole hop. For a one-shot send — our `contract_finalize` step —
that made writing the contract a coin flip, and produced fully-passing audits that executed no
contract at all.

The remaining exposure is the session service, which cannot be avoided, and which still fails at the
rate in the table above.

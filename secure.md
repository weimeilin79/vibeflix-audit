# secure.md — how every hop authenticates

Every network hop is plain HTTP locally and credentialed in the cloud. This describes the
**mechanism**, which is stable. It used to be a "files changed" list, and that rotted: it claimed
`run_local()` was *"local-safe default"* (it auto-detects — on GCP auth is ON), and that the
credential source in cloud is a *"service account / metadata server"* — which is **precisely what
an agent-identity engine does not have**.

Operational rules: **[`deploy/GOTCHAS.md`](deploy/GOTCHAS.md)** · who may call whom:
**[`topology.md`](topology.md)**.

---

## 1. Local vs cloud is AUTO-DETECTED

`vibeflix_common/cloud_auth.py` → `run_local()`:

| `RUN_LOCAL` | behaviour |
|---|---|
| **unset (normal)** | **auto-detect** — on GCP (`K_SERVICE`, or the metadata server, which only resolves inside GCP) → credentials **ON**; anywhere else → local, no credentials |
| `true` / `1` / `yes` | force local (no auth) **even on GCP** |
| `false` / `0` / `no` | force cloud auth **even off GCP** (laptop → cloud MCPs) |

Detected once per process and cached. Compose pins `RUN_LOCAL=true` and the cloud scripts pin
`RUN_LOCAL=false` — both belt-and-braces, not required.

## 2. The engines have NO service account

Each engine runs `identity_type=AGENT_IDENTITY` and executes as
`principal://…/reasoningEngines/<ID>`. **There is no service account behind the metadata
server**, so `fetch_id_token()` cannot work — and the gateway does **not** inject a credential for
you (no invoker-SA field exists on `agentToAnywhereConfig`, on the registry Service, or in
gcloud).

Cloud Run accepts **only** an audience-bound OIDC **ID token**. Measured against the MCP servers:

| the engine sends | Cloud Run answers |
|---|---|
| an **access** token | **401** — "the access token could not be verified" |
| an audience-bound **ID** token | **200** |
| nothing | **403** |

So the engine **mints one by impersonating `MCP_INVOKER_SA`**
(`cloud_auth._id_token_via_impersonation` → `impersonated_credentials.IDTokenCredentials`,
`target_audience="scheme://host"`) — exactly what the Agent Gateway codelab's `--mcp-invoker-sa`
does (it only injects that env var).

Three things are required; miss one and **every MCP call 401s**
([G9](deploy/GOTCHAS.md#g9--an-agent_identity-engine-has-no-service-account)):

1. `MCP_INVOKER_SA` on the engine,
2. `roles/iam.serviceAccountTokenCreator` for each **agent principal** on that SA,
3. `roles/iap.egressor` on `gcp-iamcredentials*` — the gateway is default-deny, so **even the
   token-minting call must be allowlisted**.

## 3. TWO headers, TWO different parties

`cloud_auth.GoogleAuth` (an `httpx.Auth` hook) attaches credentials per request. Inside a
gateway-attached engine, one call carries **two**:

| header | read by | contains |
|---|---|---|
| `Proxy-Authorization` | **the Agent Gateway** — authorizes the *egress* | the engine's access token (its agent identity) |
| `Authorization` | **the destination** — authenticates you *to it* | Cloud Run / the app → an audience-bound **ID token** (§2); a Google API → the access token |

> ⚠️ **The gateway authorizes egress. It never signs your request to the backend.** Believing
> otherwise cost days. It also gives you a distance signal: **403** = the gateway refused (the
> call never left); **401** = the gateway allowed it and the *target* refused you.

Sending only `Proxy-Authorization` was a real bug: Google's endpoint saw no credential and
answered 401, which we long mistook for a missing client certificate.

## 4. Two A2A hosts — the app and the engines differ

[G11](deploy/GOTCHAS.md#g11--two-a2a-hosts--the-app-and-the-engines-do-not-use-the-same-one).
**Engines** call the **mTLS** aiplatform host — the URL the Agent Registry registered; a
plain-host call is refused `403 Egress request is not authorized`. **The app** is a plain SA with
no client cert, so it must call the **plain** host — mTLS would demand a cert it doesn't have and
answer **401**.

No client certificate is needed by our code. We presented one for a while, then proved by
controlled test (`cert=None` → zero 401/403) that the missing `Authorization` header had been the
entire bug. The cert plumbing was deleted.

## 5. Token lifetime — refresh, don't mint once

Tokens are attached **per request** and re-minted before expiry. That matters more than it
sounds: on Cloud Run the metadata server hands back a **cached** token carrying only its
*remaining* lifetime, which can be minutes rather than an hour. A long A2A poll (a legal
escalation runs many minutes) therefore **outlives a token minted once at the start**, and the
endpoint answers `401` mid-run. `a2a_engine._send_sync` refreshes the credential per request and
treats a `401/403` as *refresh and retry*, not as fatal.

## 6. The app's own credentials

The console app is a **plain Cloud Run service account** (`vibeflix-app`), not an agent identity.
It needs `roles/aiplatform.user` **and `roles/aiplatform.agentContextEditor`** — the second is
easy to miss and its absence is baffling: `POST message:send` succeeds, then every
`GET /a2a/v1/tasks/{id}` 401s, so the fast agent appears to finish while the slow ones **hang
forever** ([G12](deploy/GOTCHAS.md#g12--rolesaiplatformagentcontexteditor-is-required--and-easy-to-forget)).

The app is `--allow-unauthenticated` (the browser must load the console), so **anyone with the URL
can run an audit**. Its shared-task-store endpoints therefore carry their own secret
(`TASK_STORE_KEY` / `X-Task-Store-Key`) — otherwise the agents' A2A task state would be
world-readable and world-writable. Cloud Run IAM can't do this job: locking the service down
locks out the frontend.

## 7. What the gateway can and cannot govern

**HTTP egress only.** It cannot match a gRPC channel or a raw TCP socket to a registered endpoint
([G8](deploy/GOTCHAS.md#g8--the-agent-gateway-governs-http-egress-only)) — which is why mesh
telemetry publishes over Pub/Sub **REST**, and why Cloud SQL and Redis are unusable as an A2A
task store.

**Ingress is not governed at all**: IAM is not enforced and IAP is not supported during
client-to-agent ingress, which can only cover `query`/`streamQuery` — methods these
`a2a_extension` engines don't even expose. The app→engine hop is authorized by the app's own
project IAM on a direct A2A call.

---

```bash
./deploy/verify_deployment.sh 4s    # every principal, SA and role — 29 checks
```

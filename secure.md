# secure.md — token & authentication changes (RUN_LOCAL gate)

Every network hop in the mesh is plain http locally but IAM-gated in the cloud.
This document lists **exactly which files changed** to attach Google credentials,
and how the mechanism works. Everything is gated by one env var:

| `RUN_LOCAL` | Behavior |
|---|---|
| `true` **or unset (default)** | No credentials attached anywhere — identical to the original local behavior |
| `false` | Every MCP + A2A call carries a fresh Google token, minted per request |

Token choice is automatic, by destination host:

- `*.googleapis.com` (Agent Runtime A2A endpoints) → **OAuth access token** (`ya29.…`, cloud-platform scope)
- everything else (`*.run.app` MCP services, Agent Gateway domains) → **OIDC ID token** (JWT, audience = `scheme://host`)

Tokens are cached ~45 min and re-minted before expiry, attached **per request** —
a process that lives for days never holds a stale credential. Credential source is
ADC: service account / metadata server in the cloud, your `gcloud auth
application-default login` user locally (its refresh carries an `id_token`).

---

## Files changed

### 1. `packages/vibeflix-common/vibeflix_common/cloud_auth.py` — NEW (the whole mechanism)

| Helper | Purpose |
|---|---|
| `run_local()` | Reads `RUN_LOCAL`; only `false/0/no` enables auth (local-safe default) |
| `_TokenMinter` | Lazy ADC credentials; one access token + per-audience ID-token cache (thread-safe) |
| `token_for(url)` | Picks access vs ID token by host |
| `GoogleAuth` | `httpx.Auth` hook — injects `Authorization: Bearer <fresh token>` on every request (sync + async) |
| `maybe_auth()` | `None` locally, `GoogleAuth()` in the cloud — drop-in for `httpx.AsyncClient(auth=…)` |
| `auth_headers(url)` | One-shot headers for short-lived `streamablehttp_client` connections |
| `mcp_httpx_factory` | `httpx_client_factory` for ADK MCP connections — every connection the toolset opens is authed |
| `a2a_httpx_client()` | Long-lived authed client for `RemoteA2aAgent(httpx_client=…)`; `None` locally |

### 2. `packages/vibeflix-common/vibeflix_common/mcp_clients.py` — agents → MCP

`mcp_toolset()` builds `StreamableHTTPConnectionParams(url, httpx_client_factory=mcp_httpx_factory)`
when `RUN_LOCAL=false` (plain params locally). Covers every agent-side MCP toolset:
brand_style, vendor_clearance, deal_pricing, legal, and the orchestrator's
note_responder tools.

### 3. `agents/orchestrator/agent.py` — orchestrator's A2A calls

- `_remote_agent()` passes `httpx_client=a2a_httpx_client()` into each
  `RemoteA2aAgent` (brand_style / vendor_clearance / deal_pricing) when cloud.
- `_a2a_send()` (the contract-finalize fresh-context call to vendor_clearance):
  `httpx.AsyncClient(timeout=…, auth=maybe_auth())`.

### 4. `agents/vendor_clearance/agent.py` — the legal hand-off

- `_call_legal()`: `httpx.AsyncClient(timeout=300, auth=maybe_auth())`.

### 5. `agents/app.py` — the console's own network calls (7 sites)

- Import of `a2a_httpx_client, auth_headers, maybe_auth`.
- **5 MCP sites**, each now `streamablehttp_client(url, headers=auth_headers(url))`
  (one-shot connections → fresh header per call):
  1. trademark-picker load (`list_trademarks` at startup)
  2. `_licensing_call()` (shared helper: `get_contract`, `dump_stores`, volume annotation)
  3. `_annotate_contract_volume()` fallback path
  4. `/api/reset` (`reset_vendors`)
  5. `/api/mcp/tools` inventory (Workflow-graph tool list)
- Presenter `RemoteA2aAgent` (ui_renderer): `httpx_client=a2a_httpx_client()` when cloud.
- Readiness probes (`/api/ready` agent-card + MCP health checks):
  `httpx.AsyncClient(timeout=6.0, auth=maybe_auth())`.

### 6. `docker-compose.yml` — local default made explicit

`x-vertex-env` anchor sets `RUN_LOCAL: "true"` with a comment pointing at this
mechanism (defensive — unset already means local).

### 7. `deploy/deploy_agents.sh` — cloud engines get auth ON

`COMMON` env string starts with `RUN_LOCAL=false,…` so every Agent Runtime
engine deploys with auth enabled.

### 8. `deploy/instruction-sre.md` + `deploy/instruction-dev.md`

The app `gcloud run deploy --set-env-vars` lists and the agent-deploy `COMMON`
example now lead with `RUN_LOCAL=false`.

---

## The resulting auth flow (cloud)

```
orchestrator/app ──A2A──► Agent Runtime engines      Bearer <access token ya29.…>
agents / app     ──MCP──► Agent Gateway / Cloud Run  Bearer <ID token, aud=service origin>
   (gateway then re-authenticates to the backend Cloud Run MCP with ITS OWN OIDC token —
    agents never hold per-MCP credentials; policies.yaml decides who may call which tool)
```

## What this does NOT change

- **Server-side IAM** is unchanged and still required: callers need
  `roles/run.invoker` (MCPs) / `roles/aiplatform.user` (engines) — the tokens
  only prove identity; IAM + gateway policies authorize.
- No secrets, keys, or tokens are stored anywhere — everything is minted from
  ADC at runtime.
- Local development: zero change (verified — full audit passes with the code in
  place, `RUN_LOCAL` unset).

## Verification record (2026-07-08)

- `RUN_LOCAL` unset → `maybe_auth() is None`, `auth_headers() == {}`; full local
  audit: brand_style `compliant`, clearance `cleared`, pricing `cleared`,
  contract `LC-415264` executed.
- `RUN_LOCAL=false` on user ADC → real OIDC JWT minted for a `run.app` audience,
  real `ya29.` access token for `googleapis.com`, `McpToolset` constructed with
  the authed factory.

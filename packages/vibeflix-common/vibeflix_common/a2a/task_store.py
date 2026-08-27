"""ONE A2A task store for the whole engine fleet (instead of one per replica).

THE PROBLEM THIS SOLVES
-----------------------
Agent Runtime runs each engine as SEVERAL replicas behind a load balancer with no
session affinity, and the A2A server's default store is `InMemoryTaskStore` — a plain
dict, private to one replica. So:

    POST /a2a/v1/message:send   → creates the task on replica [17]
    GET  /a2a/v1/tasks/{id}     → load-balanced to [19] or [22] → 404 Task not found

Measured on a real run: 1,228 misses / 1,415 polls (86.8%). And the miss is not even a
fair coin — the replica that OWNS the task is the one busy executing it, so the balancer
routes away from precisely the replica we need. One healthy run polled 73 times without
ever getting back to the owning replica while it happily kept working.

Everything we chased today came out of that single fact:
  • runs took ~5 min, of which ~2.5 min was the client losing coin flips;
  • ~1,900 "error" spans (26% of ALL spans) — every one a 404 poll;
  • the console's chat blocked for 7 minutes behind a ui_renderer form-designer task;
  • `recovery` re-ran agents that had never actually failed.

THE FIX
-------
Keep the tasks OUTSIDE the replicas. `vertexai`'s A2aAgent template accepts a
`task_store_builder` (templates/a2a.py: it falls back to InMemoryTaskStore only when
none is given), so every engine can share one store and ANY replica can serve ANY task.

WHY THE STORE LIVES BEHIND THE APP (and not in Firestore / Cloud SQL / Redis)
-----------------------------------------------------------------------------
The Agent Gateway (AGENT_TO_ANYWHERE) governs **HTTP** egress and cannot match a gRPC
channel or a raw TCP socket to a registered endpoint — that is exactly why the Pub/Sub
gRPC publisher was refused with `403 Egress request is not authorized` and had to be
rewritten over REST. So:
  • Cloud SQL / Postgres (the SDK's own DatabaseTaskStore) → TCP → the gateway can't
    govern it, and it would need VPC/PSC plumbing that cuts against the gateway demo.
  • Memorystore / Redis → TCP → same wall, plus a VPC connector the app doesn't have.
  • Firestore → HTTPS, so it WOULD pass — but A2A saves the task on every event, and
    Firestore's sustained write limit is ~1/sec on the SAME document.
    UPDATE: the app now DOES back its `/api/taskstore` endpoints with Firestore
    (collection `a2a_tasks`), trading hot-path latency for durability — the ~1/sec hot-doc
    ceiling is absorbed by the terminal-write retries below. This engine-side client is
    unchanged: it still speaks plain HTTPS to the app, which owns the Firestore write.
  • The app → plain HTTPS to a Cloud Run service. The engines ALREADY reach Cloud Run
    this way (that is how they call the MCP servers), so the whole auth story is solved:
    `GoogleAuth` attaches Proxy-Authorization (for the gateway) + an audience-bound ID
    token minted by impersonating MCP_INVOKER_SA (an agent identity cannot mint OIDC).

The app persists these to Firestore (see above), so the shared store now survives an app
restart — but this client treats it as best-effort regardless: it mirrors every write into
a local InMemoryTaskStore and falls back to it if the app is unreachable.

NOTE ON APP INSTANCES: with the Firestore backing this store no longer split-brains across
app replicas (that was the dict's failure mode). The app is still pinned to a single
instance (`--min-instances=1 --max-instances=1`) for its OTHER in-memory state — the audit-
history cache, run-token chains, presenter/note sessions — so this store isn't the reason
for the pin anymore, but the pin stays until that state is externalized too.

DEGRADATION: every call mirrors into a local InMemoryTaskStore and falls back to it if
the app is unreachable. Worst case we are exactly as broken as we were before — never
worse — and the failure is logged loudly instead of silently corrupting a run.
"""

import asyncio
import os

import httpx
from a2a.server.tasks import InMemoryTaskStore, TaskStore
from a2a.types import Task

from vibeflix_common.platform.cloud_auth import maybe_auth

_URL_ENV = "TASK_STORE_URL"

# A2A TaskState values that END the task. A dropped write of one of THESE is the only
# fatal one: the completed task then lives ONLY in this replica's local store, and the
# caller's poll — load-balanced to another replica — reads the app's stale, still-working
# task and hangs forever. (Intermediate `working` writes are safe to lose.)
_TERMINAL = ("completed", "failed", "canceled", "rejected")


def _task_state(task: Task) -> str:
    st = getattr(getattr(task, "status", None), "state", None)
    return str(getattr(st, "value", st) or "?").lower()


class TaskStoreAuthDenied(RuntimeError):
    """The shared task store refused our credential (401/403).

    Raised instead of falling back to this replica's memory. The local store cannot hold a task
    that another replica created, so answering from it turns an auth failure into the exact
    replica-roulette this store exists to prevent: the A2A layer reports "task not found", the
    caller polls a task that is running normally somewhere else, and the run hangs until its
    deadline. Failing here costs one visible error instead of a silent multi-minute stall.
    """


class RemoteTaskStore(TaskStore):
    """A2A TaskStore backed by the app's `/api/taskstore` endpoints."""

    def __init__(self, base_url: str | None = None):
        self._base = (base_url or os.environ.get(_URL_ENV, "")).rstrip("/")
        # Mirror + fallback, so an unreachable app degrades to today's behaviour
        # rather than breaking A2A outright.
        self._local = InMemoryTaskStore()
        self._warned = False
        # One httpx client per event loop, kept for the life of the replica. See _client().
        self._clients: dict[int, httpx.AsyncClient] = {}
        if not self._base:
            print(f"[task-store] {_URL_ENV} not set — falling back to a PER-REPLICA "
                  f"in-memory store; expect `404 Task not found` on task polls.",
                  flush=True)

    def _warn(self, op: str, task_id: str, exc: Exception) -> None:
        if not self._warned:
            self._warned = True
            print(f"[task-store] {op}({task_id}) FAILED (further failures silenced) — "
                  f"falling back to the per-replica store, so task polls may 404: "
                  f"{type(exc).__name__}: {exc}", flush=True)

    def _client(self) -> httpx.AsyncClient:
        """The client for this event loop, REUSED across calls — never closed per request.

        This used to return a fresh AsyncClient that each caller closed via `async with`, so
        every save/get/delete opened a new TCP+TLS connection. Under AGENT_IDENTITY the token
        is certificate-BOUND, and the mTLS handshake that carries the client certificate fails
        intermittently and PER CONNECTION: a connection that falls back to plain still sends
        the bound token, which IAP rejects with `401 ... Error code 1000`. Measured on
        vibeflix-demo 2026-08-27, one engine, one task, one 2-minute window: 43x 200 and 32x
        401 on the SAME endpoint carrying the SAME Proxy-Auth fingerprint (c39ac628) with
        16-18 minutes of life left. Identical credential, ~43% refused — the variable was the
        connection, not the token.

        Keeping one client keeps its pool alive, so a connection that handshook correctly is
        reused instead of re-rolled. Same fix, same reason, as hoisting the requests.Session
        out of the A2A poll loop in a2a/engine.py.

        Keyed by event loop: an AsyncClient binds to the loop that first drives it, and a
        replica that runs more than one loop must not share a pool between them.
        """
        try:
            loop_key = id(asyncio.get_running_loop())
        except RuntimeError:      # called outside a loop — one shared slot is fine
            loop_key = 0
        existing = self._clients.get(loop_key)
        if existing is not None and not existing.is_closed:
            return existing
        # auth=GoogleAuth() in cloud: Proxy-Authorization for the gateway + an
        # audience-bound ID token for Cloud Run. No-op locally.
        #
        # X-Task-Store-Key: the app is PUBLIC (allUsers/run.invoker — the browser has to
        # load the console), so the task-store endpoints carry their own shared secret.
        # Without it anyone on the internet could read or tamper with A2A task state.
        hdr = {}
        key = os.environ.get("TASK_STORE_KEY", "")
        if key:
            hdr["X-Task-Store-Key"] = key
        client = httpx.AsyncClient(
            auth=maybe_auth(), timeout=20.0, headers=hdr,
            # Hold connections open between polls. The A2A poll cadence is ~1s, so a short
            # keepalive would expire the good connection between every call and defeat this.
            limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=300.0),
        )
        self._clients[loop_key] = client
        return client

    async def _recycle(self) -> None:
        """Drop this loop's pooled client so the next call re-handshakes.

        Pooling is what stops us re-rolling the flaky mTLS handshake on every request — but
        it also means a connection that handshook BADLY would be reused for every subsequent
        call, turning an intermittent 401 into a permanent one. Recycling on an auth refusal
        keeps the win without that failure mode: good connections stay, a refused one is
        thrown away and the next attempt gets a fresh handshake.
        """
        try:
            loop_key = id(asyncio.get_running_loop())
        except RuntimeError:
            loop_key = 0
        client = self._clients.pop(loop_key, None)
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001 — closing must never mask the real failure
                pass

    async def save(self, task: Task, context=None) -> None:
        await self._local.save(task, context)
        if not self._base:
            return
        state = _task_state(task)
        terminal = any(t in state for t in _TERMINAL)
        # Terminal writes are the ones that hang the caller if lost, so they are logged
        # LOUDLY (success and failure, never silenced) and RETRIED. The stream of
        # intermediate `working` writes stays best-effort (retry adds latency for no gain).
        attempts = 5 if terminal else 1
        last_exc = None
        for i in range(attempts):
            try:
                c = self._client()
                r = await c.put(f"{self._base}/api/taskstore/{task.id}",
                                json={"json": task.model_dump_json()})
                r.raise_for_status()
                if terminal:
                    print(f"[task-store] save({task.id}) state={state} → PUT {r.status_code}"
                          f"{f' (after {i} retries)' if i else ''}", flush=True)
                return
            except Exception as e:  # noqa: BLE001 — the store must never kill the task
                last_exc = e
                if terminal and i < attempts - 1:
                    await asyncio.sleep(0.4 * (i + 1))
                    continue
                break
        if terminal:
            # THIS is the line to watch: a terminal state that never reached the shared
            # store. The task completed on this replica but the caller will poll a stale
            # non-terminal task on another replica and hang until its deadline.
            print(f"[task-store] ⚠️ save({task.id}) state={state} FAILED after {attempts} "
                  f"tries — TERMINAL state NOT persisted to the shared store; the caller "
                  f"will hang: {type(last_exc).__name__}: {last_exc}", flush=True)
        else:
            self._warn("save", task.id, last_exc)

    async def get(self, task_id: str, context=None) -> Task | None:
        if self._base:
            try:
                c = self._client()
                r = await c.get(f"{self._base}/api/taskstore/{task_id}")
                if r.status_code == 200:
                    return Task.model_validate_json(r.json()["json"])
                if r.status_code in (401, 403):
                    # An AUTH failure is NOT a missing task. Falling through quietly makes this
                    # replica answer from local memory, which never had the task — so the A2A
                    # layer reports 404 "task not found" for a task that exists. That is exactly
                    # how a token expiry appears in the gateway log: a burst of 404s on
                    # tasks/{id} with 401s on /api/taskstore alongside them. GoogleAuth has
                    # already retried once with a forced re-mint, so reaching here means the
                    # credential is genuinely refused — say so.
                    print(f"[task-store] get({task_id}) → {r.status_code} AUTH DENIED — this is "
                          f"NOT a missing task. Failing this read rather than answering from "
                          f"this replica's memory, which never had the task.", flush=True)
                    # The refusal may belong to this CONNECTION (a bound token on a link whose
                    # mTLS handshake fell back), not to the credential. Throw the connection
                    # away so the next call is not stuck behind the same bad one.
                    await self._recycle()
                    raise TaskStoreAuthDenied(
                        f"shared task store refused this engine's credential "
                        f"({r.status_code}) reading task {task_id}")
                elif r.status_code != 404:
                    r.raise_for_status()
            except TaskStoreAuthDenied:
                raise                       # deliberate: never downgraded to a local read
            except Exception as e:  # noqa: BLE001
                # Transport failures are different from auth failures. The app being
                # unreachable is survivable, and this replica's own view is the best answer
                # available, so those still fall through.
                self._warn("get", task_id, e)
        # 404 upstream, or the app is unreachable → whatever this replica knows.
        return await self._local.get(task_id, context)

    async def delete(self, task_id: str, context=None) -> None:
        await self._local.delete(task_id, context)
        if not self._base:
            return
        try:
            c = self._client()
            r = await c.delete(f"{self._base}/api/taskstore/{task_id}")
            if r.status_code not in (200, 204, 404):
                r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            self._warn("delete", task_id, e)

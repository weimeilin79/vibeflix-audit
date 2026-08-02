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


class RemoteTaskStore(TaskStore):
    """A2A TaskStore backed by the app's `/api/taskstore` endpoints."""

    def __init__(self, base_url: str | None = None):
        self._base = (base_url or os.environ.get(_URL_ENV, "")).rstrip("/")
        # Mirror + fallback, so an unreachable app degrades to today's behaviour
        # rather than breaking A2A outright.
        self._local = InMemoryTaskStore()
        self._warned = False
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
        return httpx.AsyncClient(auth=maybe_auth(), timeout=20.0, headers=hdr)

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
                async with self._client() as c:
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
                async with self._client() as c:
                    r = await c.get(f"{self._base}/api/taskstore/{task_id}")
                if r.status_code == 200:
                    return Task.model_validate_json(r.json()["json"])
                if r.status_code != 404:
                    r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                self._warn("get", task_id, e)
        # 404 upstream, or the app is unreachable → whatever this replica knows.
        return await self._local.get(task_id, context)

    async def delete(self, task_id: str, context=None) -> None:
        await self._local.delete(task_id, context)
        if not self._base:
            return
        try:
            async with self._client() as c:
                r = await c.delete(f"{self._base}/api/taskstore/{task_id}")
                if r.status_code not in (200, 204, 404):
                    r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            self._warn("delete", task_id, e)

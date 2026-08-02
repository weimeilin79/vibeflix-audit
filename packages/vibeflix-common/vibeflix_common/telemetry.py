"""Live mesh telemetry → Pub/Sub (the Workflow graph's tool LEDs).

`emit_event` publishes one event onto PUBSUB_TOPIC (see deploy/setup_pubsub.sh for
the schema/contract); it is FIRE-AND-FORGET and a NO-OP when PUBSUB_TOPIC is unset,
so the mesh runs unchanged without the backbone. Publishing is non-blocking (the
Pub/Sub client batches on a background thread) — a tool call never waits on it.

`instrument_fastmcp` hooks a FastMCP server's tool registration so EVERY tool —
current and future — emits a `started` event on entry and a `completed` (or
`failed`) event just before returning, without touching the tool bodies:

    mcp = FastMCP("...")
    instrument_fastmcp(mcp, source="mcp_licensing")   # BEFORE the @mcp.tool() defs
"""

import contextvars
import functools
import inspect
import json
import os
import time

_TOPIC = os.environ.get("PUBSUB_TOPIC", "").strip()
_publisher = None
_warned = False

# ---- run scoping -----------------------------------------------------------
# The mesh topic is ONE broadcast bus shared by every run and every open console.
# Without a run id the console cannot tell "a node of the audit I am watching" from
# "a node of the audit that finished 30 seconds ago" — and the graph renders BOTH.
# Every event therefore carries the id of the run that produced it, and the console
# drops any event stamped with a run that is not the one on screen.
#
# A ContextVar (not a global) because one engine serves CONCURRENT runs: asyncio
# copies the context per task, so each request keeps its own id with no locking.
_RUN_ID: contextvars.ContextVar[str] = contextvars.ContextVar("vibeflix_run_id", default="")


def set_run_id(run_id: str) -> None:
    """Bind the current task to a run (called once, where the request arrives)."""
    _RUN_ID.set(str(run_id or ""))


def _node_run_id(args, kwargs=None) -> str:
    """The run id for a node, preferring the workflow Context over the ContextVar.

    WHY not just the ContextVar: a ContextVar only flows PARENT→CHILD at task creation.
    The orchestrator's `ingest` sets it, but every other node runs in a SIBLING task, so
    the value never reaches them — they all reported an empty run. `ctx.state` is the
    workflow's own durable store: it survives across nodes, tasks, and the resume of a
    suspended workflow. The ContextVar is only a fallback for nodes with no Context.

    MUST scan kwargs too: ADK invokes nodes with KEYWORD arguments, so scanning `args`
    alone found no Context and silently fell through to the (empty) ContextVar — the
    agent nodes shipped with run_id="" and the console could not scope them.
    """
    for a in (*args, *(kwargs or {}).values()):
        get = getattr(getattr(a, "state", None), "get", None)
        if callable(get):
            try:
                rid = get("run_id")
            except Exception:  # noqa: BLE001 — a foreign object with a .state.get
                continue
            if rid:
                return str(rid)
    return _RUN_ID.get("")


def _publish_rest(project: str, payload: bytes, source: str, event: str) -> None:
    """Publish over Pub/Sub's REST API instead of the gRPC client.

    WHY: inside a GATEWAY-ATTACHED engine the gRPC PublisherClient is refused —
        403 Egress request is not authorized. The endpoint is either incorrect or
        unregistered in the Agent Registry.
    …no matter how the pubsub host is registered. The Agent Gateway governs HTTP egress;
    it cannot match a gRPC channel to a registered endpoint, so agent telemetry never
    left the engine. The tool LEDs still worked (the MCP servers are plain Cloud Run and
    are NOT gateway-governed), so the console's dead workflow graph looked like a frontend
    bug for a very long time. It wasn't.

    Plain HTTPS to https://pubsub.googleapis.com (the exact host registered as `gcp-pubsub`
    and granted iap.egressor) passes governed egress cleanly — and keeps the telemetry ON
    the governed path, which is the point of the demo.
    """
    import base64
    import requests
    import google.auth
    import google.auth.transport.requests as _gar

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(_gar.Request())
    hdr = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    if os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
        hdr["Proxy-Authorization"] = f"Bearer {creds.token}"   # the gateway leg
    r = requests.post(
        f"https://pubsub.googleapis.com/v1/projects/{project}/topics/{_TOPIC}:publish",
        headers=hdr, timeout=10,
        json={"messages": [{
            "data": base64.b64encode(payload).decode(),
            "attributes": {"source": source, "event": event},
        }]},
    )
    r.raise_for_status()


def emit_event(source: str, event: str, tool: str = "", node: str = "",
               status: str = "", detail: str = "", run_id: str = "") -> None:
    """Publish one mesh-telemetry event (no-op when PUBSUB_TOPIC is unset)."""
    global _publisher, _warned
    if not _TOPIC:
        return
    try:
        if _publisher is None:
            from google.cloud import pubsub_v1
            _publisher = pubsub_v1.PublisherClient()
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        payload = json.dumps({
            # Falls back to the task's bound run — so callers that never pass run_id
            # (every MCP tool, most nodes) are still scoped correctly.
            "run_id": run_id or _RUN_ID.get(""),
            "source": source,
            "node": node or source,
            "tool": tool,
            "event": event,
            "status": status,
            "detail": detail or (f"{tool}()" if tool else ""),
            "ts": int(time.time() * 1000),
        }).encode()
        # Inside a gateway-attached ENGINE the gRPC publisher is refused (the gateway
        # governs HTTP egress and cannot match a gRPC channel to a registered endpoint) —
        # so agents publish over REST. The MCP servers are plain Cloud Run, not
        # gateway-governed, so they keep the batching gRPC client.
        if os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
            _publish_rest(project, payload, source, event)
            return

        # Returns a future; the client publishes from a background thread.
        fut = _publisher.publish(_publisher.topic_path(project, _TOPIC), payload,
                                 source=source, event=event)

        # SURFACE ASYNC FAILURES. publish() only raises synchronously for bad args — a
        # PermissionDenied (no roles/pubsub.publisher) or a gateway egress denial lands on
        # the FUTURE, and if nobody reads it the error is silently swallowed. That is how
        # the console's graph + tool LEDs went dark in cloud with no error anywhere: the
        # agents ran fine, the events just never left. Log the first failure loudly.
        def _check(f):
            global _warned
            try:
                f.result(timeout=0) if hasattr(f, "result") else None
            except Exception as exc:  # noqa: BLE001
                if not _warned:
                    _warned = True
                    print(f"[telemetry] PUBLISH FAILED (further failures silenced) — the "
                          f"console's graph/LEDs will stay dark: {type(exc).__name__}: {exc}",
                          flush=True)
        try:
            fut.add_done_callback(_check)
        except Exception:
            pass
    except Exception as e:  # telemetry must never break the tool call
        if not _warned:
            _warned = True
            print(f"[telemetry] emit failed (further failures silenced): "
                  f"{type(e).__name__}: {e}", flush=True)


def instrument_node(source: str, node_name: str | None = None):
    """Decorator for ADK Workflow node functions: emits `started` on entry and
    `completed` (or `failed`) when the node finishes. Handles every node shape —
    plain fn, async fn, generator, async generator. Apply UNDER @node(...):

        @node(name="dispatch", rerun_on_resume=True)
        @instrument_node("orchestrator")
        async def dispatch(ctx, node_input): ...

    `node_name` overrides the emitted node id (needed for factory-made nodes whose
    function name is generic, e.g. the orchestrator's guards).
    """
    def deco(fn):
        name = node_name or fn.__name__

        if inspect.isasyncgenfunction(fn):
            @functools.wraps(fn)
            async def wrapped(*args, **kwargs):
                rid = _node_run_id(args, kwargs)
                emit_event(source, "started", node=name, run_id=rid)
                try:
                    async for ev in fn(*args, **kwargs):
                        yield ev
                except Exception as e:
                    emit_event(source, "failed", node=name, run_id=_node_run_id(args, kwargs),
                               detail=f"{name}: {type(e).__name__}")
                    raise
                # Re-read: the node may have just WRITTEN run_id into ctx.state (the
                # orchestrator's `ingest` does exactly that), so `completed` can be
                # scoped even when `started` fired before the id was known.
                emit_event(source, "completed", node=name, run_id=_node_run_id(args, kwargs))
        elif inspect.isgeneratorfunction(fn):
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                rid = _node_run_id(args, kwargs)
                emit_event(source, "started", node=name, run_id=rid)
                try:
                    yield from fn(*args, **kwargs)
                except Exception as e:
                    emit_event(source, "failed", node=name, run_id=_node_run_id(args, kwargs),
                               detail=f"{name}: {type(e).__name__}")
                    raise
                emit_event(source, "completed", node=name, run_id=_node_run_id(args, kwargs))
        elif inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapped(*args, **kwargs):
                rid = _node_run_id(args, kwargs)
                emit_event(source, "started", node=name, run_id=rid)
                try:
                    result = await fn(*args, **kwargs)
                except Exception as e:
                    emit_event(source, "failed", node=name, run_id=_node_run_id(args, kwargs),
                               detail=f"{name}: {type(e).__name__}")
                    raise
                emit_event(source, "completed", node=name, run_id=_node_run_id(args, kwargs))
                return result
        else:
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                rid = _node_run_id(args, kwargs)
                emit_event(source, "started", node=name, run_id=rid)
                try:
                    result = fn(*args, **kwargs)
                except Exception as e:
                    emit_event(source, "failed", node=name, run_id=_node_run_id(args, kwargs),
                               detail=f"{name}: {type(e).__name__}")
                    raise
                emit_event(source, "completed", node=name, run_id=_node_run_id(args, kwargs))
                return result

        return wrapped

    return deco


def instrument_fastmcp(mcp, source: str) -> None:
    """Wrap `mcp.tool` so every registered tool emits started/completed/failed.

    Call BEFORE the @mcp.tool() definitions. functools.wraps preserves the original
    function's name/docstring, and inspect.signature follows __wrapped__, so
    FastMCP's schema generation (incl. Annotated params) is unaffected.
    """
    original_tool = mcp.tool

    def tool(*dargs, **dkwargs):
        register = original_tool(*dargs, **dkwargs)

        def decorator(fn):
            name = dkwargs.get("name") or fn.__name__

            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def wrapped(*args, **kwargs):
                    emit_event(source, "started", tool=name)
                    try:
                        result = await fn(*args, **kwargs)
                    except Exception as e:
                        emit_event(source, "failed", tool=name,
                                   detail=f"{name}: {type(e).__name__}")
                        raise
                    emit_event(source, "completed", tool=name)
                    return result
            else:
                @functools.wraps(fn)
                def wrapped(*args, **kwargs):
                    emit_event(source, "started", tool=name)
                    try:
                        result = fn(*args, **kwargs)
                    except Exception as e:
                        emit_event(source, "failed", tool=name,
                                   detail=f"{name}: {type(e).__name__}")
                        raise
                    emit_event(source, "completed", tool=name)
                    return result

            return register(wrapped)

        return decorator

    mcp.tool = tool

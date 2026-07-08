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

import functools
import inspect
import json
import os
import time

_TOPIC = os.environ.get("PUBSUB_TOPIC", "").strip()
_publisher = None
_warned = False


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
            "run_id": run_id,
            "source": source,
            "node": node or source,
            "tool": tool,
            "event": event,
            "status": status,
            "detail": detail or (f"{tool}()" if tool else ""),
            "ts": int(time.time() * 1000),
        }).encode()
        # Returns a future; the client publishes from a background thread.
        _publisher.publish(_publisher.topic_path(project, _TOPIC), payload,
                           source=source, event=event)
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
                emit_event(source, "started", node=name)
                try:
                    async for ev in fn(*args, **kwargs):
                        yield ev
                except Exception as e:
                    emit_event(source, "failed", node=name, detail=f"{name}: {type(e).__name__}")
                    raise
                emit_event(source, "completed", node=name)
        elif inspect.isgeneratorfunction(fn):
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                emit_event(source, "started", node=name)
                try:
                    yield from fn(*args, **kwargs)
                except Exception as e:
                    emit_event(source, "failed", node=name, detail=f"{name}: {type(e).__name__}")
                    raise
                emit_event(source, "completed", node=name)
        elif inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapped(*args, **kwargs):
                emit_event(source, "started", node=name)
                try:
                    result = await fn(*args, **kwargs)
                except Exception as e:
                    emit_event(source, "failed", node=name, detail=f"{name}: {type(e).__name__}")
                    raise
                emit_event(source, "completed", node=name)
                return result
        else:
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                emit_event(source, "started", node=name)
                try:
                    result = fn(*args, **kwargs)
                except Exception as e:
                    emit_event(source, "failed", node=name, detail=f"{name}: {type(e).__name__}")
                    raise
                emit_event(source, "completed", node=name)
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

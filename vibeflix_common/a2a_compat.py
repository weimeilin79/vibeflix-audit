"""Compat bridge: google-adk 2.3 imports the OLD a2a.types names; vertexai's
A2aAgent template requires a2a-sdk>=1.0 (new AgentCard model, new constants).
We run a2a-sdk 1.x and alias every missing old name into a2a.types from the
SDK's own compat module. Call ensure() BEFORE any google.adk import — both
client-side (deploy script) and engine-side (build_executor)."""


def ensure():
    import a2a.types as new
    try:
        from a2a.compat.v0_3 import types as old
    except ImportError:      # old sdk — nothing to bridge
        return
    for n in dir(old):
        if not n.startswith("_") and not hasattr(new, n):
            setattr(new, n, getattr(old, n))
    # adk imports a2a.client.middleware (removed in 1.x) — alias it.
    import sys, types as _t
    if "a2a.client.middleware" not in sys.modules:
        try:
            import a2a.client.middleware  # noqa: F401
        except ImportError:
            from a2a.client.client import ClientCallContext
            mod = _t.ModuleType("a2a.client.middleware")
            mod.ClientCallContext = ClientCallContext
            sys.modules["a2a.client.middleware"] = mod

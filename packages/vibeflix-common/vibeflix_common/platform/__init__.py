"""Platform — cross-cutting plumbing, used by agents AND MCP servers.

If a module is here it is because BOTH sides import it. That is the whole entry rule.

    cloud_auth.py  the credential layer: which of three token dialects to present to
                   which destination, gated by RUN_LOCAL
    telemetry.py   live mesh telemetry to Pub/Sub — instrument_node (agents) and
                   instrument_fastmcp (MCP servers)
    registry.py    semantic registry reads from Firestore, with an offline fallback
    health.py      handshake-level mesh probes and the startup banner

Note this package is named `platform`, which is also a stdlib module. That is safe:
Python 3 has no implicit relative imports, so `import platform` anywhere still resolves
to the standard library. Only `vibeflix_common.platform` reaches this package.
"""

"""Compat shim: vertexai's A2aAgent template imports TransportProtocol /
PROTOCOL_VERSION_CURRENT from a2a.utils.constants (a2a-sdk>=1.0 layout), but
google-adk 2.3 requires a2a-sdk<1 (old layout). Bridge the gap — call ensure()
before touching the template, client-side AND inside the engine."""

def ensure():
    import a2a.utils.constants as c
    if not hasattr(c, "TransportProtocol"):
        from a2a.types import TransportProtocol
        c.TransportProtocol = TransportProtocol
    if not hasattr(c, "PROTOCOL_VERSION_CURRENT"):
        c.PROTOCOL_VERSION_CURRENT = "0.3.0"

"""Semantic registry reads for the MCP servers (Phase 2).

Reads facts ("what's true": approved media/sources, style guidelines, exclusivity
contracts, trademarks, sourcing caps) from Firestore, falling back to the value
baked into the calling server when Firestore isn't configured or is unreachable.
This keeps each MCP server self-contained (its own hardcoded fallback) while
letting the registries be edited in Firestore without a redeploy.

Enable by setting FIRESTORE_DATABASE (e.g. "(default)"); unset → always fallback.
Depends on google-cloud-firestore (the `mcp` extra), NOT google-adk.
"""

import os
from typing import Any

_client = None


def _firestore_client():
    global _client
    if _client is None:
        from google.cloud import firestore

        _client = firestore.Client(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            database=os.environ["FIRESTORE_DATABASE"],
        )
    return _client


def registry_get(collection: str, document: str, fallback: Any, *, field: str | None = None) -> Any:
    """Return a registry value from Firestore `collection/document`, else `fallback`.

    Args:
        collection, document: the Firestore path.
        fallback: value returned when Firestore is unset/unreachable/missing.
        field: if given, return that field of the document (for list/scalar
            registries stored as ``{field: value}``); otherwise return the whole
            document dict.
    """
    if not os.environ.get("FIRESTORE_DATABASE"):
        return fallback
    try:
        snap = _firestore_client().collection(collection).document(document).get()
        if not snap.exists:
            return fallback
        data = snap.to_dict()
        return data.get(field, fallback) if field else data
    except Exception:
        # Registry is best-effort: never fail a compliance check on a lookup error.
        return fallback

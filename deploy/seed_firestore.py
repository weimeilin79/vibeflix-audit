"""Seed the Vibeflix semantic registries into Firestore (Phase 2).

Writes the current hardcoded MCP-server defaults into Firestore so the migration
is behavior-preserving: with FIRESTORE_DATABASE set, the servers read these and
behave identically — then you can edit a document to change a rule without a
redeploy. List/scalar registries are stored as {"items": [...]}; the MCP servers
read them via registry_get(..., field="items").

Run:
  GOOGLE_CLOUD_PROJECT=pokedemo-test FIRESTORE_DATABASE=vibeflix-registry \
    python deploy/seed_firestore.py
"""

import os

from google.cloud import firestore

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "pokedemo-test")
DATABASE = os.environ.get("FIRESTORE_DATABASE", "vibeflix-registry")

REGISTRIES = {
    "brand_style_registry": {
        "brand_terms": {"items": [
            "grogu", "mandalorian", "mando", "din", "djarin", "skywalker", "vibeflix",
            "funko", "pop", "vinyl", "sku", "starwars", "yoda",
            "boba", "fett", "ahsoka", "tano", "obi", "wan", "kenobi", "vader",
        ]},
        "printed_media": {"items": [
            "vinyl figure box", "poster", "trading card", "apparel tag",
            "sticker sheet", "art print", "enamel pin card", "mug wrap", "T-shirt",
            "book cover", "comic book cover", "magazine cover", "shoes", "hat",
            "hoodie", "jacket", "backpack", "lunchbox", "water bottle", "phone case",
            "tablet case", "laptop sleeve",
        ]},
        "approved_sources": {"items": [
            "gs://vibeflix-approved-assets/",
            "gs://vibeflix-licensing/",
            "gs://vibeflix-request-image/",
            "https://assets.vibeflix.com/",
        ]},
    },
    "legal_registry": {
        "style_guidelines_grogu": {
            "official_name": "The Child (Grogu)",
            "primary_logo_font": "Outfit-Bold",
            "allowed_fonts": ["Outfit", "Inter"],
            "hex_palette": ["#10b981", "#1e293b", "#ffffff"],
            "restricted_keywords": ["Baby Yoda"],
        },
        "exclusivity_grogu_north_america": {
            "has_conflict": True,
            "conflicting_partner": "Hasbro Inc.",
            "exclusivity_type": "Stylized Vinyl Figurines / Action Figures",
            "contract_expiration": "2028-12-31",
            "message": "Block release. Hasbro has exclusive rights for vinyl figures in North America.",
        },
        "trademark_grogu": {
            "character_id": "grogu",
            "registration_status": "Valid",
            "customs_database_synced": True,
            "renewal_date": "2029-04-15",
        },
    },
    "market_policy": {
        "sourcing_caps": {
            "authorized_max_skus": 25000,
            "current_sourcing_cap_rules": "Volume overrides > 25,000 trigger structural splitter agent workflows to split capacity into distinct addendums.",
        },
    },
}


def _seed_vendors(client: "firestore.Client") -> None:
    """Seed the `vendors` collection (mcp_licensing's Firestore-backed CRUD store)
    from the in-code defaults. Unlike the registries above, vendors are MUTATED at
    runtime (create_vendor/update_vendor — onboarding), so by default only MISSING
    vendors are created; set RESET_VENDORS=1 to overwrite every default vendor with
    its pristine record (resets demo onboarding state)."""
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                           / "mcp_servers" / "mcp_licensing"))
    from data import _VENDORS  # the pristine default records

    reset = os.environ.get("RESET_VENDORS", "") == "1"
    col = client.collection("vendors")
    if reset:  # true restore: also drop vendors onboarded at runtime
        for doc in col.stream():
            if doc.id not in _VENDORS:
                col.document(doc.id).delete()
                print(f"[seed] vendors/{doc.id} deleted (not a default vendor)")
    for vid, record in _VENDORS.items():
        if reset or not col.document(vid).get().exists:
            col.document(vid).set(record)
            print(f"[seed] vendors/{vid}" + (" (reset)" if reset else ""))
        else:
            print(f"[seed] vendors/{vid} exists — kept (RESET_VENDORS=1 to overwrite)")


def main() -> None:
    client = firestore.Client(project=PROJECT, database=DATABASE)
    print(f"[seed] project={PROJECT} database={DATABASE}")
    for collection, docs in REGISTRIES.items():
        for doc_id, data in docs.items():
            client.collection(collection).document(doc_id).set(data)
            print(f"[seed] {collection}/{doc_id}")
    _seed_vendors(client)
    print("[seed] done.")


if __name__ == "__main__":
    main()

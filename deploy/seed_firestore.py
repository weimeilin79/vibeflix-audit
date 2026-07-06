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


def main() -> None:
    client = firestore.Client(project=PROJECT, database=DATABASE)
    print(f"[seed] project={PROJECT} database={DATABASE}")
    for collection, docs in REGISTRIES.items():
        for doc_id, data in docs.items():
            client.collection(collection).document(doc_id).set(data)
            print(f"[seed] {collection}/{doc_id}")
    print("[seed] done.")


if __name__ == "__main__":
    main()

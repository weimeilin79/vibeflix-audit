"""Data layer for the Vendor & Licensing Clearance registry (mcp_licensing).

  * VENDORS       — approved manufacturing partners (VND-####). **Firestore-backed
                    CRUD** when FIRESTORE_DATABASE is set (collection `vendors`, doc
                    id = vendor id, auto-seeded from the defaults below on first use);
                    the in-memory `_VENDORS` dict is the offline fallback. Access ONLY
                    via `vendors_all` / `vendor_get` / `vendor_put`.
  * _TRADEMARKS   — IP/trademark registrations, keyed by character_id (in-memory).
  * _EXCLUSIVITY  — exclusivity contracts (EXC-####) that lock a category × territory
                    (in-memory).
  * _CONTRACTS    — executed licensing contracts, LC-#### (in-memory; the app snapshots
                    each contract into the audit history at record time).
  * _RATE_CARDS   — licensor rate cards per character (in-memory, read-only).
"""

import os

# ---------------------------------------------------------------------------
# VENDORS — approved manufacturing partners.
# ---------------------------------------------------------------------------
_VENDORS: dict[str, dict] = {
    "VND-1001": {
        "vendor_id": "VND-1001",
        "legal_name": "Shenzhen Apex Collectibles Ltd.",
        "dba": "Apex Toys",
        "hq_country": "China",
        "operating_territories": ["Asia-Pacific", "North America"],
        "product_categories": ["Vinyl Figures", "Action Figures", "Blind Box"],
        "manufacturing_capabilities": ["injection_molding", "hand_painting", "packaging", "tampo_printing"],
        "license_tier": "Tier 1 - Approved",
        "status": "active",
        "annual_capacity_units": 4_500_000,
        "moq": 3_000,
        "lead_time_days": 55,
        "certifications": ["ISO 9001", "ICTI Ethical Toy", "ASTM F963"],
        "compliance_rating": "A",
        "last_audit": "2025-11-02",
        "contact": {"name": "Wei Zhang", "email": "wzhang@apextoys.example", "phone": "+86-755-8100-2233"},
        "onboarded": "2021-03-14",
        "notes": "Primary vinyl-figure partner. Strong QA record; preferred for stylized collectibles.",
    },
    "VND-1002": {
        "vendor_id": "VND-1002",
        "legal_name": "Bavaria Präzision Formenbau GmbH",
        "dba": "BP Studios",
        "hq_country": "Germany",
        "operating_territories": ["Europe", "North America"],
        "product_categories": ["Resin Statues", "Premium Collectibles"],
        "manufacturing_capabilities": ["resin_casting", "cold_cast", "hand_finishing", "limited_runs"],
        "license_tier": "Tier 1 - Approved",
        "status": "active",
        "annual_capacity_units": 180_000,
        "moq": 500,
        "lead_time_days": 90,
        "certifications": ["ISO 9001", "EN 71"],
        "compliance_rating": "A",
        "last_audit": "2025-09-18",
        "contact": {"name": "Lena Vogt", "email": "l.vogt@bpstudios.example", "phone": "+49-89-2000-4471"},
        "onboarded": "2020-07-01",
        "notes": "High-end resin statues, low volume / high margin. EU customs pre-cleared.",
    },
    "VND-1003": {
        "vendor_id": "VND-1003",
        "legal_name": "Guadalajara Figuras S.A. de C.V.",
        "dba": "GDL Figuras",
        "hq_country": "Mexico",
        "operating_territories": ["North America", "Latin America"],
        "product_categories": ["Action Figures", "Plush", "Vinyl Figures"],
        "manufacturing_capabilities": ["injection_molding", "sewing", "stuffing", "assembly"],
        "license_tier": "Tier 2 - Conditional",
        "status": "active",
        "annual_capacity_units": 900_000,
        "moq": 5_000,
        "lead_time_days": 40,
        "certifications": ["ICTI Ethical Toy"],
        "compliance_rating": "B",
        "last_audit": "2025-10-27",
        "contact": {"name": "Mateo Reyes", "email": "mreyes@gdlfiguras.example", "phone": "+52-33-3600-1188"},
        "onboarded": "2022-11-09",
        "notes": "Nearshore NA capacity, faster lead time. Conditional tier pending ISO 9001 renewal.",
    },
    "VND-1004": {
        "vendor_id": "VND-1004",
        "legal_name": "Osaka Craft Works K.K.",
        "dba": "OCW",
        "hq_country": "Japan",
        "operating_territories": ["Asia-Pacific"],
        "product_categories": ["Vinyl Figures", "Blind Box", "Sofubi"],
        "manufacturing_capabilities": ["soft_vinyl", "rotocast", "hand_painting", "designer_toy"],
        "license_tier": "Tier 1 - Approved",
        "status": "active",
        "annual_capacity_units": 320_000,
        "moq": 1_000,
        "lead_time_days": 70,
        "certifications": ["ISO 9001", "ST Mark (Japan)"],
        "compliance_rating": "A",
        "last_audit": "2025-08-30",
        "contact": {"name": "Aiko Tanaka", "email": "a.tanaka@ocw.example", "phone": "+81-6-6900-7788"},
        "onboarded": "2023-02-20",
        "notes": "Designer/sofubi specialist for APAC drops. Not cleared outside Asia-Pacific.",
    },
    "VND-1005": {
        "vendor_id": "VND-1005",
        "legal_name": "Istanbul Novelty Imports Ltd. Şti.",
        "dba": "INI",
        "hq_country": "Türkiye",
        "operating_territories": ["Europe", "Middle East & Africa"],
        "product_categories": ["Apparel", "Novelty", "Accessories"],
        "manufacturing_capabilities": ["screen_printing", "embroidery", "cut_and_sew"],
        "license_tier": "Tier 3 - Probation",
        "status": "suspended",
        "annual_capacity_units": 1_200_000,
        "moq": 2_000,
        "lead_time_days": 35,
        "certifications": ["OEKO-TEX"],
        "compliance_rating": "D",
        "last_audit": "2026-01-15",
        "contact": {"name": "Emre Demir", "email": "e.demir@ini.example", "phone": "+90-212-555-9090"},
        "onboarded": "2024-06-11",
        "notes": "SUSPENDED 2026-01 after a failed social-compliance audit (unauthorized subcontracting).",
    },
    "VND-1006": {
        "vendor_id": "VND-1006",
        "legal_name": "Kraków Vinyl Studio Sp. z o.o.",
        "dba": "KVS",
        "hq_country": "Poland",
        "operating_territories": ["Europe", "North America"],
        "product_categories": ["Vinyl Figures", "Action Figures"],
        "manufacturing_capabilities": ["injection_molding", "hand_painting", "packaging", "tampo_printing"],
        "license_tier": "Tier 1 - Approved",
        "status": "active",
        "annual_capacity_units": 700_000,
        "moq": 2_500,
        "lead_time_days": 50,
        "certifications": ["ISO 9001", "EN 71", "ICTI Ethical Toy"],
        "compliance_rating": "A",
        "last_audit": "2025-12-05",
        "contact": {"name": "Zofia Nowak", "email": "z.nowak@kvs.example", "phone": "+48-12-350-6600"},
        "onboarded": "2022-04-18",
        "notes": "EU-based vinyl-figure capacity; primary option for Europe drops.",
    },
    "VND-1007": {
        "vendor_id": "VND-1007",
        "legal_name": "Maple Collectibles Inc.",
        "dba": "Maple Toys",
        "hq_country": "Canada",
        "operating_territories": ["North America"],
        "product_categories": ["Vinyl Figures", "Plush", "Action Figures"],
        "manufacturing_capabilities": ["injection_molding", "sewing", "hand_painting", "packaging"],
        "license_tier": "Tier 1 - Approved",
        "status": "active",
        "annual_capacity_units": 620_000,
        "moq": 2_000,
        "lead_time_days": 45,
        "certifications": ["ISO 9001", "ASTM F963", "ICTI Ethical Toy"],
        "compliance_rating": "A",
        "last_audit": "2025-11-20",
        "contact": {"name": "Olivia Tremblay", "email": "o.tremblay@mapletoys.example", "phone": "+1-416-555-2040"},
        "onboarded": "2021-09-08",
        "notes": "Toronto-based; strong NA nearshore option with fast turnaround.",
    },
    "VND-1008": {
        "vendor_id": "VND-1008",
        "legal_name": "Liberty Figure Works LLC",
        "dba": "Liberty Toys",
        "hq_country": "United States",
        "operating_territories": ["North America", "Latin America"],
        "product_categories": ["Action Figures", "Vinyl Figures", "Resin Statues"],
        "manufacturing_capabilities": ["injection_molding", "resin_casting", "hand_painting", "assembly"],
        "license_tier": "Tier 1 - Approved",
        "status": "active",
        "annual_capacity_units": 1_100_000,
        "moq": 4_000,
        "lead_time_days": 42,
        "certifications": ["ISO 9001", "ASTM F963"],
        "compliance_rating": "A",
        "last_audit": "2025-10-09",
        "contact": {"name": "Marcus Bell", "email": "mbell@libertytoys.example", "phone": "+1-614-555-7781"},
        "onboarded": "2020-05-22",
        "notes": "Columbus, OH. Domestic US capacity; premium tooling, higher unit cost.",
    },
    "VND-1009": {
        "vendor_id": "VND-1009",
        "legal_name": "Amazônia Brinquedos Ltda.",
        "dba": "Amazô Toys",
        "hq_country": "Brazil",
        "operating_territories": ["Latin America", "North America"],
        "product_categories": ["Plush", "Vinyl Figures", "Novelty"],
        "manufacturing_capabilities": ["sewing", "stuffing", "injection_molding", "screen_printing"],
        "license_tier": "Tier 2 - Conditional",
        "status": "active",
        "annual_capacity_units": 850_000,
        "moq": 5_000,
        "lead_time_days": 48,
        "certifications": ["ICTI Ethical Toy", "INMETRO"],
        "compliance_rating": "B",
        "last_audit": "2025-09-30",
        "contact": {"name": "Beatriz Souza", "email": "b.souza@amazotoys.example", "phone": "+55-11-4002-8922"},
        "onboarded": "2022-08-15",
        "notes": "São Paulo. LatAm plush specialist; conditional pending ISO 9001.",
    },
    "VND-1010": {
        "vendor_id": "VND-1010",
        "legal_name": "Andina Figuras S.A.S.",
        "dba": "Andina",
        "hq_country": "Colombia",
        "operating_territories": ["Latin America"],
        "product_categories": ["Action Figures", "Apparel", "Accessories"],
        "manufacturing_capabilities": ["injection_molding", "cut_and_sew", "screen_printing"],
        "license_tier": "Tier 2 - Conditional",
        "status": "active",
        "annual_capacity_units": 480_000,
        "moq": 3_000,
        "lead_time_days": 44,
        "certifications": ["ICTI Ethical Toy"],
        "compliance_rating": "B",
        "last_audit": "2025-12-01",
        "contact": {"name": "Camilo Restrepo", "email": "c.restrepo@andina.example", "phone": "+57-4-444-1290"},
        "onboarded": "2023-05-03",
        "notes": "Medellín. Regional LatAm capacity; not yet cleared outside Latin America.",
    },
    "VND-1011": {
        "vendor_id": "VND-1011",
        "legal_name": "Pampas Craft S.R.L.",
        "dba": "Pampas",
        "hq_country": "Argentina",
        "operating_territories": ["Latin America"],
        "product_categories": ["Resin Statues", "Premium Collectibles"],
        "manufacturing_capabilities": ["resin_casting", "cold_cast", "hand_finishing", "limited_runs"],
        "license_tier": "Tier 3 - Probation",
        "status": "pending_review",
        "annual_capacity_units": 90_000,
        "moq": 300,
        "lead_time_days": 85,
        "certifications": [],
        "compliance_rating": "C",
        "last_audit": "2026-02-10",
        "contact": {"name": "Sofía Giménez", "email": "s.gimenez@pampas.example", "phone": "+54-11-4300-5566"},
        "onboarded": "2025-01-19",
        "notes": "Buenos Aires. New onboarding under review; artisanal resin, low volume.",
    },
    "VND-1012": {
        "vendor_id": "VND-1012",
        "legal_name": "Taipei Precision Molding Co., Ltd.",
        "dba": "TPM",
        "hq_country": "Taiwan",
        "operating_territories": ["Asia-Pacific", "North America"],
        "product_categories": ["Vinyl Figures", "Blind Box", "Action Figures"],
        "manufacturing_capabilities": ["injection_molding", "soft_vinyl", "hand_painting", "tampo_printing", "packaging"],
        "license_tier": "Tier 1 - Approved",
        "status": "active",
        "annual_capacity_units": 2_600_000,
        "moq": 2_000,
        "lead_time_days": 52,
        "certifications": ["ISO 9001", "ASTM F963", "ICTI Ethical Toy"],
        "compliance_rating": "A",
        "last_audit": "2025-11-11",
        "contact": {"name": "Chen Yu-Ting", "email": "yt.chen@tpm.example", "phone": "+886-2-2700-3344"},
        "onboarded": "2021-06-30",
        "notes": "Taipei. High-capacity APAC vinyl + blind-box; also cleared for North America.",
    },
}

# ---------------------------------------------------------------------------
# TRADEMARKS — IP registrations per character/mark.
# ---------------------------------------------------------------------------
_TRADEMARKS: dict[str, dict] = {
    "grogu": {
        "mark": "GROGU",
        "character_id": "grogu",
        "owner": "Lucasfilm Ltd. LLC",
        "registration_number": "US-88765432",
        "nice_classes": ["Class 28 — Toys & Games", "Class 25 — Apparel", "Class 16 — Paper Goods"],
        "jurisdictions": {
            "North America": "registered",
            "Europe": "registered",
            "Asia-Pacific": "registered",
            "Latin America": "pending",
            "Middle East & Africa": "unregistered",
        },
        "registration_status": "Valid",
        "customs_recordation": {"US_CBP": True, "EU_customs": True, "JP_customs": True},
        "filed": "2020-01-10",
        "renewal_date": "2030-01-10",
        "status": "active",
    },
    "gremlins": {
        "mark": "GREMLINS / GIZMO",
        "character_id": "gremlins",
        "owner": "Warner Bros. Entertainment Inc.",
        "registration_number": "US-73512088",
        "nice_classes": ["Class 28 — Toys & Games", "Class 25 — Apparel", "Class 41 — Entertainment"],
        "jurisdictions": {
            "North America": "registered", "Europe": "registered", "Asia-Pacific": "registered",
            "Latin America": "registered", "Middle East & Africa": "unregistered",
        },
        "registration_status": "Valid",
        "customs_recordation": {"US_CBP": True, "EU_customs": True},
        "filed": "1984-05-01", "renewal_date": "2034-05-01", "status": "active",
    },
    "et": {
        "mark": "E.T. THE EXTRA-TERRESTRIAL",
        "character_id": "et",
        "owner": "Universal City Studios LLC",
        "registration_number": "US-73385112",
        "nice_classes": ["Class 28 — Toys & Games", "Class 16 — Paper Goods", "Class 41 — Entertainment"],
        "jurisdictions": {
            "North America": "registered", "Europe": "registered", "Asia-Pacific": "pending",
            "Latin America": "unregistered", "Middle East & Africa": "unregistered",
        },
        "registration_status": "Valid",
        "customs_recordation": {"US_CBP": True, "EU_customs": True},
        "filed": "1982-08-12", "renewal_date": "2032-08-12", "status": "active",
    },
    "stitch": {
        "mark": "STITCH",
        "character_id": "stitch",
        "owner": "Disney Enterprises, Inc.",
        "registration_number": "US-78402219",
        "nice_classes": ["Class 28 — Toys & Games", "Class 25 — Apparel", "Class 30 — Confectionery"],
        "jurisdictions": {
            "North America": "registered", "Europe": "registered", "Asia-Pacific": "registered",
            "Latin America": "registered", "Middle East & Africa": "registered",
        },
        "registration_status": "Valid",
        "customs_recordation": {"US_CBP": True, "EU_customs": True, "JP_customs": True},
        "filed": "2002-06-21", "renewal_date": "2032-06-21", "status": "active",
    },
    "little_green_men": {
        "mark": "LITTLE GREEN MEN (LGM)",
        "character_id": "little_green_men",
        "owner": "Disney Enterprises, Inc. / Pixar",
        "registration_number": "US-76550031",
        "nice_classes": ["Class 28 — Toys & Games", "Class 25 — Apparel"],
        "jurisdictions": {
            "North America": "registered", "Europe": "registered", "Asia-Pacific": "registered",
            "Latin America": "pending", "Middle East & Africa": "unregistered",
        },
        "registration_status": "Valid",
        "customs_recordation": {"US_CBP": True, "EU_customs": True},
        "filed": "1995-11-22", "renewal_date": "2035-11-22", "status": "active",
    },
    "minions": {
        "mark": "MINIONS",
        "character_id": "minions",
        "owner": "Universal City Studios LLC",
        "registration_number": "US-85678234",
        "nice_classes": ["Class 28 — Toys & Games", "Class 25 — Apparel", "Class 30 — Confectionery", "Class 09 — Video Games"],
        "jurisdictions": {
            "North America": "registered", "Europe": "registered", "Asia-Pacific": "registered",
            "Latin America": "registered", "Middle East & Africa": "registered",
        },
        "registration_status": "Valid",
        "customs_recordation": {"US_CBP": True, "EU_customs": True, "JP_customs": True},
        "filed": "2010-07-09", "renewal_date": "2030-07-09", "status": "active",
    },
}

# ---------------------------------------------------------------------------
# EXCLUSIVITY — active contracts locking a category to a partner in a territory.
# Exactly FOUR: one per region, each a different trademark, and every partner is
# a REGISTRY vendor (name + vendor_id match _VENDORS) so the data is coherent.
# ---------------------------------------------------------------------------
_EXCLUSIVITY: dict[str, dict] = {
    "EXC-4471": {
        "contract_id": "EXC-4471",
        "partner": "Liberty Figure Works LLC",
        "partner_vendor_id": "VND-1008",
        "character_id": "grogu",
        "category": "Vinyl Figures",
        "territory": "North America",
        "type": "exclusive",
        "effective": "2023-01-01",
        "expiration": "2028-12-31",
        "status": "active",
    },
    "EXC-5588": {
        "contract_id": "EXC-5588",
        "partner": "Kraków Vinyl Studio Sp. z o.o.",
        "partner_vendor_id": "VND-1006",
        "character_id": "gremlins",
        "category": "Vinyl Figures",
        "territory": "Europe",
        "type": "exclusive",
        "effective": "2023-01-01", "expiration": "2026-12-31", "status": "active",
    },
    "EXC-5333": {
        "contract_id": "EXC-5333",
        "partner": "Osaka Craft Works K.K.",
        "partner_vendor_id": "VND-1004",
        "character_id": "stitch",
        "category": "Vinyl Figures",
        "territory": "Asia-Pacific",
        "type": "exclusive",
        "effective": "2022-04-01", "expiration": "2029-03-31", "status": "active",
    },
    "EXC-5567": {
        "contract_id": "EXC-5567",
        "partner": "Amazônia Brinquedos Ltda.",
        "partner_vendor_id": "VND-1009",
        "character_id": "minions",
        "category": "Plush",
        "territory": "Latin America",
        "type": "exclusive",
        "effective": "2023-06-01", "expiration": "2028-05-31", "status": "active",
    },
}


# ---------------------------------------------------------------------------
# LICENSING CONTRACTS — vendor × character × category × territory agreements.
# Runtime-populated (created when a vendor is legally cleared for a category).
# ---------------------------------------------------------------------------
_CONTRACTS: dict[str, dict] = {}


# Licensor rate cards — the EXPECTED pricing the deal_pricing agent reconciles the vendor's
# agreed royalty/advance/MG against. Keyed by character_id (lowercase). Editable by hand.
_RATE_CARDS: dict[str, dict] = {
    "minions": {
        "property": "Minions",
        "character_tier": "A-list",
        "base_royalty_rate": 0.12,
        "category_modifier": {
            "vinyl figures": 1.15, "action figures": 1.15, "blind box": 1.10,
            "resin statues": 1.20, "premium collectibles": 1.20, "sofubi": 1.20,
            "novelty": 0.95, "plush": 0.90, "apparel": 1.0, "accessories": 1.0,
            "stationery": 0.95, "homeware": 1.0,
        },
        "territory_modifier": {"north america": 1.0, "europe": 1.05, "asia-pacific": 0.95},
        "volume_discount_tiers": [
            {"min_units": 0, "mult": 1.0},
            {"min_units": 50000, "mult": 0.95},
            {"min_units": 250000, "mult": 0.90},
        ],
        "min_royalty_rate": 0.08,
        "mg_rule": {"pct_of_projected_royalty": 0.50, "floor_usd": 100000},
        "advance_rule": {"pct_of_mg": 0.20},
        "tolerance_pct": 0.05,
    },
    "grogu": {
        "property": "Grogu (The Child)",
        "character_tier": "A-list",
        "base_royalty_rate": 0.14,
        "category_modifier": {
            "vinyl figures": 1.20, "action figures": 1.20, "blind box": 1.15,
            "resin statues": 1.25, "premium collectibles": 1.25, "sofubi": 1.25,
            "novelty": 0.95, "plush": 1.0, "apparel": 1.0, "accessories": 1.0,
            "stationery": 0.95, "homeware": 1.0,
        },
        "territory_modifier": {"north america": 1.0, "europe": 1.05, "asia-pacific": 1.0},
        "volume_discount_tiers": [
            {"min_units": 0, "mult": 1.0},
            {"min_units": 100000, "mult": 0.95},
        ],
        "min_royalty_rate": 0.10,
        "mg_rule": {"pct_of_projected_royalty": 0.50, "floor_usd": 150000},
        "advance_rule": {"pct_of_mg": 0.25},
        "tolerance_pct": 0.05,
    },
    # Lilo & Stitch — A-list evergreen; plush is the signature category and APAC is
    # the strongest territory (hence the premium there, mirroring the APAC exclusivity demand).
    "stitch": {
        "property": "Stitch (Lilo & Stitch)",
        "character_tier": "A-list",
        "base_royalty_rate": 0.13,
        "category_modifier": {
            "vinyl figures": 1.10, "action figures": 1.05, "blind box": 1.15,
            "resin statues": 1.15, "premium collectibles": 1.15, "sofubi": 1.20,
            "novelty": 1.0, "plush": 1.15, "apparel": 1.05, "accessories": 1.05,
            "stationery": 1.0, "homeware": 1.05,
        },
        "territory_modifier": {"north america": 1.0, "europe": 1.0, "asia-pacific": 1.10},
        "volume_discount_tiers": [
            {"min_units": 0, "mult": 1.0},
            {"min_units": 75000, "mult": 0.95},
            {"min_units": 300000, "mult": 0.90},
        ],
        "min_royalty_rate": 0.09,
        "mg_rule": {"pct_of_projected_royalty": 0.50, "floor_usd": 120000},
        "advance_rule": {"pct_of_mg": 0.25},
        "tolerance_pct": 0.05,
    },
    # Gremlins — cult/retro B-list; collector formats (resin/premium/action) carry a
    # premium, mass-market plush discounts, Europe strongest (EU collector base).
    "gremlins": {
        "property": "Gremlins",
        "character_tier": "B-list",
        "base_royalty_rate": 0.10,
        "category_modifier": {
            "vinyl figures": 1.10, "action figures": 1.15, "blind box": 1.05,
            "resin statues": 1.25, "premium collectibles": 1.25, "sofubi": 1.15,
            "novelty": 1.05, "plush": 0.85, "apparel": 0.95, "accessories": 0.95,
            "stationery": 0.90, "homeware": 0.95,
        },
        "territory_modifier": {"north america": 1.0, "europe": 1.05, "asia-pacific": 0.90},
        "volume_discount_tiers": [
            {"min_units": 0, "mult": 1.0},
            {"min_units": 50000, "mult": 0.95},
            {"min_units": 250000, "mult": 0.90},
        ],
        "min_royalty_rate": 0.07,
        "mg_rule": {"pct_of_projected_royalty": 0.50, "floor_usd": 75000},
        "advance_rule": {"pct_of_mg": 0.20},
        "tolerance_pct": 0.05,
    },
}


# ---------------------------------------------------------------------------
# Vendor store — Firestore-backed CRUD (collection `vendors`, doc id = VND-####)
# when FIRESTORE_DATABASE is set; `_VENDORS` above is the fallback AND the seed:
# an empty collection is auto-seeded with the defaults on first use, so the
# mesh migrates itself. Onboarded vendors/categories survive restarts this way.
# ---------------------------------------------------------------------------
_FIRESTORE_DB = os.environ.get("FIRESTORE_DATABASE", "").strip()
_VENDOR_COLLECTION = "vendors"
_fs_vendors = None  # lazy collection handle

# Pristine copy of the defaults, so vendor_reset() can restore them even in the
# in-memory fallback mode (where _VENDORS itself gets mutated).
import copy as _copy
_DEFAULT_VENDORS = _copy.deepcopy(_VENDORS)


def _vendors_fs():
    """The Firestore `vendors` collection (lazy client; seeds defaults if empty)."""
    global _fs_vendors
    if _fs_vendors is None:
        from google.cloud import firestore
        col = firestore.Client(database=_FIRESTORE_DB).collection(_VENDOR_COLLECTION)
        if next(iter(col.limit(1).stream()), None) is None:
            for vid, rec in _VENDORS.items():
                col.document(vid).set(rec)
            print(f"[mcp_licensing] seeded '{_VENDOR_COLLECTION}' with "
                  f"{len(_VENDORS)} default vendors", flush=True)
        _fs_vendors = col
    return _fs_vendors


def vendors_all() -> dict[str, dict]:
    """Every vendor record, keyed by id."""
    if _FIRESTORE_DB:
        try:
            return {d.id: d.to_dict() for d in _vendors_fs().stream()}
        except Exception as e:
            print(f"[mcp_licensing] Firestore vendors read failed "
                  f"({type(e).__name__}: {e}) — using in-memory fallback", flush=True)
    return _VENDORS


def vendor_get(vendor_id: str) -> dict | None:
    if _FIRESTORE_DB:
        try:
            doc = _vendors_fs().document(vendor_id).get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            print(f"[mcp_licensing] Firestore vendor_get({vendor_id}) failed "
                  f"({type(e).__name__}: {e}) — using in-memory fallback", flush=True)
    return _VENDORS.get(vendor_id)


def vendor_put(vendor_id: str, record: dict) -> None:
    """Create or replace a vendor record (create_vendor / update_vendor)."""
    if _FIRESTORE_DB:
        try:
            _vendors_fs().document(vendor_id).set(record)
            return
        except Exception as e:
            print(f"[mcp_licensing] Firestore vendor_put({vendor_id}) failed "
                  f"({type(e).__name__}: {e}) — writing in-memory only", flush=True)
    _VENDORS[vendor_id] = record


def vendor_reset() -> dict:
    """DEMO RESET: restore every default vendor to its pristine record and delete
    vendors created at runtime. Returns {'restored': n, 'deleted': n}."""
    deleted = 0
    if _FIRESTORE_DB:
        try:
            col = _vendors_fs()
            for doc in col.stream():
                if doc.id not in _DEFAULT_VENDORS:
                    col.document(doc.id).delete()
                    deleted += 1
            for vid, rec in _DEFAULT_VENDORS.items():
                col.document(vid).set(rec)
            print(f"[mcp_licensing] vendors reset to defaults "
                  f"({len(_DEFAULT_VENDORS)} restored, {deleted} deleted)", flush=True)
            return {"restored": len(_DEFAULT_VENDORS), "deleted": deleted}
        except Exception as e:
            print(f"[mcp_licensing] Firestore vendor_reset failed "
                  f"({type(e).__name__}: {e}) — resetting in-memory only", flush=True)
    for vid in [k for k in _VENDORS if k not in _DEFAULT_VENDORS]:
        del _VENDORS[vid]
        deleted += 1
    for vid, rec in _DEFAULT_VENDORS.items():
        _VENDORS[vid] = _copy.deepcopy(rec)
    return {"restored": len(_DEFAULT_VENDORS), "deleted": deleted}

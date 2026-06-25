import sys
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Legal & Compliance Registry")

@mcp.tool()
def query_style_guidelines(character_id: str) -> str:
    """
    Fetches authorized typography files, logo dimensions, and exact hex swatches 
    from the master franchise style registry.
    """
    guidelines = {
        "grogu": {
            "official_name": "The Child (Grogu)",
            "primary_logo_font": "Outfit-Bold",
            "allowed_fonts": ["Outfit", "Inter"],
            "hex_palette": ["#10b981", "#1e293b", "#ffffff"],
            "restricted_keywords": ["Baby Yoda"]
        }
    }
    return json.dumps(guidelines.get(character_id.lower(), {"error": "Character not found in style registry."}))

@mcp.tool()
def check_territorial_rights(partner_id: str, character_id: str) -> str:
    """
    Verifies if a manufacturer holds valid legal rights to distribute assets in a specific country.
    """
    # Simulate rights query.
    return json.dumps({
        "partner_id": partner_id,
        "character_id": character_id,
        "valid_territories": ["North America", "Europe", "Asia-Pacific"],
        "status": "Active"
    })

@mcp.tool()
def scan_global_exclusivity_clauses(character_id: str, territory: str) -> str:
    """
    Crawls active contracts to see if a competitor (e.g., Hasbro or Mattel) owns an 
    exclusive lock on that product category in that region.
    """
    # Simulate exclusivity checker
    if character_id.lower() == "grogu" and territory == "North America":
        return json.dumps({
            "has_conflict": True,
            "conflicting_partner": "Hasbro Inc.",
            "exclusivity_type": "Stylized Vinyl Figurines / Action Figures",
            "contract_expiration": "2028-12-31",
            "message": "Block release. Hasbro has exclusive rights for vinyl figures in North America."
        })
    return json.dumps({
        "has_conflict": False,
        "message": f"Territory {territory} is clear for category 'Stylized Vinyl Figurines' under franchise guidelines."
    })

@mcp.tool()
def verify_trademark_record(character_id: str) -> str:
    """
    Validates that the character's intellectual property registration is up to date 
    with border protection databases to prevent customs seizures.
    """
    return json.dumps({
        "character_id": character_id,
        "registration_status": "Valid",
        "customs_database_synced": True,
        "renewal_date": "2029-04-15"
    })

if __name__ == "__main__":
    mcp.run()

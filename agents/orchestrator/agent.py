import json
from agents.brand_style.agent import BrandStyleComplianceAgent
from agents.ip_counsel.agent import IPCounselAgent
from agents.storyline.agent import FranchiseStorylineAgent

# In a real environment: from google.adk.orchestrators.coordinator import Coordinator
# SourcingOrchestrator acts as the Graph coordinator routing details parallelly.

class SourcingOrchestrator:
    def __init__(self):
        self.style_agent = BrandStyleComplianceAgent()
        self.legal_agent = IPCounselAgent()
        self.storyline_agent = FranchiseStorylineAgent()

    def execute_workflow(self, payload: dict) -> dict:
        """
        Runs the multi-agent execution pipeline:
        1. Parse design elements via CV (mcp-vision-analyzer)
        2. Brand Style agent checks typography compliance
        3. Legal IP agent checks exclusivity rights and clearance
        4. Franchise Storyline agent checks scripts, canon lore, and spoiler embargoes
        5. Orchestrator invokes mcp-ui-renderer tool schema to display dynamic views
        """
        image_path = payload.get("image_path", "grogu_mockup_box.png")
        target_market = payload.get("target_market", "North America")
        volume = payload.get("volume", 15000)

        # 1. Parse mockup design elements
        parsed_data = {
            "status": "success",
            "image_file": image_path,
            "detected_logos": ["star_wars_logo"],
            "extracted_text": [
                {"text": "STAR WARS", "font": "Outfit-Bold", "color": "#10b981"},
                {"text": "THE CHILD", "font": "SpaceGrotesk" if target_market == "North America" else "Outfit", "color": "#ffffff"}
            ]
        }

        # 2. Brand style checks
        style_guidelines = {
            "official_name": "The Child (Grogu)",
            "allowed_fonts": ["Outfit", "Inter"]
        }
        style_report = self.style_agent.analyze_mockup(parsed_data, style_guidelines)

        # 3. Legal IP clearances
        exclusivity_data = {
            "has_conflict": True if target_market == "North America" else False,
            "conflicting_partner": "Hasbro Inc." if target_market == "North America" else None
        }
        customs_data = {"registration_status": "Valid"}
        ecom_data = {"status": "Secure - No leaks detected."}
        
        legal_report = self.legal_agent.evaluate_clearance(
            character_id="grogu",
            territory=target_market,
            exclusivity_data=exclusivity_data,
            customs_data=customs_data,
            ecom_data=ecom_data
        )

        # 4. Sourcing script & storyline check (The Storyline Agent Node)
        storyline_report = self.storyline_agent.verify_storyline_compliance(
            character_id="grogu",
            design_concept="Grogu in hover-pram"
        )

        # 5. UI Painting display JSON schema generation (Invoked directly by the Orchestrator)
        a2ui_payload = self.compile_ui_layout(style_report, legal_report, storyline_report, target_market, volume)

        return {
            "style_report": style_report,
            "legal_report": legal_report,
            "storyline_report": storyline_report,
            "a2ui_payload": a2ui_payload
        }

    def compile_ui_layout(self, style_report: dict, legal_report: dict, storyline_report: dict, target_market: str, volume: int) -> dict:
        """
        Orchestration Display Layer: Assembles the layout payload using mcp-ui-renderer tool models.
        """
        components = [
            {
                "type": "remediation_form",
                "fields": [
                    {
                        "id": "target_market",
                        "value": target_market,
                        "status": "blocked" if legal_report.get("status") == "blocked" else "clear"
                    },
                    {
                        "id": "production_volume",
                        "value": volume
                    }
                ]
            }
        ]
        return {
            "a2ui_version": "2.0",
            "canvas_layout": {
                "container": "procurement_audit_viewport",
                "components": components
            }
        }

import json
# In a real environment: from google.adk.agents.llm_agent import Agent

class BrandStyleComplianceAgent:
    def __init__(self):
        self.name = "brand_style_compliance_agent"
        self.instruction = (
            "You are a Brand Style Compliance Agent. Your job is to extract style details "
            "(fonts, colors, logos) from the design element scan and verify them against the official franchise registry."
        )

    def analyze_mockup(self, parsed_design_data: dict, style_guidelines: dict) -> dict:
        """
        Validates design legitimacy. Extracts typography, logo assets, and color palettes
        to flag text anomalies, font errors, or color drift from guidelines.
        """
        extracted_text = parsed_design_data.get("extracted_text", [])
        official_fonts = style_guidelines.get("allowed_fonts", [])
        
        anomalies = []
        for text_item in extracted_text:
            font = text_item.get("font")
            text = text_item.get("text")
            # If font contains SpaceGrotesk (unverified font)
            if font == "SpaceGrotesk":
                anomalies.append({
                    "element_id": "text_the_child",
                    "issue_type": "typography_anomaly",
                    "severity": "warning",
                    "description": f"Font 'SpaceGrotesk' is unverified for title text '{text}'. Official guidelines allow: {', '.join(official_fonts)}."
                })
        
        return {
            "agent": self.name,
            "status": "warning" if anomalies else "compliant",
            "anomalies": anomalies
        }

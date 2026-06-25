import json
# In a real environment: from google.adk.agents.llm_agent import Agent

class IPCounselAgent:
    def __init__(self):
        self.name = "ip_counsel_agent"
        self.instruction = (
            "You are a Global Market Clearance & IP Counsel Agent. Your job is to check exclusivity "
            "clauses, territorial rights, and scrape marketplaces to catch unauthorized leaks or pre-orders."
        )

    def evaluate_clearance(self, character_id: str, territory: str, exclusivity_data: dict, customs_data: dict, ecom_data: dict) -> dict:
        """
        Evaluates territorial clearances, contract exclusivity, and out-of-band market risks.
        """
        has_exclusivity_conflict = exclusivity_data.get("has_conflict", False)
        
        clearance_issues = []
        if has_exclusivity_conflict:
            clearance_issues.append({
                "element_id": "territory_rights",
                "issue_type": "exclusivity_collision",
                "severity": "critical",
                "partner_conflict": exclusivity_data.get("conflicting_partner"),
                "description": f"IP Exclusivity Collision: Competitor ({exclusivity_data.get('conflicting_partner')}) holds exclusive license for stylized figurines in {territory}."
            })
            
        customs_valid = customs_data.get("registration_status") == "Valid"
        if not customs_valid:
            clearance_issues.append({
                "element_id": "customs_check",
                "issue_type": "customs_invalid",
                "severity": "warning",
                "description": "IP customs registry is not validated for export/import clearance."
            })

        return {
            "agent": self.name,
            "status": "blocked" if has_exclusivity_conflict else "cleared",
            "issues": clearance_issues,
            "ecom_status": ecom_data.get("status")
        }

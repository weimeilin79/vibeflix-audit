output "mcp_urls" {
  description = "Env contract for the agents phase (streamable-HTTP MCP endpoints)"
  value = {
    MCP_LICENSING_URL   = "${google_cloud_run_v2_service.mcp["licensing"].uri}/mcp"
    MCP_MARKET_URL      = "${google_cloud_run_v2_service.mcp["market"].uri}/mcp"
    MCP_BRAND_STYLE_URL = "${google_cloud_run_v2_service.mcp["brand_style"].uri}/mcp"
  }
}

output "runtime_service_accounts" {
  value = {
    licensing_rw = google_service_account.mcp_rw.email
    readonly     = google_service_account.mcp_ro.email
  }
}

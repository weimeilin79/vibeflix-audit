output "agents_service_account" {
  value = google_service_account.agents.email
}

output "app_service_account" {
  value = google_service_account.app.email
}

output "app_pubsub_subscription" {
  value = google_pubsub_subscription.app_cloud.name
}

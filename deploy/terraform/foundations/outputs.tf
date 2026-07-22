output "artifact_registry" {
  description = "Full Artifact Registry path (REGION-docker.pkg.dev/PROJECT/REPO) that every image build pushes to."
  value       = "${var.region}-docker.pkg.dev/${var.project}/${google_artifact_registry_repository.vibeflix.repository_id}"
}

output "pubsub_topic" {
  description = "Telemetry topic name — feed to PUBSUB_TOPIC and the mcp/agents modules' -var pubsub_topic."
  value       = google_pubsub_topic.telemetry.name
}

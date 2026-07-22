variable "project" {
  type        = string
  description = "GCP project id."
}

variable "region" {
  type        = string
  description = "Region for the Artifact Registry repo (e.g. us-central1)."
}

variable "ar_repo_id" {
  type        = string
  description = "Artifact Registry repository id (the image-path segment; images live at REGION-docker.pkg.dev/PROJECT/<this>)."
  default     = "vibeflix"
}

variable "pubsub_topic" {
  type        = string
  description = "Telemetry Pub/Sub topic name. MUST match PUBSUB_TOPIC in deploy/.env (default there is the same)."
  default     = "vibeflix-mesh-events"
}

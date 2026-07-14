variable "project" {
  description = "GCP project id"
  type        = string
  # No default — a hardcoded project id silently deploys to the wrong place.
}

variable "region" {
  description = "Cloud Run / Artifact Registry region"
  type        = string
  default     = "us-central1"
}

variable "firestore_database" {
  description = "Named Firestore db holding registries + vendors + audit history"
  type        = string
  default     = "vibeflix-registry"
}

variable "pubsub_topic" {
  description = "Live mesh-telemetry topic the MCP tools publish to"
  type        = string
  default     = "vibeflix-mesh-events"
}

variable "deployer" {
  description = "Human IAM member granted run.invoker for verification (e.g. user:me@example.com)"
  type        = string
}

variable "invoker_members" {
  description = "Additional IAM members granted run.invoker on every MCP service (the agents' runtime SA is added here in the agents phase)"
  type        = list(string)
  default     = []
}

variable "image_tag" {
  description = "Image tag to deploy (builds push :latest)"
  type        = string
  default     = "latest"
}

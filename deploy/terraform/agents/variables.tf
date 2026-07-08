variable "project" {
  type    = string
  default = "pokedemo-test"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "pubsub_topic" {
  type    = string
  default = "vibeflix-mesh-events"
}

variable "upload_bucket" {
  description = "Vendor image-upload bucket (the app writes + reset-cleans it)"
  type        = string
  default     = "vibeflix-request-image"
}

variable "asset_buckets" {
  description = "Buckets holding licensed artwork the agents pass to Gemini by gs:// reference"
  type        = list(string)
  default     = ["vibeflix-request-image", "vibeflix-approved-assets"]
}

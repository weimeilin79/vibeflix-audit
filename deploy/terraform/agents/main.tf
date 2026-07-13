# Agent tier — cloud phase 2 of the Vibeflix audit mesh (IAM only).
#
# The reasoning-engine DEPLOYS are source pushes done by deploy/deploy_agents.sh
# (Agent Runtime is source-based; its code artifact doesn't belong in Terraform
# state). This module owns the durable part: the runtime identities and their
# least-privilege grants.
#
#   vibeflix-agents  — shared runtime SA for the 5 agents on Agent Runtime
#                      (upgrade path: per-agent Agent Identity, preview)
#   vibeflix-app     — the console app on Cloud Run (frontend + orchestrator)

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project
  region  = var.region
}

resource "google_service_account" "agents" {
  account_id   = "vibeflix-agents"
  display_name = "Vibeflix agents (Agent Runtime runtime identity)"
}

resource "google_service_account" "app" {
  account_id   = "vibeflix-app"
  display_name = "Vibeflix console app (Cloud Run)"
}

# ---------------------------------------------------------------------------
# Agents: Gemini + RAG retrieval (legal) via Vertex; telemetry publish.
# MCP access is NOT granted here — it goes through the Agent Gateway
# (or, pre-gateway, via terraform/mcp var.invoker_members).
# ---------------------------------------------------------------------------
resource "google_project_iam_member" "agents_vertex" {
  project = var.project
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agents.email}"
}

resource "google_pubsub_topic_iam_member" "agents_publisher" {
  topic  = var.pubsub_topic
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.agents.email}"
}

# Licensed-asset buckets: brand_style passes gs:// images to Gemini by reference.
resource "google_storage_bucket_iam_member" "agents_assets" {
  for_each = toset(var.asset_buckets)
  bucket   = each.value
  role     = "roles/storage.objectViewer"
  member   = "serviceAccount:${google_service_account.agents.email}"
}

# ---------------------------------------------------------------------------
# App: queries the reasoning engines (A2A), owns audit history + uploads,
# pulls its OWN telemetry subscription, publishes its own node events.
# ---------------------------------------------------------------------------
resource "google_project_iam_member" "app_vertex" {
  project = var.project
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_datastore" {
  project = var.project
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# The app resolves ui_renderer through the Agent Registry (list_agents).
resource "google_project_iam_member" "app_agentregistry" {
  project = var.project
  role    = "roles/agentregistry.viewer"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# ---------------------------------------------------------------------------
# Agent IDENTITIES (principalSet) — the engines run as their own agent-identity
# principals (identity_type=AGENT_IDENTITY), NOT the `agents` SA. These grants
# are what actually let them call Gemini, read the registry, and publish.
# ---------------------------------------------------------------------------
data "google_project" "this" { project_id = var.project }

locals {
  agents_set = "principalSet://agents.global.org-${var.org_id}.system.id.goog/attribute.platformContainer/aiplatform/projects/${data.google_project.this.number}"
}

resource "google_project_iam_member" "agents_identity_roles" {
  for_each = toset([
    "roles/aiplatform.expressUser",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/browser",
    "roles/agentregistry.viewer", # callers list the registry to resolve engines
  ])
  project = var.project
  role    = each.value
  member  = local.agents_set
}

resource "google_storage_bucket_iam_member" "app_uploads" {
  bucket = var.upload_bucket
  role   = "roles/storage.objectAdmin" # upload + reset-time cleanup
  member = "serviceAccount:${google_service_account.app.email}"
}

resource "google_pubsub_topic_iam_member" "app_publisher" {
  topic  = var.pubsub_topic
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.app.email}"
}

# The cloud app gets its OWN pull subscription (the local dev bridge keeps
# vibeflix-mesh-events-app; two bridges on one subscription steal each other's events).
resource "google_pubsub_subscription" "app_cloud" {
  name                       = "${var.pubsub_topic}-app-cloud"
  topic                      = var.pubsub_topic
  ack_deadline_seconds       = 10
  message_retention_duration = "600s"
  expiration_policy {
    ttl = "" # never expires
  }
}

resource "google_pubsub_subscription_iam_member" "app_subscriber" {
  subscription = google_pubsub_subscription.app_cloud.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.app.email}"
}

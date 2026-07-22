# Foundations tier — the shared, declarative infrastructure the rest of the mesh builds on:
# the container image registry and the telemetry Pub/Sub topic. Apply this FIRST, before any
# image build (MCP or app) and before the mcp/agents modules.
#
#   terraform -chdir=deploy/terraform/foundations init
#   terraform -chdir=deploy/terraform/foundations apply -var project=$PROJECT -var region=$REGION
#
# Deliberately NOT owned here (see README):
#   • Firestore database — stateful, one-per-project, mode is irreversible, and it needs
#     app-level SEEDING (seed_firestore.py). Owned by deploy/setup_firestore.sh, so Terraform
#     never risks destroying a live data store.
#   • Pub/Sub SUBSCRIPTIONS — the cloud app's is owned by terraform/agents
#     (`${topic}-app-cloud`); the local bridge is created by setup_pubsub.sh.
#   • API enablement — done once by the runbook's `gcloud services enable` block (Step 1).

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

# The one Docker repo every image (MCP + app) is pushed to. Previously created ad hoc by
# BOTH deploy_mcp_cloudrun.sh and terraform/mcp; owned here now so the APP build no longer
# implicitly depends on the MCP step having run first.
resource "google_artifact_registry_repository" "vibeflix" {
  location      = var.region
  repository_id = var.ar_repo_id
  format        = "DOCKER"
  description   = "Vibeflix audit mesh images"
}

# The single telemetry topic every emitter (agents, MCP servers, app) publishes onto and the
# app subscribes to (event schema documented in deploy/setup_pubsub.sh). Was created by
# setup_pubsub.sh; that script now only creates the local bridge subscription + smoke test.
resource "google_pubsub_topic" "telemetry" {
  name = var.pubsub_topic
}

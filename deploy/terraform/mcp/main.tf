# MCP tier — cloud phase 1 of the Vibeflix audit mesh.
#
# Three streamable-HTTP MCP servers on Cloud Run, IAM-gated (no public access),
# with least-privilege runtime identities:
#
#   vibeflix-mcp-licensing    SA vibeflix-mcp-licensing  Firestore READ/WRITE
#                             (vendors CRUD)             + Pub/Sub publish (topic-scoped)
#   vibeflix-mcp-market       SA vibeflix-mcp-readonly   Firestore READ-ONLY
#   vibeflix-mcp-brand-style  SA vibeflix-mcp-readonly   + Pub/Sub publish (topic-scoped)
#
# Deliberately NO GCS and NO Vertex bindings — the MCP servers use neither.
# Images are built OUTSIDE Terraform (gcloud builds submit, deploy/cloudbuild-mcp.yaml)
# and referenced here by tag. Apply via deploy/deploy_mcp_cloudrun.sh.
#
# Cloud-readiness caveat (accepted for the demo): mcp_licensing keeps
# trademarks/exclusivity/CONTRACTS in-memory → max_instance_count = 1 (single
# writer); executed contracts still reset on instance recycle (the app's audit
# history snapshots them). Durable fix later: move _CONTRACTS to Firestore.

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

locals {
  # The `vibeflix` repo is owned by terraform/foundations now — reference it by name.
  ar = "${var.region}-docker.pkg.dev/${var.project}/vibeflix"

  services = {
    licensing = {
      name  = "vibeflix-mcp-licensing"
      image = "${local.ar}/mcp-licensing:${var.image_tag}"
      sa    = google_service_account.mcp_rw.email
      max   = 1 # in-memory contract store — single writer
    }
    market = {
      name  = "vibeflix-mcp-market"
      image = "${local.ar}/mcp-market:${var.image_tag}"
      sa    = google_service_account.mcp_ro.email
      max   = 2
    }
    brand_style = {
      name  = "vibeflix-mcp-brand-style"
      image = "${local.ar}/mcp-brand-style:${var.image_tag}"
      sa    = google_service_account.mcp_ro.email
      max   = 2
    }
  }

  invokers = concat([var.deployer], var.invoker_members)
}

# ---------------------------------------------------------------------------
# Image registry — MOVED to terraform/foundations (google_artifact_registry_repository.vibeflix).
# On an already-applied deployment, drop it from THIS module's state so apply doesn't try to
# destroy the repo (and its images):
#   terraform -chdir=deploy/terraform/mcp state rm google_artifact_registry_repository.vibeflix
# See deploy/terraform/foundations/README.md.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Runtime identities + least-privilege grants
# ---------------------------------------------------------------------------
resource "google_service_account" "mcp_rw" {
  account_id   = "vibeflix-mcp-licensing"
  display_name = "Vibeflix MCP (licensing — Firestore read/write)"
}

resource "google_service_account" "mcp_ro" {
  account_id   = "vibeflix-mcp-readonly"
  display_name = "Vibeflix MCP (market/brand_style — Firestore read-only)"
}

# Firestore: licensing writes (vendors CRUD); the others only read registries.
resource "google_project_iam_member" "rw_datastore" {
  project = var.project
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.mcp_rw.email}"
}

resource "google_project_iam_member" "ro_datastore" {
  project = var.project
  role    = "roles/datastore.viewer"
  member  = "serviceAccount:${google_service_account.mcp_ro.email}"
}

# Pub/Sub telemetry: publisher on THIS topic only — not project-wide.
resource "google_pubsub_topic_iam_member" "publisher" {
  for_each = {
    rw = google_service_account.mcp_rw.email
    ro = google_service_account.mcp_ro.email
  }
  topic  = var.pubsub_topic
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${each.value}"
}

# ---------------------------------------------------------------------------
# Cloud Run services (IAM-gated; callers need run.invoker + an ID token)
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "mcp" {
  for_each = local.services

  name                = each.value.name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = each.value.sa
    # 1800s, not Cloud Run's 300s default.
    #
    # MCP streamable-http holds a LONG-LIVED SSE GET stream open for the whole session. An
    # agent that reasons for minutes between tool calls — legal does RAG plus several model
    # calls — keeps that stream open past 300s, at which point Cloud Run severs it. The client
    # then reconnects ("GET stream disconnected, reconnecting in 1000ms..."), re-handshakes,
    # re-mints its token, and can 401 on the way back in. Observed on vibeflix-demo: legal
    # looping on exactly that for 10+ minutes without ever reaching a model call, which read as
    # a hung onboarding workflow.
    #
    # The tool CALLS are fast; it is the idle session that outlives the default.
    timeout         = "1800s"

    scaling {
      min_instance_count = 0
      max_instance_count = each.value.max
    }

    containers {
      image = each.value.image

      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }

      env {
        name  = "MCP_TRANSPORT"
        value = "streamable-http"
      }
      env {
        name  = "HOST"
        value = "0.0.0.0"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project
      }
      env {
        name  = "FIRESTORE_DATABASE"
        value = var.firestore_database
      }
      env {
        name  = "PUBSUB_TOPIC"
        value = var.pubsub_topic
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = {
    for pair in setproduct(keys(local.services), local.invokers) :
    "${pair[0]}/${pair[1]}" => { service = pair[0], member = pair[1] }
  }

  name     = google_cloud_run_v2_service.mcp[each.value.service].name
  location = var.region
  role     = "roles/run.invoker"
  member   = each.value.member
}

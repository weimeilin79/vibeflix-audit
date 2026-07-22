# terraform/foundations

The shared infrastructure every other tier depends on, owned declaratively:

| Resource | Was |
|---|---|
| `google_artifact_registry_repository.vibeflix` — the Docker repo all MCP + app images push to | created by `deploy_mcp_cloudrun.sh` **and** `terraform/mcp` |
| `google_pubsub_topic.telemetry` — the one mesh-telemetry topic | created by `setup_pubsub.sh` |

Apply it **first** — before any image build and before the `mcp` / `agents` modules — so the
app build no longer implicitly depends on the MCP step having run.

## Fresh project

```bash
terraform -chdir=deploy/terraform/foundations init
terraform -chdir=deploy/terraform/foundations apply \
  -var project=$PROJECT -var region=$REGION \
  -var pubsub_topic=${PUBSUB_TOPIC:-vibeflix-mesh-events}
```

Then continue with `setup_firestore.sh` (Firestore stays shell — it's stateful and needs
seeding), `setup_pubsub.sh` (now only the subscription + smoke test), and the rest of the
runbook.

## Migrating an EXISTING deployment (pokedemo-test, etc.)

The repo and topic already exist and were owned elsewhere, so **adopt them — do not
recreate**. Otherwise `terraform/mcp` would try to *destroy* the repo (deleting every image)
and this module's apply would fail with "already exists".

```bash
# 1. Drop the repo from terraform/mcp's state (leaves the real repo + images untouched):
terraform -chdir=deploy/terraform/mcp state rm google_artifact_registry_repository.vibeflix

# 2. Import the existing repo + topic into THIS module's state:
terraform -chdir=deploy/terraform/foundations init
terraform -chdir=deploy/terraform/foundations import \
  google_artifact_registry_repository.vibeflix \
  projects/$PROJECT/locations/$REGION/repositories/vibeflix
terraform -chdir=deploy/terraform/foundations import \
  google_pubsub_topic.telemetry \
  projects/$PROJECT/topics/${PUBSUB_TOPIC:-vibeflix-mesh-events}

# 3. Confirm a no-op plan (nothing created/destroyed):
terraform -chdir=deploy/terraform/foundations plan \
  -var project=$PROJECT -var region=$REGION \
  -var pubsub_topic=${PUBSUB_TOPIC:-vibeflix-mesh-events}
```

A clean `plan` at step 3 (0 to add, 0 to change, 0 to destroy) means ownership has moved
without touching the live resources.

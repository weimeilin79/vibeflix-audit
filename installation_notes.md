# Vibeflix Deployment: Installation Friction Points & Fixes

> [!IMPORTANT]
> The original codebase was reverted to its pristine state. To successfully deploy the Vibeflix multi-agent mesh on a fresh GCP project, you **must make the following changes** to the respective codebase files as described below.

## Summary of Required Gaps & Patches
* **Serverless RAG Mode**: The RAG setup scripts lacked serverless mode configuration, requiring a manual REST API PATCH to enable it.
* **Missing Artifact Registry**: No script created the Artifact Registry Docker repository (vibeflix) before pushing images, causing circular dependencies in Terraform. We manually created the repository and imported it.
* **Approved Assets Bucket Name Conflict**: Since `gs://vibeflix-approved-assets` was globally taken, we created a project-prefixed bucket and updated the Firestore registry document accordingly.
* **Agent Gateway Dependency**: The deployment scripts had a circular dependency expecting the gateway to exist during Pass 1 engine creation. We resolved this by building the gateway early in the process.
* **JSON Contamination**: Logging outputs in `cloud_auth.py` contaminated tool spec JSON files redirected during registration. We redirected these logs to `sys.stderr` so that tool specs generate cleanly.
* **KeyErrors & Vertex Validation Errors**: Fixed crashes in `deploy_agents_a2a.py` due to missing agent keys in the first pass and added env var filtering to prevent Vertex AI 400 BadRequest validation errors on empty strings.

---

## Detailed Issues and Resolutions


## 1. Capacity Limits on RAG Engine (Spanner Mode) in `us-central1`
* **Symptom:** RAG corpus creation failed with `400 INVALID_ARGUMENT`. The error message indicated that Spanner mode is capacity-restricted for new projects in `us-central1`.
* **Root Cause:** By default, the project RAG engine configuration uses Spanner mode.
* **Resolution:** Switched the project's RAG configuration to **Serverless mode** in the region `us-central1` by making a direct `PATCH` REST API call to the Vertex AI location endpoint:
  ```json
  PATCH https://us-central1-aiplatform.googleapis.com/v1beta1/projects/vibeflix-test-1/locations/us-central1/ragEngineConfig
  {
    "ragManagedDbConfig": {
      "serverless": {}
    }
  }
  ```

---

## 2. Invalid Billing/Quota Project in Application Default Credentials (ADC)
* **Symptom:** Bucket ownership verification failed during RAG corpus creation.
* **Root Cause:** The local `application_default_credentials.json` had its `quota_project_id` set to `io26-keynote-demo-starter`, a project which has been deleted. This caused all API calls routing through Google client libraries (such as the Cloud Resource Manager API) to fail with a `PermissionDenied` exception because the billing project could not be found.
* **Resolution:** Set the active ADC quota project to `vibeflix-test-1` by running:
  ```bash
  gcloud auth application-default set-quota-project vibeflix-test-1
  ```

---

## 3. Missing Cloud Resource Manager API in Target Project
* **Symptom:** Even after fixing the ADC quota project, python's RAG SDK still returned `ValueError: Bucket does not belong to project vibeflix-test-1` when verifying bucket ownership.
* **Root Cause:** The bucket ownership check (`_verify_bucket_ownership`) internally queries the Resource Manager API (`resourcemanager_v3.ProjectsClient().get_project()`) to map the project ID to a project number. The API was disabled in the new project `vibeflix-test-1`.
* **Resolution:** Enabled the Resource Manager API:
  ```bash
  gcloud services enable cloudresourcemanager.googleapis.com --project=vibeflix-test-1
  ```

---

## 4. Missing Artifact Registry Repository
* **Symptom:** Cloud Build failed during container upload with `name unknown: Repository "vibeflix" not found`.
* **Root Cause:** The `deploy_mcp_cloudrun.sh` script attempts to push images to an Artifact Registry repository named `vibeflix` under the project, but the repository was never created by any script in the workflow.
* **Resolution:** Created the repository manually:
  ```bash
  gcloud artifacts repositories create vibeflix --repository-format=docker --location=us-central1 --project=vibeflix-test-1 --description="Vibeflix Docker repository"
  ```

---

## 5. Global Approved Assets Bucket Conflict
* **Symptom:** Creating the bucket `gs://vibeflix-approved-assets` failed with `HTTPError 409: The requested bucket name is not available` because GCS bucket names are globally unique and it was already taken.
* **Root Cause:** The default bucket name is hardcoded or set as default in several places.
* **Resolution:** Created a project-prefixed bucket `gs://vibeflix-test-1-approved-assets` and updated the `brand_style_registry/approved_sources` document in the Firestore `vibeflix-registry` database to include `gs://vibeflix-test-1-approved-assets/`.

---

## 6. KeyError on Missing Agent Identities in `deploy_agents_a2a.py`
* **Symptom:** Running `deploy_agents_a2a.py vendor_clearance` crashed with `KeyError: 'vibeflix-vendor-clearance'`.
* **Root Cause:** The script assumed all agent identities were already present in `agent_identities.json` when setting A2A URLs, which is not true for a fresh deployment before all engines have been created.
* **Resolution:** Patched `deploy/deploy_agents_a2a.py` to check if keys exist in the `identities` dictionary before resolving their A2A URLs.

---

## 7. Vertex AI Validation Error on Empty Environment Variables
* **Symptom:** Deploying the reasoning engines in Pass 1 failed with `400 INVALID_ARGUMENT: Field: reasoning_engine.spec.deployment_spec.env[6].value; Message: Required field is not set.`.
* **Root Cause:** `deploy_agents_a2a.py` passed `TASK_STORE_URL` as an empty string `""` on Pass 1 (since the console app was not yet deployed). Vertex AI rejects empty string values for environment variables.
* **Resolution:** Patched `deploy/deploy_agents_a2a.py` to filter out any environment variables with empty string values before passing them to the Vertex config:
  ```python
  env = {k: v for k, v in env.items() if v != ""}
  ```

---

## 8. Circular Dependency on Agent Gateway
* **Symptom:** Deploying engines in Pass 1 failed because the `agent_gateway_config` pointed to the Agent Gateway `vibeflix-gateway` which did not exist yet (as the gateway is created in Step 5 of the runbook, after the app is up).
* **Root Cause:** The deployment config in `deploy_agents_a2a.py` hardcodes attaching the engine to the gateway at create time.
* **Resolution:** Provisioned the Agent Gateway early by executing the gateway creation step:
  ```bash
  ./deploy/setup_gateway.sh gateway
  ```

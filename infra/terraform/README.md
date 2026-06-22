# Terraform — GCP infrastructure (Phase 1)

Flat Terraform root. There are **no modules**: each resource type is created a
fixed, small number of times, so a flat layout split by concern is clearer than
module indirection. Files:

| File | Resources |
|------|-----------|
| `versions.tf`  | Terraform + provider pins; provider config (`default_labels`) |
| `backend.tf`   | GCS remote-state backend (partial config) |
| `backend.hcl`  | State bucket name, supplied at `init` |
| `variables.tf` | All inputs |
| `gcs.tf`       | Bronze landing bucket + lifecycle |
| `bigquery.tf`  | Datasets `raw`, `staging`, `marts`, `dbt_ci` (`for_each`) |
| `iam.tf`       | Pipeline service account + least-privilege bindings |
| `composer.tf`  | Composer 2 env — **gated off** (`enable_composer`, Phase 4) |
| `outputs.tf`   | Bucket name, dataset ids, SA email, Airflow URI |
| `dev.tfvars`   | `dev` environment values |

Run all commands from the repo root via `make tf-*`, or `cd` here and use
`terraform` directly.

## One-time bootstrap (chicken-and-egg: state bucket first)

Terraform cannot create the bucket that stores its own state, so create it by
hand once:

```bash
# 1. Auth + select the project
gcloud auth login
gcloud auth application-default login
gcloud config set project <PROJECT_ID>

# 2. Enable the APIs this stack needs
gcloud services enable \
  bigquery.googleapis.com \
  composer.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  monitoring.googleapis.com

# 3. Create the remote-state bucket (versioned, uniform access)
gcloud storage buckets create gs://<PROJECT_ID>-tf-state \
  --location=us-central1 \
  --uniform-bucket-level-access
gcloud storage buckets update gs://<PROJECT_ID>-tf-state --versioning
```

Then point Terraform at it:

- `backend.hcl` → set `bucket = "<PROJECT_ID>-tf-state"`
- `dev.tfvars`  → set `project_id = "<PROJECT_ID>"`

## Apply

```bash
make tf-init     # terraform init -backend-config=backend.hcl
make tf-plan     # review the plan (no Composer resources while the flag is off)
make tf-apply    # stand up bucket + 4 datasets + SA + IAM
make tf-destroy  # clean teardown (dev force-destroy is on)
```

## Enabling Composer (Phase 4)

```bash
gcloud composer images list --location=us-central1   # pick a current image
```

In `dev.tfvars` set `composer_image_version` to that value and
`enable_composer = true`, then `make tf-plan && make tf-apply`.

## Secrets

No secrets live in Terraform or `*.tfvars`. The NASS API key is stored in Secret
Manager; the pipeline SA is granted `secretmanager.secretAccessor` here so it can
read the key at runtime.

# Phase 1 — Tasks

Atomic tasks for the flat Terraform root. All files live in `infra/terraform/`.

| # | Task | Files | Depends on | Done when |
|---|------|-------|-----------|-----------|
| T1 | Version + provider pins, partial backend | `versions.tf`, `backend.tf`, `backend.hcl` | — | `init -backend=false` resolves provider |
| T2 | Input variables | `variables.tf` | — | all vars typed + described |
| T3 | Bronze bucket + lifecycle | `gcs.tf` | T2 | bucket, UBLA, lifecycle, force_destroy var |
| T4 | Datasets via `for_each` | `bigquery.tf` | T2 | 4 datasets, dbt_ci 7-day expiry |
| T5 | Pipeline SA + least-privilege IAM | `iam.tf` | T3, T4 | SA + jobUser + per-dataset editor + bucket objectAdmin + secretAccessor |
| T6 | Composer env (gated, count=0) | `composer.tf` | T2, T5 | gated by `enable_composer`; no fabricated image |
| T7 | Outputs | `outputs.tf` | T3–T6 | bucket, dataset ids, SA email, airflow URI |
| T8 | Dev values | `dev.tfvars` | T2 | project_id placeholder, region, dev force-destroy, composer off |
| T9 | Repo glue | root `.gitignore`, `Makefile`, `infra/terraform/README.md`; remove `modules/` | T1–T8 | tf-* make targets; TF ignores; bootstrap doc; modules/ gone |
| T10 | Verify | — | T1–T9 | `fmt -check`, `validate` green; lock file generated |

## Manual bootstrap (user, outside Terraform — needs GCP)

1. `gcloud auth login` + `gcloud config set project <project_id>`.
2. Enable APIs: bigquery, composer, storage, artifactregistry, secretmanager,
   monitoring.
3. Create the **state bucket** (versioning + UBLA), then put its name in
   `backend.hcl`.
4. Put the real `project_id` in `dev.tfvars`.
5. `make tf-init && make tf-plan` → review → `make tf-apply`.

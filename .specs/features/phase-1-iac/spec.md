# Phase 1 — Infrastructure as Code (Terraform)

Provision all GCP resources for the weather × crop-yield warehouse reproducibly
from a single **flat** Terraform root at `infra/terraform/`, with remote state in
GCS. A fresh `apply` stands up the `dev` environment; `destroy` tears it down
cleanly. No secrets in state-tracked files.

Companion: [docs/IMPLEMENTATION_PLAN.md](../../../docs/IMPLEMENTATION_PLAN.md) §Phase 1.

## In scope

- Remote state backend (GCS, partial config; state bucket created manually).
- GCS bronze landing bucket with lifecycle expiry.
- BigQuery datasets `raw`, `staging`, `marts`, `dbt_ci` (`US` multi-region).
- Pipeline service account + least-privilege IAM.
- Composer 2 environment — written but **gated behind `enable_composer=false`**
  (deferred to Phase 4; Composer is the largest fixed cost).
- `dev` environment via `dev.tfvars`.

## Out of scope

- `prod` environment / tfvars (later).
- Artifact Registry (only if ingestion is containerized — MVP skip).
- Workload Identity Federation for CI (Phase 6).
- Creating the NASS secret itself (Phase 0/2); IAM accessor is granted here.

## Requirements

### Backend & layout

- **FR-1** Flat root at `infra/terraform/`, files split by concern. No Terraform
  modules; the empty `modules/` tree is removed.
- **FR-2** Remote state in GCS via **partial** backend config — `backend.hcl`
  supplies the (manually created) bucket; `prefix` namespaces state. GCS backend
  gives state locking for free.
- **FR-3** `terraform` and provider versions pinned (`versions.tf`).

### GCS

- **FR-4** One bronze bucket `<project_id>-bronze`, location `var.region`, uniform
  bucket-level access, public access prevention enforced.
- **FR-5** Lifecycle rule deletes objects older than `var.bronze_retention_days`
  (default 365).
- **FR-6** `force_destroy` controllable via var (dev=true for clean teardown).

### BigQuery

- **FR-7** Datasets created via `for_each` over a typed map; location
  `var.bq_location` (`US`).
- **FR-8** Warehouse datasets have no default table expiration; `dbt_ci` expires
  tables after 7 days.
- **FR-9** `delete_contents_on_destroy` controllable via var (dev=true).

### IAM (least privilege)

- **FR-10** One pipeline service account (`var.pipeline_sa_account_id`).
- **FR-11** BigQuery: **project-level** `jobUser`; **dataset-level** `dataEditor`
  on each dataset (not project-wide).
- **FR-12** GCS: `objectAdmin` on the **bronze bucket only** (not project-wide).
- **FR-13** Secret Manager: project-level `secretAccessor` (scope to the NASS
  secret in Phase 4 once it exists).
- **FR-14** Bindings use additive `*_iam_member` — never authoritative
  `*_iam_binding`/`*_iam_policy`.

### Composer (deferred)

- **FR-15** `composer.tf` defines a Composer 2 env, gated by
  `count = var.enable_composer ? 1 : 0`; default false.
- **FR-16** Uses the pipeline SA as the environment service account;
  `image_version` has **no default** — must be set & verified before enabling.
- **FR-17** `composer.worker` granted to the pipeline SA only when enabled.

### Outputs

- **FR-18** Outputs expose bronze bucket name, dataset ids (map), pipeline SA
  email, and Composer Airflow URI (null when disabled).

## Verification (DoD)

- **V-1** `terraform fmt -check` passes.
- **V-2** `terraform init -backend=false && terraform validate` passes.
- **V-3** With a real `project_id`, `terraform plan` shows bucket + 4 datasets +
  SA + IAM and **no Composer resources** (flag off).
- **V-4** `.terraform.lock.hcl` committed; no `*.tfstate` or secrets tracked.
- **V-5** *(manual, needs GCP)* `apply` stands up the stack; `destroy` is clean.

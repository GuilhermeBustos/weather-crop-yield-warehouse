# Airflow / Cloud Composer

DAGs for the `wcy` pipeline. They live in `airflow/dags/` and are deployed to a
**ephemeral** Cloud Composer 3 environment (Airflow 3.1.7). Composer is only
provisioned to prove the end-to-end run, then torn down to avoid ongoing cost
(~$300+/month while up).

## Local DAG validation

Validates every DAG file in `airflow/dags/` locally — no Composer required.
Uses Airflow's `DagBag` to parse and report import errors.

```bash
make dags-validate
```

The `airflow` dependency group must be available. `uv run --group airflow`
resolves it automatically, but you can pre-install for faster feedback:

```bash
uv sync --group airflow
```

## Deploying to Composer

### Prerequisites

1. Composer environment is up (`make composer-up` or verified running).
2. dbt packages are installed locally so they are included in the sync:
   ```bash
   make dbt-deps
   ```
3. The dbt manifest is current. `transform_dbt` renders its task graph from
   `dbt/target/manifest.json` (cosmos `LoadMode.DBT_MANIFEST`), so regenerate it
   whenever models change — before every deploy:
   ```bash
   make dbt-build   # refreshes target/manifest.json as part of a full build
   # or, without touching BigQuery (e.g. datasets dropped for a clean run):
   uv run dbt parse --project-dir dbt --profiles-dir dbt/profiles
   ```
   A stale or missing manifest renders an outdated/empty dbt graph in Composer.

### Deploy

```bash
make composer-deploy
```

This syncs three things into the Composer DAG bucket:

| Local path | Bucket path | Purpose |
|---|---|---|
| `airflow/dags/` | `dags/` | DAG files |
| `dbt/` | `dags/dbt/` | dbt project (models, seeds, packages, profiles, compiled `target/manifest.json`) |
| `ingestion/src/wcy_ingestion/` | `dags/wcy_ingestion/` | ingestion source (not on PyPI) |

`wcy_ingestion` is synced as source rather than a wheel to avoid an Artifact
Registry repo — keeping teardown a single `terraform destroy`.

The `COMPOSER_ENV` and `GCP_REGION` Make variables default to `wcy-composer`
and `us-central1`. Override if your `dev.tfvars` differs:

```bash
make composer-deploy COMPOSER_ENV=my-env GCP_REGION=us-east1
```

## Composer lifecycle

### Provision (soft-up, ~25 min)

```bash
make composer-up
```

Sets `enable_composer=true` and runs `terraform apply`. Keeps all warehouse
data (BigQuery datasets, GCS bronze bucket) intact.

### Tear down Composer only (soft-down)

```bash
make composer-down
```

Sets `enable_composer=false` and runs `terraform apply`. Drops the Composer
environment but leaves all warehouse data intact. Use this between demo runs
to avoid billing.

### Destroy everything

```bash
make tf-destroy
```

Destroys all Terraform-managed resources including the Composer environment,
BigQuery datasets, and the bronze GCS bucket.

> **Auto-bucket:** Composer creates a managed GCS bucket (not in Terraform
> state) named `<region>-<env-name>-<hash>-bucket`. After `tf-destroy`, check
> for and manually delete it:
> ```bash
> gcloud storage buckets list --filter="name~wcy-composer"
> gcloud storage rm --recursive gs://<auto-bucket-name>
> ```

## Teardown verification

### Phase 4 Terraform inventory

Phase 4 added exactly two resources to Terraform, both in
`infra/terraform/composer.tf` and both gated by `count = var.enable_composer ? 1 : 0`:

| Resource | Destroyed by |
|---|---|
| `google_composer_environment.main` | `composer-down` or `tf-destroy` |
| `google_project_iam_member.pipeline_composer_worker` | `composer-down` or `tf-destroy` |

No other Phase 4 billable resource was introduced. Specifically:

- **No Artifact Registry** — `wcy_ingestion` is synced as Python source into
  the DAG bucket rather than published as a wheel, so no registry resource
  exists and teardown remains a single `terraform destroy`.
- **No Cloud Run, no additional GCS buckets, no Pub/Sub topics** — only the
  Composer environment itself.

When `enable_composer = false` (soft lever) or after `terraform destroy` (hard
lever), both Phase 4 resources are absent and no billable Phase 4 resource
persists.

### Two teardown levers

| Lever | Command | What it removes | What it keeps |
|---|---|---|---|
| **Soft** | `make composer-down` | Composer environment + `composer.worker` IAM binding | BigQuery datasets, bronze GCS bucket, service account |
| **Hard** | `make tf-destroy` | Everything above + all warehouse data | Nothing (full destroy) |

Use the soft lever between demo runs to stop billing while preserving data.
Use the hard lever at the end of Phase 4 for a clean slate.

### Post-destroy verification

After `make composer-down` or `make tf-destroy`, confirm the environment is gone:

```bash
gcloud composer environments list --locations=us-central1
# Expected: empty list (or "Listed 0 items.")
```

### Composer auto-bucket cleanup

Composer provisions a GCS bucket outside Terraform state (named
`<region>-<env-name>-<hash>-bucket`). It is **not** removed by
`terraform destroy` and must be deleted manually after teardown:

```bash
# Locate the auto-bucket (name contains the environment name or a short hash):
gcloud storage buckets list --filter="name~wcy-composer"

# Delete it (force-removes all objects first):
gcloud storage rm --recursive gs://<auto-bucket-name>

# Confirm it is gone:
gcloud storage buckets list --filter="name~wcy-composer"
# Expected: empty list
```

This bucket does not incur significant cost on its own, but deleting it keeps
the GCP project clean and avoids confusion during any future reprovisioning.

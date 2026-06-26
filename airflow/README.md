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

### Deploy

```bash
make composer-deploy
```

This syncs three things into the Composer DAG bucket:

| Local path | Bucket path | Purpose |
|---|---|---|
| `airflow/dags/` | `dags/` | DAG files |
| `dbt/` | `dags/dbt/` | dbt project (models, seeds, packages, profiles) |
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

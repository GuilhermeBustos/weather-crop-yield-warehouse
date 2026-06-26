# Phase 4 — Orchestration (Airflow / Cloud Composer)

Schedule, observe, and backfill the existing extract → load → transform pipeline
on **Cloud Composer 3** (managed Airflow 3). Ingestion (`wcy_ingestion`) and the
`wcy` dbt project already work standalone; Phase 4 wires them into Airflow DAGs
so the whole chain runs on a trigger, coordinates by data dependency, and can be
backfilled over a parameterized window. The headline deliverable is a green
**end-to-end run in Composer** that lands `raw.*` and rebuilds the marts.

Because this is a **portfolio / skills build**, the Composer environment is
**ephemeral**: stood up to prove the planned pipeline end-to-end, then **torn down
cleanly via Terraform** so nothing is left billing. The lasting artifact is the
*code and the captured run*, not a running service.

Companion: [docs/IMPLEMENTATION_PLAN.md](../../../docs/IMPLEMENTATION_PLAN.md) §Phase 4,
[docs/DATA_MODEL.md](../../../docs/DATA_MODEL.md).

## Inputs (from Phases 1–3)

- **Terraform (Phase 1):** `raw` / `staging` / `marts` BigQuery datasets, the GCS
  bronze bucket, the `pipeline` service account (BQ jobUser + dataset dataEditor +
  bucket objectAdmin), and a **gated `composer.tf`** — a `google_composer_environment`
  behind `enable_composer` (default `false`), node SA = `pipeline`, plus a
  `composer.worker` grant. Needs a verified `composer_image_version` before enabling.
- **Ingestion (Phase 2):** `wcy_ingestion` — a `uv` workspace package configured
  entirely from env via `Settings()` (pydantic-settings). Callable pipeline
  entrypoints `weather.run(Settings())` and `nass_yield.run(Settings())` (and a
  `seed` builder), also exposed as `python -m wcy_ingestion {seed,weather,yield}`.
  The NASS key is read from **Secret Manager** at runtime via the pipeline SA;
  bronze→raw loads are idempotent (`WRITE_TRUNCATE`).
- **Transformation (Phase 3):** the `wcy` dbt project (`staging` → `intermediate`
  → `marts`), env-driven `profiles.yml` (`method: oauth` / ADC), structural test
  suite, `fact_weather_daily` incremental. `dbt build` is green for the 2025 slice.

## Scope decisions (locked)

Resolved with the user before planning:

- **Provision Composer on-demand, then tear it down.** Set a verified
  `composer_image_version`, flip `enable_composer = true`, and `terraform apply` the
  **Composer 3, SMALL** environment on the existing `pipeline` SA to prove the
  pipeline end-to-end — then **`terraform destroy`** it. The environment is
  **ephemeral, not a running service**: Composer has no free tier (smallest env ≈
  **$300+/month while up**), so a clean, complete teardown is a **first-class
  deliverable** (FR-10), not an afterthought. Two levers exist — *soft*
  (`enable_composer = false` + `terraform apply` → drops only the expensive Composer
  env, keeps the cheap BQ/GCS data) and *hard* (`terraform destroy` → removes
  everything).
- **dbt via astronomer-cosmos.** The `transform_dbt` DAG renders the dbt project as
  **native Airflow tasks** (one task per model + test) for per-node observability and
  retries, rather than an opaque `dbt build` BashOperator. **Check:** the cosmos
  version must support **Airflow 3** (the `composer-3-airflow-3.x` image) — the
  `composer.tf` `pypi_packages` lower bound and the local pin (T2) must be raised to
  an Airflow-3-compatible cosmos release; verified in T2/T7.
- **Three dataset-coordinated DAGs.** `ingest_weather` and `ingest_yield` each
  publish an **Airflow Dataset** on success; `transform_dbt` is **scheduled on those
  datasets** so it runs only after both ingestions update — no manual ordering.
- **Manual end-to-end + parameterized backfill; catchup off.** A manually
  triggerable end-to-end path plus a separate **backfill DAG** parameterized by
  weather date range and NASS year. Cron schedules are *defined* (weather monthly,
  NASS on release cadence) but run with **`catchup=False`**, since the 2025 slice is
  a one-shot aligned window with no new data arriving.

Secondary defaults (resolvable in design, not user-blocking):

- **Composer 3 / Airflow 3**, image `composer-3-airflow-3.1.7-build.11` (the only
  Airflow 3 image currently published; Airflow 3 requires Composer 3). Environment
  size **SMALL**.
- **Ingestion runs in-process** as Airflow Python tasks calling the existing
  `weather.run` / `nass_yield.run` entrypoints. The `wcy_ingestion` source is made
  importable in Composer (synced to the bucket + third-party deps via
  `pypi_packages`); exact packaging mechanism settled in design. Prefer
  **bucket-synced source over an Artifact Registry wheel repo** so teardown stays a
  single `terraform destroy` with no extra resource to clean up.
- **Auth:** the Composer **node SA = `pipeline` SA** provides BigQuery/GCS access
  (dbt `oauth`/ADC resolves to it) and Secret Manager access for the NASS key. No
  Airflow Connections with embedded secrets.
- **Failure alerting via `on_failure_callback`**, email by default; Slack deferred.

## In scope

- Terraform: enable + apply the Composer 3 environment (image version, size,
  `pypi_packages`, Airflow env vars for `DBT_*` / `WCY_*` config).
- Deployment glue: sync DAGs and the `dbt/` project into the Composer bucket;
  `make` targets for deploy + local DAG validation; `airflow/README.md`.
- DAGs: `ingest_weather`, `ingest_yield` (dataset producers), `transform_dbt`
  (cosmos, dataset-scheduled consumer), and a parameterized `backfill` DAG.
- Reliability: retries + backoff, `execution_timeout`, failure alerting.
- Verified green end-to-end run in Composer + a deliberate-failure alert demo.
- **Verified clean teardown** — `terraform destroy` removes all Phase 4 resources
  (Composer included) with no orphaned billable leftovers.

## Out of scope

- Expanded data quality (`dbt_expectations`, range/plausibility, source freshness,
  reconciliation) — **Phase 5**.
- CI/CD of DAGs (lint/deploy on push, Slim CI) — **Phase 6**.
- Cost/monitoring dashboards & budget alerts beyond the teardown note — **Phase 7**.
- Real multi-year backfill *data* (the slice stays 2025); Slack notifications;
  KubernetesPodOperator/image-based execution.

## Requirements

### Infrastructure (Composer)

- **FR-1** Provision the Composer 3 environment via Terraform: a verified
  `composer_image_version` (Airflow 3 ⇒ Composer 3; list via the Composer REST API
  `imageVersions` endpoint, or `gcloud composer images list` on a beta-enabled SDK),
  `enable_composer = true` in `dev.tfvars`, `environment_size =
  ENVIRONMENT_SIZE_SMALL`, node SA = `pipeline`. **Done:** `terraform apply` brings
  the environment up and the Airflow UI is reachable.
- **FR-2** The environment installs the runtime deps the DAGs need via
  `software_config.pypi_packages` — `astronomer-cosmos`, `dbt-bigquery`, and the
  `wcy_ingestion` third-party deps not already on the image (pydantic-settings,
  httpx, tenacity, …) — and sets Airflow **environment variables** for the dbt/
  ingestion config (`DBT_BQ_PROJECT`, `DBT_RAW_DATASET`, `DBT_STAGING_DATASET`,
  `DBT_MARTS_DATASET`, `DBT_BQ_LOCATION`, `DBT_PROFILES_DIR`, `WCY_*`). **No secrets
  in env** — the NASS key stays in Secret Manager. **Done:** a DAG can `import
  cosmos` and `import wcy_ingestion` without error.

### Deployment glue

- **FR-3** DAGs deploy to `gs://<composer-dag-bucket>/dags`; the `dbt/` project
  (models, macros, seeds, packages, profiles) deploys somewhere cosmos can read it
  (`dags/dbt` or `data/dbt`). `make` targets perform the sync and run a **local DAG
  validation** (import/parse check, e.g. `airflow dags list`/`test`) without needing
  Composer. An `airflow/README.md` documents deploy + local validation. **Done:**
  `make`-driven deploy lands DAGs that parse with **zero import errors** in Composer.

### DAGs — ingestion (dataset producers)

- **FR-4** `ingest_weather` — runs the weather pipeline (`weather.run(Settings())`)
  for the run window (extract → bronze → `raw.weather_daily`) and **publishes the
  `raw.weather_daily` Airflow Dataset** on success. Monthly schedule, `catchup=False`,
  manually triggerable; retries + backoff + `execution_timeout`.
- **FR-5** `ingest_yield` — runs the NASS pipeline (`nass_yield.run(Settings())`)
  (extract → bronze → `raw.nass_yield`), **guarded to no-op when there is no new
  release** for the configured year, and **publishes the `raw.nass_yield` Dataset**
  on success. NASS-release-aligned schedule, `catchup=False`, manually triggerable.

### DAG — transform (dataset consumer, cosmos)

- **FR-6** `transform_dbt` — renders the `wcy` dbt project via **astronomer-cosmos**
  as native Airflow tasks (models + structural tests), **scheduled on
  `[raw.weather_daily, raw.nass_yield]`** so it runs only after both ingestions
  update. Resolves the dbt profile from the node SA (`oauth`/ADC) + env vars; handles
  `deps`/`seed` as needed. **Done:** a run materializes staging → marts, the
  structural tests pass, and each model/test shows as its own task in the UI.

### DAG — backfill

- **FR-7** `backfill` — a manually triggered DAG **parameterized** by weather date
  range (`start`, `end`) and NASS `year`, running extract → load → dbt for the given
  window. `catchup=False`; **idempotent** (bronze overwrite + `WRITE_TRUNCATE` +
  idempotent marts / incremental fact). **Done:** a backfill of the 2025 slice
  reproduces the marts identically to the scheduled path.

### Reliability & secrets

- **FR-8** Every task has **retries with exponential backoff** and an
  `execution_timeout`; an **`on_failure_callback`** raises an alert (email default)
  so a deliberate failure is surfaced. SLAs optional.
- **FR-9** No secrets or hardcoded project/dataset ids in DAGs or the repo: BigQuery/
  GCS auth via the Composer **node SA** (= `pipeline`), the NASS key via **Secret
  Manager** through the existing `wcy_ingestion` path, all ids via Airflow env vars.

### Teardown & cost control

- **FR-10** Teardown is **one command and leaves no billable Phase 4 resource**.
  `make tf-destroy` (`terraform destroy -var-file=dev.tfvars`) removes the Composer
  environment along with everything else; the existing `bucket_force_destroy` /
  `dataset_force_destroy` flags already let the bronze bucket and BigQuery datasets
  drop even when non-empty, and no resource carries `prevent_destroy`. The
  Composer-managed **auto-bucket** (created by the service, not Terraform) is
  documented as a manual post-destroy check. The **soft lever**
  (`enable_composer = false` + `terraform apply`) drops only the Composer env while
  keeping the warehouse data. Phase 4 adds **no new persistent paid resource**
  (e.g. no Artifact Registry) that would survive `destroy`. **Done:** after
  `make tf-destroy`, `gcloud composer environments list` is empty and no Phase 4
  resource remains billable.

## Verification (DoD)

- **V-1** `terraform apply` with `enable_composer = true` provisions the Composer 3
  SMALL environment; the Airflow UI loads; the required `pypi_packages` are present.
- **V-2** All four DAGs (`ingest_weather`, `ingest_yield`, `transform_dbt`,
  `backfill`) parse with **zero import errors** — verified locally and in Composer.
- **V-3** Triggering `ingest_weather` and `ingest_yield` updates `raw.*` and emits
  their Datasets; `transform_dbt` **auto-triggers via dataset scheduling** (no manual
  ordering) and rebuilds the marts with structural tests green.
- **V-4** The full chain completes green in Composer and the marts reflect the run —
  `weather_yield_analysis` populated, corn ≈ **150–200 bu/acre** for 2025.
- **V-5** A deliberate failure surfaces an alert via `on_failure_callback`.
- **V-6** The `backfill` DAG run for the 2025 slice is **idempotent** — marts
  identical to the scheduled path; re-running is stable.
- **V-7** No secrets/hardcoded ids in DAGs or repo; auth via node/pipeline SA +
  Secret Manager (`profiles.yml` stays env-driven `oauth`).
- **V-8** Teardown is **verified**, not just planned: `make tf-destroy` removes all
  Phase 4 resources (Composer included), `gcloud composer environments list` returns
  empty, and any manual cleanup (the Composer auto-bucket) is documented. The cost +
  teardown plan is recorded in the IMPLEMENTATION_PLAN decision log (§8).
- **V-9** *(manual, needs GCP)* the end-to-end Composer run is captured (screenshot /
  run log) for the portfolio milestone.

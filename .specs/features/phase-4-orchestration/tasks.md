# Phase 4 — Tasks

Atomic tasks for the orchestration layer. DAGs live under `airflow/dags/`
(pure-Python helpers + tests alongside); Composer config lives in
`infra/terraform/`; repo glue in the root `Makefile`. `[P]` = parallelizable once
deps are met. Each task traces to a spec **FR**; the end-to-end run (V-3/V-4) is a
manual GCP step, mirroring how Phase 3 deferred the live `dbt build` to bootstrap.

| # | Task | Files | FR | Depends on | Done when |
|---|------|-------|----|-----------| ----------|
| T1 | Wire the Composer env in Terraform: `software_config.pypi_packages` (`astronomer-cosmos`, `dbt-bigquery`, ingestion third-party deps not on the image), `env_variables` (`DBT_*`, `WCY_*` **non-secret** ids), pin a verified `composer_image_version`; keep `enable_composer` **default false** | `infra/terraform/composer.tf`, `variables.tf`, `dev.tfvars`, `dev.tfvars.example` | FR-1, FR-2 | — | `make tf-validate` clean; `terraform plan -var enable_composer=true` shows the env with `pypi_packages` + `env_variables` and **no secret values**; image version pinned |
| T2 | Local Airflow + cosmos dev environment: add `apache-airflow` (+ needed providers) and `astronomer-cosmos` to a dev dependency group, pinned to the **chosen Composer image's Airflow version** via the Airflow constraints file, so DAGs import/parse locally | root `pyproject.toml`, `uv.lock` | FR-3 | — | `uv run python -c "import airflow, cosmos"` succeeds; local Airflow version matches the Composer image |
| T3 [P] | Repo glue: `make` targets `composer-deploy` (rsync `airflow/dags` + the `dbt/` project to the env bucket), `dags-validate` (local parse check), `composer-up` / `composer-down` (apply/destroy via the `enable_composer` toggle); `airflow/README.md` | `Makefile`, `airflow/README.md` | FR-3, FR-10 | T2 | `make dags-validate` parses every DAG locally with **zero import errors**; README documents deploy + up/down |
| T4 [P] | Shared DAG module: a `default_args` factory (retries + exponential backoff, `execution_timeout`, `on_failure_callback` email alert), the two `Dataset` objects (`raw.weather_daily`, `raw.nass_yield`), and thin wrappers invoking `weather.run` / `nass_yield.run` with `Settings()` — **+ pytest unit tests** | `airflow/dags/common.py`, `airflow/dags/tests/test_common.py` | FR-8, FR-9 | T2 | helpers unit-tested (`uv run pytest`); datasets + `default_args` importable; **no secrets** in code |
| T5 [P] | `ingest_weather` DAG — one task calls the weather wrapper, `outlets=[weather dataset]`; **monthly** schedule, `catchup=False`, manually triggerable; reliability from `default_args` | `airflow/dags/ingest_weather.py` | FR-4 | T4 | DAG parses; weather dataset is the task outlet; `catchup=False`; retries/timeout inherited |
| T6 [P] | `ingest_yield` DAG — task calls the NASS wrapper behind a **no-new-release guard** (skip/short-circuit when the configured year is already loaded), `outlets=[yield dataset]`; release-aligned schedule, `catchup=False` — **+ unit test for the guard** | `airflow/dags/ingest_yield.py`, `airflow/dags/tests/test_ingest_yield.py` | FR-5 | T4 | DAG parses; guard's no-op path unit-tested; yield dataset outlet; `catchup=False` |
| T7 | `transform_dbt` DAG via **astronomer-cosmos** — render the `wcy` project as a `DbtDag`/`DbtTaskGroup`, `ProfileConfig` from the node SA (`oauth`/ADC) + env vars, `schedule=[weather dataset, yield dataset]`; handle `deps`/`seed` | `airflow/dags/transform_dbt.py` | FR-6 | T4 | DAG parses and renders dbt nodes as individual tasks; scheduled on **both** datasets; profile resolves from env (no hardcoded ids) |
| T8 | `backfill` DAG — params (`weather_start`, `weather_end`, `nass_year`); runs extract → load → dbt for the window; `catchup=False`; **idempotent**, reusing the T5/T6/T7 building blocks — **+ param-handling unit test** | `airflow/dags/backfill.py`, `airflow/dags/tests/test_backfill.py` | FR-7 | T5, T6, T7 | DAG parses; params surfaced for trigger config; param parsing unit-tested; reuses ingestion + cosmos steps |
| T9 | Teardown verification + runbook: confirm `make tf-destroy` removes Composer **and** all Phase 4 resources; document the **Composer auto-bucket** manual check and the soft (`enable_composer=false`) vs hard (`destroy`) levers; assert **no Artifact Registry / persistent paid resource** was added | `airflow/README.md` (teardown section) | FR-10 | T1, T3 | runbook documents destroy + auto-bucket cleanup; `terraform plan -destroy` shows Composer removed; plan adds no surviving paid resource |
| T10 | Verify end-to-end in Composer + record Phase 4 decisions in `IMPLEMENTATION_PLAN` §8 (ephemeral provision→destroy, cosmos, three dataset DAGs, teardown levers) | `docs/IMPLEMENTATION_PLAN.md` (§8) | V-1…V-9 | T1–T9 | manual Composer run green (corn ≈ 150–200 bu/acre); dataset-triggered `transform_dbt`; deliberate-failure alert fires; backfill idempotent; `gcloud composer environments list` empty after teardown; decisions logged |

## Notes on tricky tasks

- **T1 — no secrets in `env_variables`.** Only non-secret ids go into Composer env
  (`DBT_BQ_PROJECT`, `DBT_RAW_DATASET`, `DBT_STAGING_DATASET`, `DBT_MARTS_DATASET`,
  `DBT_BQ_LOCATION`, `DBT_PROFILES_DIR`, `WCY_*` config). The **NASS key stays in
  Secret Manager** and is fetched at runtime by the existing `wcy_ingestion`
  `io/secrets.py` via the node/pipeline SA. Image is pinned to
  `composer-3-airflow-3.1.7-build.11` (Airflow 3 ⇒ Composer 3); list images via the
  Composer REST API `imageVersions` endpoint (the `images` subcommand is not on the
  GA `gcloud composer` surface).
- **T2 — version pinning (Airflow 3 check).** Composer bundles a specific Airflow
  version (here **Airflow 3.1.7**); local authoring/validation must match it via the
  official constraints file (`constraints-3.1.7-<py>.txt`) or DAGs that parse locally
  can still break in Composer. **astronomer-cosmos check:** confirm the cosmos release
  supports **Airflow 3** *and* `dbt-bigquery` — the current `composer.tf`
  `pypi_packages` lower bound (`>=1.5.0`) predates Airflow 3 support and must be
  raised here and in `composer.tf` to the verified Airflow-3-compatible version.
- **T3 — `wcy_ingestion` in Composer (the packaging wrinkle).** The package is a
  local workspace member, **not on PyPI**, so it can't be a plain `pypi_packages`
  entry. Preferred path: **sync its source into the env bucket** (`dags/` so it's
  importable) and add only its third-party deps via `pypi_packages` — avoiding an
  Artifact Registry repo keeps teardown a single `destroy`. `composer-deploy` does
  this sync alongside the `dbt/` project.
- **T4 — invoke the existing entrypoints, don't reimplement.** Wrappers call
  `weather.run(Settings())` / `nass_yield.run(Settings())` in-process (PythonOperator
  / `@task`). `Settings()` reads the Airflow env vars from T1 — same config contract
  as the CLI. Keep the helpers pure so they unit-test without Airflow scheduling.
- **T6 — no-new-release guard.** NASS county yields publish once per crop year; the
  guard prevents a scheduled run from re-pulling an already-loaded year (e.g. check
  `raw.nass_yield` for the target year, or use `ShortCircuitOperator`). The 2025
  slice is already loaded, so the default scheduled path must **no-op**, not duplicate.
- **T7 — cosmos profile from ADC.** `ProfileConfig` should map to the existing
  env-driven `profiles.yml` (`method: oauth`), which on Composer resolves to the node
  SA via ADC — no keyfile. Cosmos needs the rendered project + `dbt_packages`
  (`dbt deps`) available; run `deps`/`seed` as a setup step or pre-sync the installed
  packages.
- **T8 — reuse, don't fork.** The backfill DAG composes the same wrapper calls + the
  cosmos render with parameterized dates/year; it must not introduce a second copy of
  the ingestion or transform logic. Idempotency rides on Phase 2/3 guarantees
  (bronze overwrite, `WRITE_TRUNCATE`, idempotent marts / incremental fact).

## Manual bootstrap (user — outside the code, needs GCP)

1. `gcloud services enable composer.googleapis.com`; confirm/refresh
   `composer_image_version` in `dev.tfvars` (pinned to an Airflow 3 image) — list
   images via the Composer REST API `imageVersions` endpoint.
2. `make composer-up` (`terraform apply -var enable_composer=true`) — provisions the
   SMALL env (~25 min).
3. `make composer-deploy` — sync DAGs + the `dbt/` project + `wcy_ingestion` source to
   the env bucket.
4. In the Airflow UI: trigger `ingest_weather` and `ingest_yield`; confirm
   `transform_dbt` **auto-triggers via datasets**; spot-check
   `marts.weather_yield_analysis` (corn ≈ 150–200 bu/acre, 2025).
5. Trigger a deliberate failure (e.g. a bad var) → confirm the `on_failure_callback`
   alert fires.
6. Trigger `backfill` with the 2025 params → confirm the marts are unchanged
   (idempotent).
7. `make composer-down` (or `make tf-destroy`) → confirm
   `gcloud composer environments list` is empty; delete the leftover Composer
   **auto-bucket** if it survived.

## Sequencing (suggested)

```
T1 ────────────────────────────────────────┐
                                            │
T2 ─┬─ T3 [P] ──────────────────────┐       │
    │                               │       │
    └─ T4 [P] ─┬─ T5 [P] ─┐         │       │
               ├─ T6 [P] ─┼── T8 ───┤       │
               └─ T7 ─────┘         │       │
                                    ├──────  T10
        (T9 needs T1, T3) ── T9 ────┘
                       (T10 needs T1–T9)
```

`[P]` pairs: **T3 ∥ T4** (both need only T2), then **T5 ∥ T6** (both need T4). T7
joins at T4; T8 gathers the three DAGs; T9 verifies teardown once T1/T3 land; T10 is
the final end-to-end verify + decision log.

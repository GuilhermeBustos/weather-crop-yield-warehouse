# Implementation Plan — Weather × Crop Yield Warehouse

This document is the build guide for the project. It breaks the work into phases, each
with a **goal**, concrete **tasks**, **deliverables**, and a **definition of done (DoD)**.
Phases are ordered so you always have something runnable end-to-end early, then deepen.

- **Scope:** corn & soybeans, county & state level, batch.
- **Cloud:** GCP (using available credits).
- **Orchestration:** Airflow on Cloud Composer 2.
- **Transformation:** dbt Core. **IaC:** Terraform. **CI/CD:** GitHub Actions.

> Companion docs: [DATA_SOURCES.md](DATA_SOURCES.md) (API details) and
> [DATA_MODEL.md](DATA_MODEL.md) (warehouse schemas).

---

## 1. Guiding principles

1. **ELT, not ETL.** Land raw data as-is, transform inside BigQuery with dbt. This keeps
   ingestion dumb/reliable and makes transformations versioned, testable, and re-runnable.
2. **Medallion layering.** `bronze` (GCS raw files) → `raw`/`staging` (BigQuery, lightly
   typed/cleaned) → `marts` (BigQuery, modeled for analysis).
3. **Idempotent & re-runnable.** Any task can be re-run for a given partition (date/year)
   without creating duplicates. Backfills are first-class.
4. **Everything as code.** Infra (Terraform), transforms (dbt), orchestration (DAGs),
   pipelines (Python) — all in this repo, all reviewed via PRs, all CI-checked.
5. **Cost-aware by default.** Partition + cluster every large table, cap bytes billed,
   right-size Composer, set budget alerts.

---

## 2. Conceptual data flow

The analytical heart of the project is joining **growing-season weather features** to
**annual yield** per **(county, commodity, year)**.

```
Open-Meteo ──> daily weather per county centroid ──┐
                                                    ├─> growing-season features
NASS Quick Stats ──> annual yield per county ───────┘   (GDD, precip, heat-stress days)
                                                          joined to yield => analysis mart
```

Key modeling decision: Open-Meteo is queried **per geographic point (lat/lon)**, but NASS
yields are reported **per county (FIPS code)**. We bridge them with a **county reference
table** mapping each county FIPS to a representative centroid (lat/lon), sourced from the
US Census Gazetteer county file. Weather is then aggregated over the growing season
(≈ April–October for the US Corn Belt) into per-county-year features.

---

## 3. Repository structure (target)

```
weather-crop-yield-warehouse/
├── README.md
├── Makefile                       # common dev commands (lint, test, plan, deploy)
├── pyproject.toml                 # tooling config (ruff, etc.)
├── .pre-commit-config.yaml
├── .github/workflows/             # CI/CD pipelines
│   ├── ci.yml                     # lint + unit tests + dbt build (CI dataset)
│   ├── terraform.yml              # fmt / validate / plan
│   └── deploy.yml                 # deploy DAGs + dbt on merge to main
├── docs/                          # this plan + references
├── infra/terraform/               # GCP infrastructure as code
│   ├── main.tf  variables.tf  outputs.tf  backend.tf
│   └── modules/{gcs,bigquery,composer,iam}/
├── ingestion/                     # Python extract-and-load package
│   ├── pyproject.toml
│   ├── src/wcy_ingestion/
│   │   ├── config.py              # settings (env-driven)
│   │   ├── clients/openmeteo.py   # Open-Meteo client
│   │   ├── clients/nass.py        # NASS Quick Stats client
│   │   ├── io/gcs.py              # write Parquet to bronze
│   │   ├── io/bigquery.py         # load bronze -> raw
│   │   └── pipelines/{weather,yield}.py
│   └── tests/                     # pytest (mocked HTTP)
├── dbt/                           # dbt Core project
│   ├── dbt_project.yml  packages.yml  profiles/
│   ├── seeds/county_centroids.csv # FIPS -> lat/lon, state, name
│   ├── models/staging/            # stg_weather_daily, stg_nass_yield
│   ├── models/intermediate/       # int_weather_growing_season
│   ├── models/marts/              # dims, facts, weather_yield_analysis
│   ├── macros/  tests/            # custom macros & singular tests
│   └── exposures/
└── airflow/
    ├── dags/                      # ingest_weather, ingest_yield, transform_dbt, orchestrator
    ├── plugins/
    └── requirements.txt           # PyPI deps for the Composer environment
```

---

## 4. Phased plan

### Phase 0 — Foundations & scaffolding
**Goal:** a clean, reproducible local + cloud baseline before writing pipeline code.

**Tasks**
- Create the repo structure above; add `Makefile`, `pyproject.toml`, `.pre-commit-config.yaml`.
- Choose a Python toolchain (recommend **`uv`** for speed; `poetry` is fine) and pin
  Python 3.12. Configure `ruff` (lint+format) and `sqlfluff` (dbt/BigQuery dialect).
- GCP project setup: create/confirm the project, enable APIs (BigQuery, Composer,
  Storage, Artifact Registry, Secret Manager, Cloud Monitoring). Install & auth `gcloud`.
- Register for a **free NASS Quick Stats API key** (see DATA_SOURCES.md) and store it in
  **Secret Manager** (never commit it).
- Decide naming conventions: project id, dataset names (`raw`, `staging`, `marts`,
  `dbt_ci`), bucket names (`<proj>-bronze`, `<proj>-composer`, `<proj>-tf-state`),
  service-account names, labels (`project=wcy`, `env=dev`).

**Deliverables:** populated repo skeleton, working `make lint`, documented GCP project,
secrets stored, conventions written in this doc.

**DoD:** `pre-commit run --all-files` passes on an empty skeleton; `gcloud` can list the
project; NASS key retrievable from Secret Manager.

---

### Phase 1 — Infrastructure as Code (Terraform)
**Goal:** all GCP resources provisioned reproducibly from code.

**Tasks**
- Configure **remote state** in a GCS bucket (`backend.tf`); enable state locking.
- Modules / resources:
  - **GCS:** bronze landing bucket (lifecycle rules to expire old raw files), Composer
    bucket is managed by Composer itself, optional artifacts bucket.
  - **BigQuery:** datasets `raw`, `staging`, `marts`, `dbt_ci` with location (e.g. `US`),
    default table expiration off for warehouse datasets, labels.
  - **Composer 2 environment:** small/dev size, the chosen Airflow version, the project
    service account, environment variables, PyPI packages.
  - **Service accounts & IAM:** a pipeline SA (BigQuery dataEditor/jobUser, Storage
    objectAdmin on bronze, Secret Manager accessor), least privilege.
  - **Artifact Registry** (only if you containerize ingestion — optional for MVP).
- Parameterize per environment with `*.tfvars` (`dev` first; `prod` optional later).

**Deliverables:** `terraform plan`/`apply` provisions the full stack; outputs expose
bucket names, dataset ids, Composer URI, SA emails.

**DoD:** a fresh `terraform apply` from zero stands up the environment; `terraform
destroy` tears it down cleanly; no secrets in state-tracked files.

---

### Phase 2 — Ingestion (Extract & Load → bronze → raw)
**Goal:** reliably land both sources to GCS and load into BigQuery `raw`.

**Tasks**
- **County reference seed:** download the US Census Gazetteer county file; produce
  `dbt/seeds/county_centroids.csv` (`fips`, `state_alpha`, `county_name`, `lat`, `lon`).
  Optionally filter to corn/soy-producing states to bound API volume.
- **Open-Meteo client** (`clients/openmeteo.py`):
  - Call `GET https://archive-api.open-meteo.com/v1/archive` with `latitude`,
    `longitude`, `start_date`, `end_date`, a `daily=` variable list, and `timezone`.
  - **Batch multiple counties per request** (comma-separated coordinates) to stay well
    under the 10,000 calls/day free limit.
  - Add retry with exponential backoff + jitter, timeouts, and polite rate limiting.
  - Write responses to bronze as partitioned Parquet:
    `gs://<proj>-bronze/openmeteo/ingest_date=YYYY-MM-DD/part-*.parquet`.
- **NASS client** (`clients/nass.py`):
  - Call `GET https://quickstats.nass.usda.gov/api/api_GET/` with `key`,
    `commodity_desc` (`CORN`, `SOYBEANS`), `statisticcat_desc=YIELD`,
    `agg_level_desc` (`COUNTY`, `STATE`), `year`, and (for county) `state_alpha`.
  - Respect the **50,000-record per-request limit** — page by `year` and/or
    `state_alpha`; use `get_counts` first to size queries.
  - Land to `gs://<proj>-bronze/nass/commodity=<c>/year=<y>/part-*.parquet`.
- **Load bronze → BigQuery `raw`** (`io/bigquery.py`): load jobs (or external tables) into
  `raw.weather_daily` and `raw.nass_yield`, partitioned by ingest/observation date/year.
- **Pipelines** (`pipelines/weather.py`, `pipelines/yield.py`): thin orchestration that
  ties extract → land → load, parameterized by date/year range; **idempotent** (overwrite
  the target partition).
- **Backfill strategy:** define the historical window (recommend **2000–present** to keep
  volumes reasonable; ERA5 supports back to 1940 if you want more). Backfill weather by
  county-year chunks; backfill NASS by year.

**Deliverables:** running `python -m wcy_ingestion ...` lands and loads a date/year slice;
`raw.weather_daily` and `raw.nass_yield` populated for a test slice.

**DoD:** re-running the same slice produces identical row counts (idempotent); a small
backfill (e.g., one state, 2 years) completes and is queryable in `raw`.

---

### Phase 3 — Transformation (dbt: staging → marts)
**Goal:** a clean, tested, documented analytical model in BigQuery.

**Tasks**
- Initialize the dbt project; configure `profiles` for BigQuery (service-account auth in
  CI/Composer, `oauth` locally). Add `packages.yml` (`dbt_utils`, optionally
  `dbt_expectations`).
- **Sources:** declare `raw.weather_daily`, `raw.nass_yield` with freshness rules.
- **Seeds:** load `county_centroids.csv`.
- **Staging** (`models/staging/`, views): `stg_weather_daily`, `stg_nass_yield` — rename,
  cast, deduplicate, standardize units and FIPS codes.
- **Intermediate** (`models/intermediate/`): `int_weather_growing_season` — aggregate daily
  weather into per-county-year features over the growing season:
  **GDD** (growing degree days, base 50 °F / 10 °C), total/seasonal precipitation,
  count of heat-stress days (e.g., Tmax > 30 °C), dry-spell metrics, mean radiation.
- **Marts** (`models/marts/`, tables, partitioned+clustered):
  - `dim_date`, `dim_county` (from the seed), `dim_commodity`.
  - `fact_weather_daily`, `fact_crop_yield`.
  - `weather_yield_analysis` — the headline mart: one row per (county, commodity, year)
    with yield + growing-season weather features, ready for correlation/BI/ML.
- Add **dbt tests** (see Phase 5) and **`dbt docs`** descriptions on every model/column.

**Deliverables:** `dbt build` produces the full DAG; `weather_yield_analysis` is
populated and queryable; `dbt docs generate` renders lineage.

**DoD:** `dbt build` is green (models + tests); the analysis mart returns sensible numbers
for a known county-year (sanity-check corn yield ≈ 150–200 bu/acre in the Corn Belt).

---

### Phase 4 — Orchestration (Airflow / Cloud Composer)
**Goal:** scheduled, observable, backfillable pipelines in Composer.

**Tasks**
- **DAG design** (recommend one orchestrator DAG with task groups, or three coordinated
  DAGs):
  - `ingest_weather` — extract+load weather for the run window.
  - `ingest_yield` — extract+load NASS yields (annual; guarded so it no-ops when no new
    release).
  - `transform_dbt` — `dbt build` (run + test) after ingestion succeeds.
- Use **Airflow datasets / `TriggerDagRun`** (or task-group dependencies) so transforms run
  only after successful ingestion.
- **Scheduling:** weather refresh **monthly** (ERA5 has a multi-day lag; annual data
  doesn't need daily runs); NASS check aligned to release calendar. Provide a separate
  **backfill DAG** parameterized by date/year range.
- **dbt in Composer:** run via `BashOperator`/`KubernetesPodOperator`, or adopt
  **astronomer-cosmos** to render dbt models as native Airflow tasks (nicer observability).
- **Secrets & connections:** pull the NASS key from Secret Manager via the Airflow
  Secret Manager backend; use the pipeline SA for BigQuery/GCS.
- **Reliability:** retries with backoff, `execution_timeout`, SLAs, and failure
  notifications (email/Slack).

**Deliverables:** DAGs deployed to the Composer DAG bucket; a manual trigger runs
extract → load → dbt end-to-end; backfill DAG fills a historical range.

**DoD:** a scheduled run completes green in Composer and updates the marts; a deliberate
failure surfaces an alert; a backfill run is idempotent.

---

### Phase 5 — Data quality & testing
**Goal:** trust in the data and the code.

**Tasks**
- **dbt tests:**
  - Generic: `not_null`, `unique` (on grain keys), `relationships` (FIPS ↔ dim_county),
    `accepted_values` (commodity, agg level).
  - Range/plausibility via `dbt_expectations` or singular SQL tests: yields within sane
    bounds, temperatures within physical limits, GDD ≥ 0, precipitation ≥ 0.
  - **Grain uniqueness** on `weather_yield_analysis` (county, commodity, year).
- **Source freshness:** `dbt source freshness` to catch stale raw loads.
- **Reconciliation checks:** row-count and key-count comparisons bronze → raw → staging.
- **Python unit tests** (`pytest`): mock HTTP (`responses`/`respx`) for both clients;
  test batching, retry, partition pathing, and parsing; test idempotent load logic.
- Wire all of the above into CI (Phase 6).

**Deliverables:** a documented test catalog; `dbt build` + `pytest` both green.

**DoD:** introducing a bad row (e.g., negative yield) or a broken parse fails the relevant
test; freshness fails when raw is stale.

---

### Phase 6 — CI/CD (GitHub Actions)
**Goal:** every change is automatically linted, tested, and safely deployed.

**Tasks**
- **`ci.yml`** (on PR): `ruff` + `sqlfluff` lint, `pytest`, `dbt deps`, `dbt build` against
  the **`dbt_ci`** dataset (use **Slim CI** with `state:modified+` and deferral to prod
  manifest to build only what changed).
- **`terraform.yml`** (on PR touching `infra/`): `fmt -check`, `validate`, `plan`
  (comment the plan on the PR).
- **`deploy.yml`** (on merge to `main`): sync `airflow/dags/` and the dbt project to the
  Composer GCS bucket; optionally run `dbt build` against prod, or let the next scheduled
  Composer run pick it up.
- **Auth:** use **Workload Identity Federation** (OIDC) from GitHub Actions to GCP — no
  long-lived SA keys. Store project ids / dataset names as Actions variables; secrets in
  Actions secrets.
- Protect `main` (required checks, PR review).

**Deliverables:** green CI on PRs; automated deploy on merge; PR-commented Terraform plans.

**DoD:** a PR cannot merge with failing lint/tests; merging to `main` updates Composer DAGs
within one run; no static cloud credentials in the repo.

---

### Phase 7 — Cost, monitoring & observability
**Goal:** keep spend predictable and failures visible.

**Tasks**
- **BigQuery cost controls:**
  - Partition large tables (weather by date, yield/analysis by year) and **cluster**
    (by `state_alpha`, `commodity`, `fips`).
  - Set `require_partition_filter` on partitioned tables; set a project/job
    **maximum bytes billed** cap.
  - Prefer incremental dbt models for the big weather fact.
- **Budgets & alerts:** a GCP **budget alert** on the project; label all resources for
  cost attribution.
- **Composer sizing:** start with the smallest viable environment; document how to pause
  or scale down between runs to conserve credits (Composer is the largest fixed cost).
- **Observability:** Cloud Monitoring dashboard (DAG success rate, run duration, BQ bytes
  scanned); Airflow SLAs + failure callbacks → email/Slack; dbt freshness alerts.
- **Runbook:** short doc on common failures (API 429s, NASS 50k-limit errors, stale ERA5)
  and how to re-run/backfill.

**Deliverables:** cost guardrails active, a monitoring dashboard, alerting wired, a runbook.

**DoD:** an over-large query is blocked by the bytes cap; a failed DAG pages you; the budget
alert fires in a test; Composer can be scaled down when idle.

---

### Phase 8 — Documentation & polish (portfolio)
**Goal:** make the project legible and impressive to reviewers.

**Tasks**
- Keep `README`, this plan, `DATA_SOURCES.md`, `DATA_MODEL.md` current.
- Publish the **dbt docs** site (lineage graph) — e.g., via GitHub Pages from CI.
- Add a short **analysis notebook** demonstrating a weather↔yield correlation finding from
  `weather_yield_analysis` (a compelling screenshot for the portfolio).
- Write a brief architecture/decision-record section (why GCP, ELT, medallion, dbt).
- Add diagrams (the README mermaid + a data-model ERD).

**Deliverables:** polished docs, dbt docs site, one analytical insight write-up.

**DoD:** a new reader can understand and (with credentials) stand up the project from the
docs alone.

---

## 5. Suggested milestones (vertical slices)

To stay motivated and always have something demoable, build **thin vertical slices** first:

1. **M1 — Hello slice:** Terraform stands up datasets/bucket; ingest **one state, two
   years** of corn yield + weather; one dbt staging model in BigQuery. (Phases 0–3 partial)
2. **M2 — End-to-end mart:** full staging→marts including `weather_yield_analysis` for that
   slice; dbt tests green. (Phase 3 + 5 partial)
3. **M3 — Orchestrated:** the slice runs in Composer on a schedule with a backfill DAG.
   (Phase 4)
4. **M4 — Scaled & hardened:** backfill all corn/soy states 2000–present; CI/CD, cost
   controls, monitoring. (Phases 2 full, 6, 7)
5. **M5 — Polished:** docs, dbt docs site, analysis insight. (Phase 8)

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Open-Meteo rate limit (10k/day) during backfill | Batch many counties per request; chunk backfill across days; cache landed Parquet so re-runs don't re-call. |
| NASS 50k-record per-call limit → errors | Page by year and `state_alpha`; call `get_counts` to size queries before fetching. |
| County→point mismatch (centroid ≠ where crops grow) | Document the simplification; optionally weight by cropland or use multiple points per large county as a later refinement. |
| Composer fixed cost burns credits | Smallest environment; pause/scale down when idle; most data is annual so runs are infrequent. |
| BigQuery runaway scans | Partition + cluster + `require_partition_filter` + max-bytes-billed cap. |
| Schema drift in NASS/Open-Meteo responses | Land raw first (bronze) + dbt source tests; fail fast on unexpected schema. |

---

## 7. Out of scope (future / stretch)

- Streaming / near-real-time ingestion (this is intentionally batch).
- BI dashboard layer (Looker Studio) — easy to add later on top of `weather_yield_analysis`.
- Additional crops (wheat, cotton) and finer geographies.
- ML yield prediction on the analysis mart.

---

## 8. Conventions & decisions (record here as you go)

Use this section as a lightweight decision log (ADR-lite). Seed entries:

- **ELT over ETL** — transform in BigQuery with dbt for testability and re-runnability.
- **Medallion layering** — bronze (GCS) → raw/staging (BQ) → marts (BQ).
- **dbt Core** over Dataform — portability and ecosystem.
- **Terraform** for all infra — reproducibility.
- **Backfill window:** _decide and record_ (recommended 2000–present).
- **Growing season definition:** _decide and record_ (recommended Apr–Oct; GDD base 10 °C).

### Phase 1 (Terraform) decisions

- **Terraform layout:** flat root at `infra/terraform/`, files split by concern —
  **no modules**. Each resource type is created a small fixed number of times, so
  module indirection adds no reuse and only costs boilerplate. Datasets use
  `for_each`. (Revisit if a `prod` environment is added.)
- **Region:** `us-central1` for regional resources (GCS bronze, Composer);
  BigQuery in the `US` multi-region.
- **Remote state:** GCS backend with partial config (`backend.hcl`); the state
  bucket is created manually (it cannot bootstrap itself).
- **IAM:** least privilege — project-level `bigquery.jobUser`, dataset-level
  `bigquery.dataEditor`, bucket-level `storage.objectAdmin`; additive
  `*_iam_member` only.
- **Composer deferred:** `composer.tf` written but gated behind
  `enable_composer = false` until Phase 4 — it is the largest fixed cost and runs
  24/7, and milestones M1/M2 need no orchestration.

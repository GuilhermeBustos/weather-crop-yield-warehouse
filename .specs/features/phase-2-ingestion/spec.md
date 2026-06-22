# Phase 2 — Ingestion (Extract & Load → bronze → raw)

Reliably land both external sources to GCS bronze as partitioned Parquet, then
load into BigQuery `raw`. ELT, not ETL: ingestion stays dumb and idempotent;
all shaping happens later in dbt (Phase 3).

Companion: [docs/IMPLEMENTATION_PLAN.md](../../../docs/IMPLEMENTATION_PLAN.md) §Phase 2,
[docs/DATA_SOURCES.md](../../../docs/DATA_SOURCES.md), [docs/DATA_MODEL.md](../../../docs/DATA_MODEL.md).

## Scope decisions (locked)

Deliberately scoped to a thin, free-tier-safe vertical slice — this is a
skills/portfolio build on GCP free credits, not a production backfill.

- **Commodities:** `CORN`, `SOYBEANS` only.
- **Geography:** Core Corn Belt — `IA`, `IL`, `IN`, `NE`, `MN` (~450 counties).
- **Weather window:** the **2025 growing season, Apr 1 – Oct 31 2025**, pulled
  once via the Open-Meteo *archive* (historical) API. One completed season, not a
  multi-year backfill — a handful of batched calls, far under the 10k/day limit.
- **Yield year:** NASS **2025** (the freshest *completed* crop year; county
  estimates published by early 2026). 2026 yields don't exist yet — excluded.
- **Alignment:** the weather window and the yield year share **year = 2025** so the
  Phase 3 analysis mart joins on `(fips, year)` and produces a real correlation.

## In scope

- Installable `ingestion/` package (`wcy_ingestion`) wired into the root `uv` setup.
- Env-driven config; NASS key read from **Secret Manager** (never committed/logged).
- County-centroid seed (`dbt/seeds/county_centroids.csv`) for the 5 states.
- Open-Meteo archive client (coordinate-batched) and NASS Quick Stats client
  (`get_counts`-gated), both with retry/backoff/timeout.
- Bronze writers (partitioned Parquet) and BigQuery `raw` loaders
  (`raw.weather_daily`, `raw.nass_yield`), partitioned + clustered, idempotent.
- Thin pipelines + a CLI (`python -m wcy_ingestion seed|weather|yield`).
- Pytest unit suite with mocked HTTP (no live network).

## Out of scope

- dbt staging/intermediate/marts models — **Phase 3**.
- Orchestration / Composer DAGs — **Phase 4**.
- Multi-year / historical backfill (deliberately excluded for cost/simplicity).
- Full data-quality, freshness, and reconciliation suite — **Phase 5**.
- Containerizing ingestion / Artifact Registry.
- Years other than 2025, states outside the 5, commodities beyond corn/soy.

## Requirements

### Packaging & config

- **FR-1** `ingestion/` is an installable package (`wcy_ingestion`, src layout)
  with **pinned runtime deps**, registered as a `uv` **workspace member** so
  `uv sync` installs it and `pytest`/`ruff` (already pointed at `ingestion/`)
  resolve it. Python 3.12.
- **FR-2** `config.py` exposes env-driven settings (`pydantic-settings`) with
  defaults matching the locked slice: `project_id`, `bronze_bucket`, `raw_dataset`,
  `region`, `target_states`, weather `start_date`/`end_date`, `daily_variables`,
  `commodities`, `nass_year`, `nass_secret_name`, Open-Meteo `batch_size`. **No
  secrets in code or defaults.**

### County reference seed

- **FR-3** A reproducible builder downloads the US Census **Gazetteer counties**
  file and emits `dbt/seeds/county_centroids.csv` with columns
  `fips,state_alpha,county_name,lat,lon`, **filtered to the 5 states**, 5-digit
  zero-padded `fips`. Output is deterministic and committed.

### Extract clients

- **FR-4** `clients/openmeteo.py` calls `GET archive-api.open-meteo.com/v1/archive`
  with **comma-separated batched** `latitude`/`longitude` (≤ `batch_size` points
  per call), `start_date`/`end_date`, the `daily=` variable list, and `timezone`.
  Responses are one block **per point in input order**; each is mapped back to its
  `fips` and flattened to one record per `(fips, date)`.
- **FR-5** `clients/nass.py` reads the API key from **Secret Manager**, calls
  `get_counts` **first** to stay under the 50k-record cap, then `api_GET`, filtering
  `commodity_desc ∈ {CORN,SOYBEANS}`, `statisticcat_desc=YIELD`,
  `agg_level_desc ∈ {COUNTY,STATE}`, `year=<nass_year>`, `state_alpha ∈` the 5
  states; **paged by `(commodity, state)`**.
- **FR-6** Both clients use a shared HTTP policy: request **timeout**, **retry with
  exponential backoff + jitter** on 429/5xx, and polite pacing. No silent failures.

### Bronze landing (GCS)

- **FR-7** `io/gcs.py` writes responses as partitioned Parquet (`pyarrow`):
  - Open-Meteo → `gs://<bronze>/openmeteo/ingest_date=YYYY-MM-DD/part-*.parquet`
  - NASS → `gs://<bronze>/nass/commodity=<c>/year=<y>/part-*.parquet`
  Writing a partition **overwrites** that prefix so re-runs don't accumulate dupes.

### Raw load (BigQuery)

- **FR-8** `io/bigquery.py` loads bronze Parquet → native `raw` tables with an
  **explicit schema**, adding `_ingested_at`:
  - `raw.weather_daily` — `fips, latitude, longitude, date, temperature_2m_max,
    temperature_2m_min, temperature_2m_mean, precipitation_sum,
    et0_fao_evapotranspiration, shortwave_radiation_sum, windspeed_10m_max,
    _ingested_at`. **Time-partition by `date`, cluster by `fips`.**
  - `raw.nass_yield` — `year, state_alpha, state_fips_code, county_code,
    county_name, commodity_desc, statisticcat_desc, short_desc, unit_desc,
    value_raw, _ingested_at`. **Range-partition by `year`, cluster by
    `state_alpha, commodity_desc`.**
- **FR-9** Loads are **idempotent** via `WRITE_TRUNCATE` of the target (full-table
  for this single-window slice; partition-decorator truncation is the documented
  path when more windows are added). `value_raw` stays a STRING (suppression flags
  like `(D)`/`(Z)` parsed later in dbt).

### Pipelines & CLI

- **FR-10** `pipelines/weather.py` and `pipelines/yield.py` tie
  extract → land → load, parameterized (dates / year / states), **idempotent
  end-to-end**.
- **FR-11** `python -m wcy_ingestion` exposes `seed`, `weather`, and `yield`
  subcommands wiring config → pipeline.

### Idempotency, limits & tests

- **FR-12** Re-running any slice yields **identical `raw` row counts** (overwrite
  semantics throughout).
- **FR-13** Stay within free limits: Open-Meteo coordinate batching; NASS
  `get_counts` gate before each fetch.
- **FR-14** **Pytest** unit suite with **mocked HTTP** (`respx`) covers batching,
  retry, response parsing, partition pathing, and idempotent-load logic. **No live
  network** in tests.

## Verification (DoD)

- **V-1** `make lint` (ruff check + format) is green on `ingestion/`.
- **V-2** `make test` (pytest) is green; both clients and the idempotent-load logic
  are covered with mocked HTTP.
- **V-3** `dbt/seeds/county_centroids.csv` exists, contains only the 5 states, has
  valid 5-digit `fips` + numeric `lat`/`lon`, and is committed.
- **V-4** *(manual, needs GCP)* `python -m wcy_ingestion weather` lands 2025-season
  Parquet to bronze and loads `raw.weather_daily` (partitioned by `date`, clustered
  by `fips`); the table is queryable for the 5 states.
- **V-5** *(manual, needs GCP)* `python -m wcy_ingestion yield` lands corn+soy 2025
  NASS to bronze and loads `raw.nass_yield` (partitioned by `year`, clustered by
  `state_alpha, commodity_desc`).
- **V-6** *(manual, needs GCP)* Re-running either pipeline produces identical row
  counts (idempotent).
- **V-7** The NASS key is fetched from Secret Manager at runtime — absent from the
  repo, config defaults, and logs.

# Phase 3 — Transformation (dbt: staging → marts)

Turn the loaded `raw` tables into a clean, tested, documented analytical model in
BigQuery. ELT discipline continues: ingestion stays dumb; **all** parsing, typing,
deduplication, and shaping happens here in dbt. The headline deliverable is the
`weather_yield_analysis` mart — one row per `(county, commodity, year)` joining
growing-season weather features to crop yield.

Companion: [docs/IMPLEMENTATION_PLAN.md](../../../docs/IMPLEMENTATION_PLAN.md) §Phase 3,
[docs/DATA_MODEL.md](../../../docs/DATA_MODEL.md), [docs/DATA_SOURCES.md](../../../docs/DATA_SOURCES.md).

## Inputs (from Phase 2)

- `raw.weather_daily` — one row per `(fips, date)`, °C / mm / MJ·m⁻² / km·h⁻¹,
  `_ingested_at` stamped, partitioned by `date`, clustered by `fips`. 5 states,
  Apr 1 – Oct 31 2025 (~101k rows).
- `raw.nass_yield` — one row per NASS record, **COUNTY and STATE** agg levels,
  corn + soy, 2025, `value_raw` kept as STRING (suppression flags intact),
  partitioned by `year`, clustered by `state_alpha, commodity_desc`.
- `dbt/seeds/county_centroids.csv` — `fips,state_alpha,county_name,lat,lon` for the
  5 states (474 rows), already committed by Phase 2.

## Scope decisions (locked)

Inherited from the Phase 2 slice, plus three Phase 3 modeling decisions resolved
before planning:

- **Slice (inherited):** Core Corn Belt `IA, IL, IN, NE, MN`; `CORN`, `SOYBEANS`;
  **2025 only**. Weather aligns by `year` with yield so the analysis mart produces a
  real correlation.
- **Growing season (inherited):** Apr 1 – Oct 31; **GDD base 10 °C** (50 °F);
  heat-stress day `Tmax > 30 °C`; dry day `precipitation < 1 mm`.
- **State-level yields → county-only analysis mart.** Weather is sampled only at
  county centroids, so `weather_yield_analysis` is **county-grain only**. STATE
  agg-level rows are still modeled in `fact_crop_yield` (carried by an `agg_level`
  column) but excluded from the analysis mart — there is no county-centroid weather
  to join them to. The `fips → dim_county` relationship test applies to COUNTY rows
  only (test-level `where` filter).
- **`fact_weather_daily` is incremental from the start.** Built as an incremental
  model (partitioned by `date`, `insert_overwrite` by partition, unique key
  `fips,date`) to demonstrate the pattern and match the DATA_MODEL note, even though
  the single-window slice would also fit a plain table.
- **Yield item = grain yield in `BU / ACRE` only.** NASS returns multiple YIELD
  items per commodity (corn GRAIN bu/acre vs corn SILAGE tons/acre). `stg_nass_yield`
  keeps only the grain yield measured in `BU / ACRE` (corn grain, soybeans) and drops
  silage / non-bu·acre items, so `(fips, commodity, year)` is a unique, comparable
  grain. Exact `short_desc` values are confirmed against the landed data while
  building.
- **t/ha conversion alongside bu/acre.** Every yield-bearing model exposes a second
  yield column, `yield_value_t_ha` (tonnes/hectare), next to `yield_value` (bu/acre) —
  a unit LATAM audiences read more naturally. The factor is **crop-specific** (bushel
  weight: corn 56 lb, soybeans 60 lb): corn ×`0.0627677`, soybeans ×`0.0672511`
  (`lb/bu × 0.45359237 kg/lb ÷ 1000 ÷ 0.40468564 ha/acre`). The arithmetic lives in a
  single macro (`bu_acre_to_t_ha`), computed **once in `stg_nass_yield`** and carried
  forward through `fact_crop_yield` and `weather_yield_analysis`; `dim_commodity`
  records the underlying `bushel_weight_lb` for discoverability.
- **dbt-on-fixed-datasets:** models write to the **existing** Terraform datasets
  (`staging`, `marts`) via a `generate_schema_name` override that returns the
  configured schema verbatim (no `<target>_<schema>` prefixing). Local auth is **ADC
  / `oauth`**; the CI/Composer service-account target is wired later (Phases 4/6).
- **Test scope split:** Phase 3 ships the **structural** tests that define correctness
  (grain `unique`/`not_null`, `relationships`, `accepted_values`) and full
  model/column docs. The **plausibility/range** suite, `dbt_expectations`, **source
  freshness**, and **bronze→raw reconciliation** are deferred to Phase 5 — mirroring
  how Phase 2 deferred the DQ suite.

## In scope

- dbt Core project scaffolding: `dbt_project.yml`, `packages.yml` (`dbt_utils`),
  in-repo env-driven `profiles.yml`, `generate_schema_name` + `bu_acre_to_t_ha`
  macros; `dbt-bigquery` pinned into the `uv` tooling deps.
- Repo glue: `make dbt-*` targets, `sqlfluff` switched to the dbt templater +
  `make sql-lint` activated, sqlfluff pre-commit hook, docs.
- Sources for `raw.weather_daily` / `raw.nass_yield`; seed config for
  `county_centroids.csv`.
- Staging views: `stg_weather_daily`, `stg_nass_yield`.
- Intermediate: `int_weather_growing_season`.
- Marts (tables, partitioned + clustered): `dim_county`, `dim_commodity`, `dim_date`,
  `fact_weather_daily` (incremental), `fact_crop_yield`, `weather_yield_analysis`.
- Structural dbt tests + model/column descriptions; `dbt docs generate` lineage.

## Out of scope

- Orchestration / Composer DAGs — **Phase 4**.
- Expanded data quality: `dbt_expectations`, range/plausibility singular tests,
  `dbt source freshness`, bronze→raw→staging reconciliation — **Phase 5**.
- CI wiring of `dbt build` / Slim CI / deferral against the `dbt_ci` dataset — **Phase 6**.
- State-level weather aggregation; years ≠ 2025; states / commodities outside the slice.

## Requirements

### Project setup & repo glue

- **FR-1** A dbt Core project exists (`dbt/dbt_project.yml`, profile `wcy`) with
  `packages.yml` pinning **`dbt_utils`** and an in-repo `dbt/profiles/profiles.yml`
  that is **fully env-driven** (project id + datasets from env vars, **no secrets,
  no hardcoded ids**). A `generate_schema_name` macro maps folder-level
  `+schema: staging|marts` to those **literal** datasets in every target. `dbt-bigquery`
  is pinned into the root `uv` dev/tooling deps (Python 3.12). **Done:** `dbt deps`
  installs `dbt_utils`; `dbt debug` connects to BigQuery via ADC.
- **FR-2** Repo glue: `make dbt-deps|dbt-seed|dbt-build|dbt-test|dbt-docs` targets;
  `.sqlfluff` templater switched to **dbt** and `make sql-lint` activated (no longer a
  `|| true` placeholder); a `sqlfluff` **pre-commit** hook added; ingestion-style docs
  note for running dbt. **Done:** `make sql-lint` lints real models; `make dbt-build`
  runs the project.

### Sources & seed

- **FR-3** A `sources.yml` declares `raw.weather_daily` and `raw.nass_yield` (dataset
  from a project var/env). **No freshness rules yet** (Phase 5). **Done:** `{{ source(...) }}`
  resolves and staging builds on it.
- **FR-4** `county_centroids.csv` is configured as a dbt **seed** with **explicit
  column types** — `fips` typed **STRING** so 5-digit leading zeros survive (note: the
  5 states are all FIPS ≥ 17, but the contract must not depend on that). Loads to the
  `staging` (or `marts`) dataset and feeds `dim_county`. **Done:** `dbt seed` loads 474
  rows; `fips` is STRING, never coerced to INT.

### Staging (views)

- **FR-5** `stg_weather_daily` — typed/renamed passthrough of `raw.weather_daily`;
  **dedupe on `(fips, date)`** keeping the latest `_ingested_at` (`row_number()`).
  Grain `(fips, date)`.
- **FR-6** `stg_nass_yield` — (a) build `fips = lpad(state_fips_code,2,'0') ||
  lpad(county_code,3,'0')` (5-digit); (b) parse `value_raw` → numeric `yield_value`
  (strip thousands separators), **null out suppression flags** (`(D)`, `(Z)`, …);
  (c) keep `statisticcat_desc = 'YIELD'` **and the grain yield in `BU / ACRE`**
  (exclude silage / non-bu·acre); (d) standardize `commodity` to a lowercase enum
  (`corn`, `soybeans`); (e) compute `yield_value_t_ha` via the `bu_acre_to_t_ha`
  macro (crop-specific factor); (f) carry `agg_level_desc`, `state_alpha`, `unit`.
  Grain `(agg_level, fips, commodity, year)`; for COUNTY rows the grain is
  `(fips, commodity, year)`.

### Intermediate

- **FR-7** `int_weather_growing_season` — aggregate `stg_weather_daily` into per
  `(fips, year)` features over the season window (driven by `growing_season_start` /
  `growing_season_end` dbt vars, defaulting Apr 1 / Oct 31, applied defensively even
  though the slice is already that window): `gdd` (Σ max(0, (tmax+tmin)/2 − 10)),
  `precip_total_mm`, `heat_stress_days` (Tmax > 30 °C), `dry_days` (precip < 1 mm),
  `et0_total_mm`, `radiation_mean`, `tmax_mean`, `tmin_mean`. Grain `(fips, year)`;
  `gdd ≥ 0`, `precip_total_mm ≥ 0` by construction.

### Marts — dimensions (tables)

- **FR-8** `dim_county` — from the seed: `fips, state_alpha, county_name, lat, lon`.
  Grain `fips`.
- **FR-9** `dim_commodity` — `commodity` (`corn`/`soybeans`), `display_name`,
  `gdd_base_c` (10), `bushel_weight_lb` (corn 56, soy 60 — the physical basis of the
  t/ha factor). Grain `commodity`.
- **FR-10** `dim_date` — calendar dimension covering the data: `date`, `year`,
  `month`, `day`, `day_of_year`, `is_growing_season` flag. Grain `date`.

### Marts — facts (tables, partitioned + clustered)

- **FR-11** `fact_weather_daily` — **incremental**, daily grain `(fips, date)`,
  `_ingested_at`; **partition by `date`, cluster by `fips`**, `insert_overwrite` by
  partition, unique key `fips,date`. FK `fips → dim_county`.
- **FR-12** `fact_crop_yield` — `(agg_level, fips, commodity, year)` grain with
  `yield_value`, `yield_value_t_ha`, `unit`, `agg_level`, `state_alpha`; **includes
  COUNTY and STATE** rows.
  **Partition by `year`, cluster by `state_alpha, commodity`.** `fips → dim_county`
  tested for **COUNTY rows only**.

### Marts — analysis (headline)

- **FR-13** `weather_yield_analysis` — **county-grain only**: join
  `fact_crop_yield` (`agg_level = 'COUNTY'`) to `int_weather_growing_season` on
  `(fips, year)` and `dim_county` on `fips`. Columns: `fips, state_alpha, county_name,
  commodity, year, yield_value, yield_value_t_ha, unit, gdd, precip_total_mm,
  heat_stress_days, dry_days, et0_total_mm, tmax_mean`. **Partition by `year`, cluster
  by `state_alpha, commodity`.**
  Grain `(fips, commodity, year)`.

### Tests & docs

- **FR-14** Structural dbt tests per the DATA_MODEL matrix: `unique` (often a
  `dbt_utils.unique_combination_of_columns`) and `not_null` on each grain;
  `relationships` (`fips → dim_county` with a COUNTY `where` filter on
  `fact_crop_yield`; `commodity → dim_commodity`); `accepted_values` (`commodity` ∈
  {corn,soybeans}, `agg_level` ∈ {COUNTY,STATE}). Plausibility/range/freshness tests
  are **Phase 5**.
- **FR-15** Every model and column has a **description** in its schema yml;
  `dbt docs generate` renders the lineage graph.

## Verification (DoD)

- **V-1** `make lint` (ruff) and `make sql-lint` (sqlfluff, dbt templater) are green;
  the sqlfluff pre-commit hook runs.
- **V-2** `dbt deps` + `dbt seed` + `dbt build` complete **green** (all models + all
  structural tests) against a developer BigQuery target.
- **V-3** `weather_yield_analysis` is populated, **unique on `(fips, commodity, year)`**,
  county-grain only, and returns sane numbers for a known county-year (Corn Belt corn
  yield ≈ **150–200 bu/acre**, 2025).
- **V-4** `fact_weather_daily` is genuinely **incremental** — a second `dbt build`
  performs an incremental (not full-refresh) run — and is partitioned by `date`,
  clustered by `fips`.
- **V-5** `dbt docs generate` succeeds; every model/column carries a description and
  the lineage graph renders.
- **V-6** No secrets or hardcoded project/dataset ids in `profiles.yml` or the repo;
  local auth is ADC / `oauth`.
- **V-7** *(manual, needs GCP)* the full `dbt build` runs end-to-end against BigQuery
  for the 2025 slice; re-running is stable (idempotent marts, incremental weather fact).

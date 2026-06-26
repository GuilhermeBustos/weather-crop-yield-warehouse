# Phase 3 — Tasks

Atomic tasks for the dbt transformation layer. Models live under `dbt/models/`
(`staging/`, `intermediate/`, `marts/`); macros under `dbt/macros/`; the seed is
already in `dbt/seeds/`. `[P]` = parallelizable once deps are met.

| # | Task | Files | Depends on | Done when |
|---|------|-------|-----------|-----------|
| T1 | dbt project scaffolding + env-driven profile + `generate_schema_name` macro; pin `dbt-bigquery` in `uv` tooling deps | `dbt/dbt_project.yml`, `dbt/packages.yml`, `dbt/profiles/profiles.yml`, `dbt/macros/generate_schema_name.sql`, root `pyproject.toml`, `uv.lock` | — | `dbt deps` installs `dbt_utils`; `dbt debug` connects via ADC; folder `+schema` maps to literal `staging`/`marts`; no secrets/ids hardcoded |
| T2 | Repo glue: `make dbt-*` targets, switch `.sqlfluff` to dbt templater + activate `sql-lint`, add sqlfluff pre-commit hook, docs note | `Makefile`, `.sqlfluff`, `.pre-commit-config.yaml`, `dbt/README.md` (or docs) | T1 | `make sql-lint` lints real models; `make dbt-build` runs; pre-commit hook present |
| T3 | Sources for `raw.weather_daily` / `raw.nass_yield` (dataset via var; no freshness yet) | `dbt/models/staging/_sources.yml` | T1 | `{{ source('raw', …) }}` resolves; staging compiles against it |
| T4 | Seed config for `county_centroids.csv` (explicit types, `fips` STRING) | `dbt/seeds/_seeds.yml` (or `dbt_project.yml` seed config) | T1 | `dbt seed` loads 473 rows; `fips` stays STRING (no leading-zero loss) |
| T5 [P] | `stg_weather_daily` view (type/rename, dedupe `(fips,date)` on latest `_ingested_at`) + schema/tests/docs | `dbt/models/staging/stg_weather_daily.sql`, `…/_stg_weather_daily.yml` | T3 | grain `(fips,date)` unique; one row per point-day; columns documented |
| T6 [P] | `stg_nass_yield` view (build 5-digit `fips`, parse `value_raw`→`yield_value`, null suppression flags, keep grain YIELD in `BU/ACRE`, lowercase commodity enum, add `yield_value_t_ha` via `bu_acre_to_t_ha` macro, carry `agg_level`) + the macro + schema/tests/docs | `dbt/models/staging/stg_nass_yield.sql`, `…/_stg_nass_yield.yml`, `dbt/macros/bu_acre_to_t_ha.sql` | T3 | silage/non-bu·acre dropped; `(fips,commodity,year)` unique for COUNTY rows; suppressed values null; `yield_value_t_ha` populated (corn ×0.0627677, soy ×0.0672511) |
| T7 | `int_weather_growing_season` (GDD base 10 °C, precip total, heat-stress/dry days, et0, radiation, tmax/tmin means; season-window vars) + tests/docs | `dbt/models/intermediate/int_weather_growing_season.sql`, `…/_int_weather_growing_season.yml` | T5 | grain `(fips,year)` unique; `gdd ≥ 0`, `precip_total_mm ≥ 0`; window driven by vars |
| T8 [P] | `dim_county` from the seed | `dbt/models/marts/dim_county.sql`, `…/_dim_county.yml` | T4 | grain `fips` unique; `fips,state_alpha,county_name,lat,lon` present + documented |
| T9 [P] | `dim_commodity` (`commodity`, `display_name`, `gdd_base_c`=10, `bushel_weight_lb`=56/60) | `dbt/models/marts/dim_commodity.sql`, `…/_dim_commodity.yml` | T1 | grain `commodity` unique; corn + soybeans rows; `bushel_weight_lb` set |
| T10 [P] | `dim_date` calendar dim (year/month/day/day_of_year, `is_growing_season`) | `dbt/models/marts/dim_date.sql`, `…/_dim_date.yml` | T1 | grain `date` unique; covers the slice; season flag correct |
| T11 | `fact_weather_daily` — **incremental** (partition `date`, cluster `fips`, `insert_overwrite`, unique key `fips,date`) + tests (FK `fips→dim_county`) | `dbt/models/marts/fact_weather_daily.sql`, `…/_fact_weather_daily.yml` | T5, T8 | first run full, second run incremental (no full refresh); grain `(fips,date)` unique; `fips` relationship passes |
| T12 | `fact_crop_yield` — table (partition `year`, cluster `state_alpha,commodity`), keeps COUNTY+STATE via `agg_level` + tests | `dbt/models/marts/fact_crop_yield.sql`, `…/_fact_crop_yield.yml` | T6, T8 | grain `(agg_level,fips,commodity,year)` unique; carries `yield_value` + `yield_value_t_ha`; `fips→dim_county` tested for COUNTY-only (`where`); `agg_level` accepted_values |
| T13 | `weather_yield_analysis` — county-only join (fact_crop_yield COUNTY × int_weather_growing_season × dim_county), partition `year`, cluster `state_alpha,commodity` + tests | `dbt/models/marts/weather_yield_analysis.sql`, `…/_weather_yield_analysis.yml` | T7, T8, T12 | grain `(fips,commodity,year)` unique; all DATA_MODEL columns present; populated |
| T14 | Complete the structural test matrix across models (`unique`/`not_null`/`relationships`/`accepted_values`) per DATA_MODEL | the `_*.yml` from T5–T13 | T11, T12, T13 | every grain + key relationship from the DATA_MODEL test table is covered; `dbt test` green |
| T15 | Model + column descriptions everywhere; `dbt docs generate` | the `_*.yml` files | T13 | every model/column documented; lineage graph renders |
| T16 | Verify + record Phase 3 decisions | `docs/IMPLEMENTATION_PLAN.md` (§8) | T1–T15 | `make lint` + `make sql-lint` + `dbt build` green; sanity corn yield ≈ 150–200 bu/acre; decisions logged |

## Notes on tricky tasks

- **T1 — `generate_schema_name`.** dbt's default `generate_schema_name` produces
  `<target_schema>_<custom_schema>`. Override it to return the **custom schema
  verbatim** (`staging`, `marts`) so models land in the existing Terraform datasets
  rather than `dev_staging` etc. The profile's `dataset:` (target schema) becomes the
  fallback for models without an explicit `+schema`. Keep all ids in env vars
  (`DBT_BQ_PROJECT`, `DBT_RAW_DATASET`, …) referenced via `env_var()` — nothing
  hardcoded, no keyfile committed.
- **T6 — yield-item filter.** Confirm the exact `short_desc` strings that landed
  (corn grain ≈ `CORN, GRAIN - YIELD, MEASURED IN BU / ACRE`; soy ≈
  `SOYBEANS - YIELD, MEASURED IN BU / ACRE`) before hardcoding the filter; prefer
  filtering on `statisticcat_desc = 'YIELD'` **and** `unit_desc = 'BU / ACRE'` so a
  `short_desc` wording change doesn't silently drop rows. Strip thousands separators
  from `value_raw`; map suppression flags (`(D)`, `(Z)`, `(NA)`, …) to NULL.
- **T6 — `bu_acre_to_t_ha` macro.** Single source of truth for the conversion:
  `case lower(commodity) when 'corn' then yield * 0.0627677 when 'soybeans' then yield
  * 0.0672511 end` (NULL for anything else, so a new crop fails loudly rather than
  silently mis-converting). Factor = `bushel_lb × 0.45359237 ÷ 1000 ÷ 0.40468564`
  (corn 56 lb, soy 60 lb). Compute `yield_value_t_ha` **once** in `stg_nass_yield`;
  fact + mart just select it forward (no recompute). `dim_commodity.bushel_weight_lb`
  documents the physical constant the factor derives from.
- **T11 — incremental config.** Use
  `{{ config(materialized='incremental', incremental_strategy='insert_overwrite',
  partition_by={'field':'date','data_type':'date'}, cluster_by=['fips'],
  unique_key=['fips','date']) }}` with an `{% if is_incremental() %}` date predicate.
  V-4 checks the second build is an incremental run, not a full refresh.
- **T12 / T13 — STATE rows.** `fact_crop_yield` carries both agg levels; the
  `fips→dim_county` `relationships` test uses a `config: {where: "agg_level = 'COUNTY'"}`
  so STATE rows (FIPS `xx000`, no centroid) don't fail it. `weather_yield_analysis`
  filters `agg_level = 'COUNTY'` in the join, so it never sees STATE rows.

## Manual bootstrap (user, outside the code — needs GCP)

1. `gcloud auth application-default login` (ADC for the `dev`/`oauth` target).
2. Export dbt env: `DBT_BQ_PROJECT`, `DBT_RAW_DATASET=raw`, `DBT_STAGING_DATASET=staging`,
   `DBT_MARTS_DATASET=marts`, `DBT_BQ_LOCATION=US`, `DBT_PROFILES_DIR=dbt/profiles`
   (or `make` exports it).
3. `make dbt-deps` → `make dbt-seed` → `make dbt-build`.
4. Spot-check `marts.weather_yield_analysis` for a known Corn Belt county-year
   (corn ≈ 150–200 bu/acre, 2025); confirm grain uniqueness.
5. Re-run `make dbt-build`; confirm marts are stable and `fact_weather_daily` runs
   incrementally.

## Sequencing (suggested)

```
T1 ─┬─ T2
    ├─ T3 ─┬─ T5 ─── T7 ─┐
    │      └─ T6 ───── T12┤
    ├─ T4 ─── T8 ─────────┼─ T11 ┐
    ├─ T9 ────────────────┤      ├─ T13 → T14 → T15 → T16
    └─ T10 ───────────────┘      │
                       (T13 needs T7, T8, T12)
```

`[P]` staging models (T5, T6) and dims (T8, T9, T10) can each be built by a separate
sub-agent in parallel once T1/T3/T4 land, then joined at the facts and the analysis
mart. T14/T15 sweep tests + docs across everything before the final T16 verify.

# Data Model

The warehouse follows a medallion layout in BigQuery. Column lists below are the target
contract — treat them as a starting point and refine as you build the dbt models.

```
GCS bronze (Parquet)  ->  BigQuery raw  ->  staging (dbt views)  ->  marts (dbt tables)
```

---

## Layer overview

| Layer | Dataset | Materialization | Purpose |
|---|---|---|---|
| Bronze | GCS bucket | Parquet files | Raw API responses, immutable, partitioned by ingest date/year. |
| Raw | `raw` | Native tables | Loaded bronze, minimally typed. Source of truth for dbt. |
| Staging | `staging` | Views | Cleaned, renamed, typed, deduplicated, units standardized. |
| Marts | `marts` | Tables (partitioned + clustered) | Dimensional model + analysis mart. |

---

## Raw layer

### `raw.weather_daily`
One row per (county point, date). Loaded from Open-Meteo bronze.

| Column | Type | Notes |
|---|---|---|
| `fips` | STRING | County FIPS (carried from the request). |
| `latitude` / `longitude` | FLOAT64 | Queried point. |
| `date` | DATE | Observation day. |
| `temperature_2m_max/min/mean` | FLOAT64 | °C. |
| `precipitation_sum` | FLOAT64 | mm. |
| `et0_fao_evapotranspiration` | FLOAT64 | mm. |
| `shortwave_radiation_sum` | FLOAT64 | MJ/m². |
| `windspeed_10m_max` | FLOAT64 | km/h. |
| `_ingested_at` | TIMESTAMP | Load metadata. |

Partition by `date`; cluster by `fips`.

### `raw.nass_yield`
One row per NASS record. Loaded from NASS bronze (kept close to source).

| Column | Type | Notes |
|---|---|---|
| `year` | INT64 | Crop year. |
| `state_alpha` | STRING | 2-letter state. |
| `state_fips_code` | STRING | |
| `county_code` | STRING | 3-digit. |
| `county_name` | STRING | |
| `commodity_desc` | STRING | `CORN` / `SOYBEANS`. |
| `statisticcat_desc` | STRING | `YIELD`. |
| `short_desc` | STRING | Fully-qualified data item. |
| `unit_desc` | STRING | e.g. `BU / ACRE`. |
| `value_raw` | STRING | Raw `Value` (may contain suppression flags). |
| `_ingested_at` | TIMESTAMP | |

Partition by `year`; cluster by `state_alpha`, `commodity_desc`.

---

## Staging layer (dbt views)

### `stg_weather_daily`
Typed/cleaned passthrough of `raw.weather_daily`; dedupe on `(fips, date)` keeping latest
`_ingested_at`.

### `stg_nass_yield`
- Build `fips = state_fips_code || county_code` (5 digits).
- Parse `value_raw` → numeric `yield_value` (bu/acre); null out suppressed values
  (`(D)`, `(Z)`, …).
- Add `yield_value_t_ha` (tonnes/hectare) via the `bu_acre_to_t_ha` macro —
  crop-specific factor (corn ×0.0627677, soy ×0.0672511; from bushel weights 56/60 lb).
- Keep only `statisticcat_desc = 'YIELD'` grain yield in `BU / ACRE`; standardize
  `commodity` to lowercase enum.
- Grain: `(fips, commodity, year)`.

---

## Intermediate layer (dbt)

### `int_weather_growing_season`
Aggregate `stg_weather_daily` into per-(fips, year) growing-season features. Growing season
default Apr 1–Oct 31 (record the final choice in the plan's decision log).

| Column | Type | Definition |
|---|---|---|
| `fips` | STRING | |
| `year` | INT64 | |
| `gdd` | FLOAT64 | Σ max(0, (Tmax+Tmin)/2 − base), base 10 °C, season window. |
| `precip_total_mm` | FLOAT64 | Σ precipitation over season. |
| `heat_stress_days` | INT64 | Count of days Tmax > 30 °C. |
| `dry_days` | INT64 | Count of days precipitation < 1 mm. |
| `et0_total_mm` | FLOAT64 | Σ reference evapotranspiration. |
| `radiation_mean` | FLOAT64 | Mean shortwave radiation. |
| `tmax_mean` / `tmin_mean` | FLOAT64 | Seasonal means. |

Grain: `(fips, year)`.

---

## Marts layer (dbt tables)

### Dimensions
- **`dim_county`** — from the `county_centroids` seed: `fips`, `state_alpha`,
  `county_name`, `lat`, `lon`.
- **`dim_commodity`** — `commodity` (`corn`/`soybeans`), display name, default GDD base,
  `bushel_weight_lb` (56/60 — physical basis of the bu/acre → t/ha conversion).
- **`dim_date`** — calendar dimension (year, month, day, season flags).

### Facts
- **`fact_weather_daily`** — daily grain, FK `fips`+`date`. Partition by `date`, cluster by
  `fips`. (Incremental dbt model — this is the largest table.)
- **`fact_crop_yield`** — `(fips, commodity, year)` grain with `yield_value` (bu/acre),
  `yield_value_t_ha` (tonnes/hectare), `unit`. Partition by `year`, cluster by
  `state_alpha`, `commodity`.

### Analysis mart (headline)
**`weather_yield_analysis`** — one row per `(fips, commodity, year)` joining
`fact_crop_yield` to `int_weather_growing_season` and `dim_county`:

| Column | Source |
|---|---|
| `fips`, `state_alpha`, `county_name` | dim_county |
| `commodity` | fact_crop_yield |
| `year` | grain |
| `yield_value`, `yield_value_t_ha`, `unit` | fact_crop_yield |
| `gdd`, `precip_total_mm`, `heat_stress_days`, `dry_days`, `et0_total_mm`, `tmax_mean` | growing-season features |

Partition by `year`; cluster by `state_alpha`, `commodity`. This is the table for
correlation analysis, BI, and any future ML.

---

## Grain & key tests (dbt)

| Model | Grain (unique) | Key relationship tests |
|---|---|---|
| `stg_nass_yield` | `fips, commodity, year` | — |
| `int_weather_growing_season` | `fips, year` | — |
| `fact_crop_yield` | `fips, commodity, year` | `fips` → `dim_county` |
| `fact_weather_daily` | `fips, date` | `fips` → `dim_county` |
| `weather_yield_analysis` | `fips, commodity, year` | `fips` → `dim_county`; `commodity` → `dim_commodity` |

Add range/plausibility tests (yields, temperatures, GDD ≥ 0, precip ≥ 0) per Phase 5 of the
implementation plan.

# Data Sources Reference

Concrete reference for the two external APIs the pipeline ingests. Verify exact parameter
names and limits against the official docs while implementing — these change occasionally.

---

## 1. Open-Meteo — Historical Weather API

Free historical reanalysis weather (ERA5 / ERA5-Land), the weather backbone of the project.

- **Docs:** https://open-meteo.com/en/docs/historical-weather-api
- **Base URL:** `https://archive-api.open-meteo.com/v1/archive`
- **Auth:** none — no API key, no sign-up.
- **Limits (non-commercial):** up to **10,000 API calls/day** free. No hard per-second
  limit documented, but be polite (backoff on HTTP 429).
- **Coverage:** hourly & daily data from **1940 to present**; ERA5 has a lag of ~5 days for
  the most recent dates. Global ~9–25 km resolution.
- **Data source:** ERA5 reanalysis from the Copernicus Climate Change Service / ECMWF.
- **Formats:** JSON (default); also supports CSV/`format=flatbuffers`.
- **License:** CC BY 4.0 — attribute Open-Meteo.

### Key request parameters

| Param | Example | Notes |
|---|---|---|
| `latitude`, `longitude` | `41.5,42.0` | Single value or **comma-separated list** for multiple points in one call. |
| `start_date`, `end_date` | `2000-01-01` / `2023-12-31` | ISO `YYYY-MM-DD`. |
| `daily` | `temperature_2m_max,temperature_2m_min,precipitation_sum,...` | Comma-separated daily variables (see below). |
| `hourly` | `temperature_2m,...` | Use daily for this project to keep volume down. |
| `timezone` | `America/Chicago` or `auto` | Affects daily aggregation boundaries. |
| `temperature_unit` | `celsius` | Default celsius; keep SI and convert in dbt if needed. |
| `precipitation_unit` | `mm` | |

### Recommended daily variables

For growing-season features (GDD, heat stress, water):

- `temperature_2m_max`, `temperature_2m_min`, `temperature_2m_mean`
- `precipitation_sum`
- `et0_fao_evapotranspiration`
- `shortwave_radiation_sum`
- `windspeed_10m_max`
- `daylight_duration` (optional)

### Sample request

```
GET https://archive-api.open-meteo.com/v1/archive
  ?latitude=40.05&longitude=-88.37
  &start_date=2020-04-01&end_date=2020-10-31
  &daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration
  &timezone=America/Chicago
```

### Ingestion notes

- **Batch counties:** pass many `latitude`/`longitude` pairs per call (comma-separated) to
  cut call count dramatically during backfill. The response is an array, one block per
  coordinate, in input order.
- **Chunk by date range** per point if a window is large.
- **Cache to bronze:** once a (point, date-range) Parquet is landed, re-runs should read
  the lake, not re-call the API.

---

## 2. USDA NASS — Quick Stats API

The US-government open source for crop yields (and production, acreage). This is the
"yield/productivity" source for the warehouse.

- **Developer docs:** https://www.nass.usda.gov/developer/index.php
- **Quick Stats UI (to explore queries):** https://quickstats.nass.usda.gov/
- **Base URL:** `https://quickstats.nass.usda.gov/api/`
- **Auth:** **free API key required** — request at
  https://quickstats.nass.usda.gov/api/ (an email link). Pass as `key=<API_KEY>`.
  Store it in Secret Manager; never commit it.
- **Limit:** a single `api_GET` call returns at most **50,000 records** — if a query would
  exceed that, the API returns an error. Narrow by `year` and/or `state_alpha`.
- **Formats:** `format=JSON` (default), `CSV`, or `XML`.
- **Coverage:** NASS survey estimates + Census of Agriculture; **county-level** estimates
  available (Quick Stats is the best NASS source for county data).

### Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/api_GET/` | Retrieve data rows for a parameter filter. |
| `GET /api/get_param_values/` | List valid values for a given parameter (great for discovery). |
| `GET /api/get_counts/` | Return the record count for a filter — **call this first** to size a query and avoid the 50k error. |

### Key parameters (filters)

| Param | Example | Notes |
|---|---|---|
| `key` | `<API_KEY>` | Required. |
| `commodity_desc` | `CORN`, `SOYBEANS` | The crop. |
| `statisticcat_desc` | `YIELD` | Also `PRODUCTION`, `AREA HARVESTED`. |
| `agg_level_desc` | `COUNTY`, `STATE`, `NATIONAL` | Geography grain. |
| `year` | `2022` | Repeatable / use `year__GE=2000` operators. |
| `state_alpha` | `IA`, `IL` | Two-letter state; key for paging county queries. |
| `source_desc` | `SURVEY` | `SURVEY` (annual estimates) vs `CENSUS`. |
| `unit_desc` | `BU / ACRE` | Yield unit for grains. |
| `short_desc` | `CORN, GRAIN - YIELD, MEASURED IN BU / ACRE` | Fully-qualified data item; precise filter. |

> Operators are supported via suffixes, e.g. `year__GE`, `year__LE`, `__LIKE`.

### Sample requests

Count first (to stay under 50k):

```
GET https://quickstats.nass.usda.gov/api/get_counts/
  ?key=API_KEY&commodity_desc=CORN&statisticcat_desc=YIELD
  &agg_level_desc=COUNTY&state_alpha=IA&year__GE=2000
```

Then fetch:

```
GET https://quickstats.nass.usda.gov/api/api_GET/
  ?key=API_KEY&commodity_desc=CORN&statisticcat_desc=YIELD
  &agg_level_desc=COUNTY&state_alpha=IA&year__GE=2000&format=JSON
```

### Useful response fields

`year`, `state_alpha`, `state_fips_code`, `county_code`, `county_name`,
`commodity_desc`, `statisticcat_desc`, `short_desc`, `unit_desc`, `Value` (the yield).

> Build the 5-digit county **FIPS** as `state_fips_code` + `county_code` to join with the
> county centroid seed and `dim_county`.

### Ingestion notes

- **Page the backfill** by `(commodity, state_alpha, year-range)` and call `get_counts`
  before each fetch.
- `Value` can contain suppression flags (e.g., `(D)`, `(Z)`) — parse/clean in dbt staging.
- NASS county yields are **annual**, typically finalized in winter following the crop year.

---

## 3. County reference (geographic bridge)

To query Open-Meteo per county and join weather to NASS yields:

- **Source:** US Census Bureau **Gazetteer Files — Counties** (`INTPTLAT`, `INTPTLONG` =
  internal point / centroid). https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
- Produce `dbt/seeds/county_centroids.csv` with: `fips` (5-digit), `state_alpha`,
  `county_name`, `lat`, `lon`.
- Optionally restrict to corn/soy-producing states to bound API volume and cost.

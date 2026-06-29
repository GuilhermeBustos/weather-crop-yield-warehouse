# wcy-ingestion

Extract → land → load for the **weather × crop-yield** warehouse (Phase 2).

Each pipeline pulls from a public API, lands raw **Parquet** in the GCS bronze
bucket (Hive-partitioned at the bucket root), then loads **that Parquet** into a
**BigQuery** `raw` table with an explicit schema and `WRITE_TRUNCATE` (so re-runs
are idempotent). The bronze bucket is the load source — not a side copy.

| Pipeline | Source | Bronze prefix | Raw table |
|---|---|---|---|
| `weather` | [Open-Meteo Archive](https://open-meteo.com/en/docs/historical-weather-api) | `weather_daily/date=…` | `raw.weather_daily` |
| `yield` | [USDA NASS Quick Stats](https://www.nass.usda.gov/developer/index.php) | `nass_yield/year=…` | `raw.nass_yield` |

The `seed` command is local-only: it builds the county-centroid CSV
(`dbt/seeds/county_centroids.csv`) that the weather pipeline reads to know which
coordinates to query.

## Layout

```
src/wcy_ingestion/
  config.py            # env-driven Settings (WCY_ prefix)
  seed.py              # county-centroid seed builder
  clients/             # http (retry policy), openmeteo, nass
  io/                  # secrets, gcs (bronze writer), bigquery (raw loader)
  pipelines/           # weather, nass_yield (extract -> land -> load)
  __main__.py          # CLI: seed / weather / yield
tests/                 # mocked-HTTP suite (respx); no live network
```

## Configuration

Settings are read from the environment (prefix `WCY_`) or a `.env` file at the
repo root. Three are **required**; the rest default to the locked 2025 Corn Belt
slice.

| Env var | Required | Default | Notes |
|---|---|---|---|
| `WCY_BRONZE_BUCKET` | ✅ | — | GCS bucket for bronze Parquet |
| `WCY_NASS_SECRET_ID` | ✅ | — | Secret Manager secret **id** holding the NASS API key |
| `WCY_PROJECT_ID` | — | from ADC | GCP project; discovered from credentials if unset |
| `WCY_RAW_DATASET` | ✅ | — | BigQuery dataset for raw tables |
| `WCY_REGION` | — | `us-central1` | |
| `WCY_TARGET_STATES` | — | `IA,IL,IN,NE,MN` | states for both pipelines |
| `WCY_START_DATE` | — | `2025-04-01` | weather window start |
| `WCY_END_DATE` | — | `2025-10-31` | weather window end |
| `WCY_NASS_YEAR` | — | `2025` | yield year |
| `WCY_BATCH_SIZE` | — | `50` | Open-Meteo coords per request |

Example `.env`:

```dotenv
WCY_PROJECT_ID=my-gcp-project
WCY_BRONZE_BUCKET=my-project-bronze
WCY_NASS_SECRET_ID=nass-api-key
WCY_RAW_DATASET=raw
```

The NASS key itself never goes in env or `.env` — only the **secret id**. The
yield pipeline resolves it at runtime to
`projects/<project>/secrets/<id>/versions/latest` and reads it from Secret
Manager.

## Authentication

Both pipelines use Application Default Credentials. Authenticate once:

```bash
gcloud auth application-default login
```

The principal needs (granted in Phase 1): `secretAccessor` on the NASS secret,
`bigquery.dataEditor` on the `raw` dataset, and `storage.objectAdmin` on the
bronze bucket. `seed` needs none of these — it only downloads a public Census
file and writes a local CSV.

## Running

From the repo root, via `make`:

```bash
make seed             # build dbt/seeds/county_centroids.csv  (review before ingesting)
make ingest-weather   # Open-Meteo  -> bronze -> raw.weather_daily
make ingest-yield     # NASS        -> bronze -> raw.nass_yield
```

Or call the CLI directly:

```bash
uv run python -m wcy_ingestion seed
uv run python -m wcy_ingestion weather
uv run python -m wcy_ingestion yield
```

Re-running any pipeline replaces the bronze prefix and truncates the raw table,
so identical inputs produce identical row counts.

## Testing

```bash
make test     # uv run pytest
```

The suite mocks all HTTP (`respx`) and the GCS/BigQuery clients — it makes **no
live network calls** and needs no credentials.

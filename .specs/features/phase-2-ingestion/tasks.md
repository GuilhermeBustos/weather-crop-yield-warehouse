# Phase 2 — Tasks

Atomic tasks for the ingestion package. Code lives under `ingestion/src/wcy_ingestion/`
(src layout); the seed lands in `dbt/seeds/`. `[P]` = parallelizable once deps are met.

| # | Task | Files | Depends on | Done when |
|---|------|-------|-----------|-----------|
| T1 | Package + pinned runtime deps; register as `uv` workspace member | `ingestion/pyproject.toml`, root `pyproject.toml`, `uv.lock` | — | `uv sync` installs `wcy_ingestion`; `import wcy_ingestion` works; ruff/pytest resolve it |
| T2 | Env-driven settings | `…/config.py` | T1 | all settings typed + defaulted to the locked slice; no secrets in defaults |
| T3 | HTTP policy helper (timeout, backoff+jitter on 429/5xx) | `…/clients/http.py` | T1 | shared retrying client; unit-testable |
| T4 | Secret Manager accessor (NASS key) | `…/io/secrets.py` | T1 | returns key by resource name; never logs it |
| T5 | County-centroid seed builder | `…/seed.py`, `dbt/seeds/county_centroids.csv` | T2 | CSV has only IA/IL/IN/NE/MN, 5-digit `fips`, numeric `lat`/`lon`; committed |
| T6 [P] | Open-Meteo archive client (coord-batched, per-point→fips, flatten to `(fips,date)`) | `…/clients/openmeteo.py` | T2, T3 | batched request built; response mapped in input order; one record per `(fips,date)` |
| T7 [P] | NASS Quick Stats client (`get_counts` gate, paged by commodity×state) | `…/clients/nass.py` | T2, T3, T4 | counts checked < 50k before each fetch; corn/soy YIELD county+state for 2025 |
| T8 | Bronze Parquet writer (partitioned paths, overwrite prefix) | `…/io/gcs.py` | T2 | writes Open-Meteo + NASS partition layouts; re-write replaces the prefix |
| T9 | Raw BigQuery loader (explicit schema, partition+cluster, `WRITE_TRUNCATE`) | `…/io/bigquery.py` | T2 | loads `raw.weather_daily` (part `date`/clust `fips`) and `raw.nass_yield` (part `year`/clust `state_alpha,commodity_desc`); adds `_ingested_at` |
| T10 | Weather pipeline (extract→land→load, idempotent) | `…/pipelines/weather.py` | T6, T8, T9 | one call lands + loads the 2025 season for the 5 states |
| T11 | Yield pipeline (extract→land→load, idempotent) | `…/pipelines/yield.py` | T7, T8, T9 | one call lands + loads corn+soy 2025 yields |
| T12 | CLI entrypoint (`seed`/`weather`/`yield` subcommands) | `…/__main__.py` | T5, T10, T11 | `python -m wcy_ingestion <sub>` runs each pipeline |
| T13 | Pytest suite, mocked HTTP (`respx`) | `ingestion/tests/…` | T6, T7, T8, T9 | batching, retry, parsing, partition pathing, idempotent load covered; no live network |
| T14 | Repo glue: `make` targets + ingestion README | `Makefile`, `ingestion/README.md` | T12 | `make ingest-weather`/`ingest-yield`/`seed`; README documents env + run |
| T15 | Verify + record decisions | `docs/IMPLEMENTATION_PLAN.md` (§8) | T1–T14 | `make lint` + `make test` green; Phase 2 decisions logged |

## Manual bootstrap (user, outside the code — needs GCP)

1. Confirm the NASS API key exists in Secret Manager and note its resource name
   (`projects/<project>/secrets/<name>/versions/latest`).
2. Ensure the pipeline SA (Phase 1) has `secretAccessor` on that secret, plus
   `bigquery.dataEditor` on `raw` and `storage.objectAdmin` on bronze (Phase 1 grants).
3. Export config env (`WCY_PROJECT_ID`, `WCY_BRONZE_BUCKET`, `WCY_NASS_SECRET_NAME`,
   …) or pass via the CLI; authenticate (`gcloud auth application-default login`).
4. `make seed` → review the CSV → `make ingest-weather` and `make ingest-yield`.
5. Spot-check `raw.weather_daily` / `raw.nass_yield` in BigQuery; re-run to confirm
   identical row counts (idempotency).

## Sequencing (suggested)

```
T1 → T2 ──┬─ T3 ─┬─ T6 ─┐
          │      └─ T7 ─┤(needs T4)
          ├─ T4 ────────┤
          ├─ T5         ├─ T10 ┐
          ├─ T8 ────────┤      ├─ T12 → T13 → T14 → T15
          └─ T9 ────────┴─ T11 ┘
```

`[P]` clients (T6, T7) and the IO modules (T8, T9) can each be built by a separate
sub-agent in parallel once T2–T4 land, then joined at the pipelines.

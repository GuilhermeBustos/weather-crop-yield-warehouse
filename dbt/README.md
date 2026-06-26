# dbt — weather-crop-yield warehouse

Transforms `raw.*` tables into a clean, tested analytical layer in BigQuery.
Models follow the staging → intermediate → marts pattern.

## Prerequisites

- GCP auth: `gcloud auth application-default login`
- Environment variables (add to your shell profile or a local `.env`):

```sh
export DBT_BQ_PROJECT=<your-gcp-project-id>
export DBT_RAW_DATASET=raw
export DBT_STAGING_DATASET=staging
export DBT_MARTS_DATASET=marts
export DBT_BQ_LOCATION=US
export DBT_PROFILES_DIR=dbt/profiles
```

## Running dbt

All targets are wired through `make` from the repo root:

| Command | Description |
|---------|-------------|
| `make dbt-deps` | Install packages from `packages.yml` (`dbt_utils`) |
| `make dbt-seed` | Load `county_centroids.csv` into BigQuery |
| `make dbt-build` | Run all models + all structural tests |
| `make dbt-test` | Run tests only (no model rebuild) |
| `make dbt-docs` | Generate HTML docs + lineage graph |
| `make sql-lint` | Lint SQL with sqlfluff (dbt templater) |

First-time bootstrap:

```sh
make dbt-deps
make dbt-seed
make dbt-build
```

## Project layout

```
dbt/
├── dbt_project.yml          # project config; folder → dataset mapping
├── packages.yml             # dbt_utils
├── profiles/profiles.yml    # env-driven BigQuery profile (no secrets)
├── macros/
│   ├── generate_schema_name.sql  # maps +schema to literal BQ dataset
│   └── bu_acre_to_t_ha.sql       # unit-conversion macro
├── seeds/
│   └── county_centroids.csv      # 473 rows; fips typed STRING
└── models/
    ├── staging/             # views; dedupe + type raw tables
    ├── intermediate/        # views; season-level aggregations
    └── marts/               # tables; dims, facts, analysis mart
```

## SQL linting

sqlfluff is configured with the **dbt templater** (`.sqlfluff` at the repo root)
and runs automatically via the pre-commit hook on staged `.sql` files, or
manually with `make sql-lint`.

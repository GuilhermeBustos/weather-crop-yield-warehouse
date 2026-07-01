# Phase 5 — Tasks

Atomic tasks for the data-quality layer. dbt tests live in the model `_*.yml`
(declarative) and `dbt/tests/*.sql` (singular); pytest lives in
`ingestion/tests/`; docs + glue in `docs/`, `Makefile`, `dbt/README.md`. `[P]` =
parallelizable once deps are met. Each task traces to a spec **FR**; the
bad-row / freshness demonstrations (V-2/V-3) are manual GCP steps, mirroring how
Phases 3–4 deferred the live run.

| # | Task | Files | FR | Depends on | Done when |
|---|------|-------|----|-----------| ----------|
| T1 | Add `dbt_expectations` to `packages.yml` (pinned range), refresh `package-lock.yml`; confirm `make dbt-deps` installs it | `dbt/packages.yml`, `dbt/package-lock.yml` | FR-1 | — | `make dbt-deps` installs `dbt_utils` + `dbt_expectations`; a `dbt_expectations.*` macro resolves |
| T2 [P] | Weather range/plausibility tests: temp bounds [−50,55] °C, `precip/et0/radiation ≥ 0` on `stg_weather_daily` (mirrored on `fact_weather_daily`), season-feature bounds (`gdd/precip/et0 ≥ 0`, `heat_stress_days`/`dry_days ∈ [0,214]`) on `int_weather_growing_season` (mirrored on `weather_yield_analysis`), **+ a singular test** `tmax ≥ tmin` | `dbt/models/staging/_stg_weather_daily.yml`, `dbt/models/intermediate/_int_weather_growing_season.yml`, `dbt/models/marts/_fact_weather_daily.yml`, `dbt/models/marts/_weather_yield_analysis.yml`, `dbt/tests/assert_tmax_ge_tmin.sql` | FR-2 | T1 | tests present + green on the slice; a 999 °C row would fail the bound; `tmax<tmin` fails the singular test |
| T3 [P] | Yield range/plausibility tests: per-commodity `yield_value` bounds via `row_condition` split (corn (0,400], soy (0,150], skip suppressed NULLs), `yield_value_t_ha ≥ 0` on `stg_nass_yield` (mirrored on `fact_crop_yield` / `weather_yield_analysis`) | `dbt/models/staging/_stg_nass_yield.yml`, `dbt/models/marts/_fact_crop_yield.yml`, `dbt/models/marts/_weather_yield_analysis.yml` | FR-2 | T1 | tests green on the slice; a negative yield fails the bound; suppressed NULLs don't trip it |
| T4 [P] | Source freshness: `loaded_at_field: _ingested_at` + `freshness` (`warn_after`/`error_after` nominal) on both raw sources; `make dbt-freshness` target; README note that the frozen slice reports stale **by design** and freshness is **not** in `dbt build` | `dbt/models/staging/_sources.yml`, `Makefile`, `dbt/README.md` | FR-3 | — | `make dbt-freshness` runs `dbt source freshness` and flags both sources stale; `dbt build` unaffected |
| T5 [P] | raw→staging reconciliation singular tests: weather `count(stg) == count(distinct fips,date of raw)`; NASS `count(stg) == count(raw rows passing the documented county/YIELD/BU·ACRE filter)` | `dbt/tests/reconcile_weather_raw_staging.sql`, `dbt/tests/reconcile_nass_raw_staging.sql` | FR-4 | — | both tests green on the slice; a deliberate staging row drop fails them |
| T6 [P] | pytest for pipelines: `weather.run` + `nass_yield.run` — mock `clients.*`/`io.*`; assert extract→land→load ordering + arg wiring, single uniform `_ingested_at` stamp, NASS secret resource-name, `_load_centroids` parse | `ingestion/tests/test_pipeline_weather.py`, `ingestion/tests/test_pipeline_nass_yield.py` | FR-5 | — | `pytest` covers both `run()`; wrong ordering / mis-stamped `_ingested_at` fails |
| T7 [P] | pytest for `config.py` (`Settings` env+defaults, `_discover_project_id` fallback **and** raise), `io/secrets.py` (mocked `SecretManagerServiceClient` + decode), `seed.py` (`build` state filter + `fips` from `GEOID` + deterministic sort; Gazetteer fetch mocked) | `ingestion/tests/test_config.py`, `ingestion/tests/test_secrets.py`, `ingestion/tests/test_seed.py` | FR-6 | — | three modules covered; `make test` green |
| T8 | Test catalog doc + glue: enumerate every test class (structural / range / freshness / reconciliation / pytest), what each guards, how to run; wire `make dbt-freshness` into docs; `dbt/README.md` note | `docs/TEST_CATALOG.md`, `dbt/README.md`, `Makefile` (help text) | FR-7, FR-8 | T2, T3, T4, T5, T6, T7 | catalog covers all classes; run commands documented |
| T9 | Verify + record Phase 5 decisions in `IMPLEMENTATION_PLAN` §8 (dbt_expectations, freshness-stale-as-demo, raw→staging-only reconciliation, pytest gap-fill) | `docs/IMPLEMENTATION_PLAN.md` (§8) | V-1…V-8 | T1–T8 | `dbt build` + `make dbt-freshness` + `make test` + `make sql-lint` green; bad-row fails a test; decisions logged |

## Notes on tricky tasks

- **T1 — second dbt package.** `dbt_expectations` depends on `dbt_utils`
  (already present) and on `dbt-labs/dbt_date`; `dbt deps` pulls both — verify
  `package-lock.yml` records all three. Pin a compatible range (e.g.
  `[">=0.10.0", "<0.11.0"]`); confirm against the installed `dbt-bigquery` /
  dbt-core version.
- **T2/T3 — `expect_column_values_to_be_between` + NULLs.** By default the macro
  counts NULLs as failures; suppressed yields are legitimately NULL, so pass
  `row_condition: "yield_value is not null"` (combined with the per-commodity
  filter). Per-commodity bounds need two test entries (corn vs soybeans), each
  with `row_condition: "commodity = '<c>' and yield_value is not null"`. Mirror
  the same bound on downstream models so a regression is caught at every layer,
  not just staging. Keep bounds **generous/physical**, not tight — this is
  plausibility, not a model of expected yields.
- **T4 — freshness is standalone, and stale is expected.** `dbt source
  freshness` is a **separate command**, never part of `dbt build`, so the
  always-stale frozen slice never breaks a build. The stale result *is* the
  deliverable (proves detection). Document this in `dbt/README.md` and the
  decision log so a reviewer doesn't read it as a failure. `_ingested_at` is
  `TIMESTAMP` — a valid `loaded_at_field` with no casting needed.
- **T5 — reconciliation catches silent loss, not just grain.** Structural
  `unique`/`not_null` already guard the grain; reconciliation guards the
  **count** across the parse/filter/dedup boundary. Weather: staging dedups, so
  `count(stg) == count(distinct fips,date)` of raw. NASS: staging filters to real
  county + `YIELD` + `BU / ACRE`, so assert `count(stg)` equals the raw count
  under that **exact** documented predicate — encode the predicate once so it
  can't drift from `stg_nass_yield`. A singular test passes when it returns **zero
  rows**: `select ... where staging_count != source_count`.
- **T6 — assert the idempotency contract, don't reimplement.** The pipelines
  stamp one `_ingested_at = datetime.now(UTC)` across **all** records so bronze
  and raw agree; patch `datetime` (or capture the records passed to
  `gcs.write_parquet`) and assert every record shares one timestamp. Assert the
  call order/args to `write_parquet` then `load_*` (bucket/prefix/dataset/
  `partition_by`), and — for NASS — the `projects/.../secrets/.../versions/latest`
  resource name handed to `secrets.get_secret`. Mock all `clients.*`/`io.*`; no
  network, no GCP.
- **T7 — `config.py` two-path project discovery.** `_discover_project_id` calls
  `google.auth.default()`; test both the **found** path (returns the project) and
  the **missing** path (raises `ValueError`) by patching `google.auth.default`.
  Also verify `WCY_`-prefixed env vars override defaults and that required fields
  (`bronze_bucket`, `raw_dataset`, `nass_secret_id`) are enforced. `seed.build`:
  feed a small in-memory Gazetteer zip fixture (patch `urllib.request.urlopen`),
  assert only `target_states` survive, `fips == GEOID`, and the output is sorted
  (deterministic — same input → same file).

## Manual bootstrap (user — outside the code, needs GCP)

Runs against the **existing dev BigQuery** slice (kept after the Phase 4 soft
teardown). If hard-destroyed, `make dbt-build` first to repopulate.

1. `make dbt-deps` → `make dbt-build` — structural + new plausibility +
   reconciliation tests all green.
2. `make dbt-freshness` — both sources report **stale** (the detection demo).
3. Inject a bad row (CTE override / temporary seed edit) → the matching
   range/reconciliation test fails; revert to green.
4. `make test` — pytest green, including the newly covered modules.

## Sequencing (suggested)

```
T1 ─┬─ T2 [P] ┐
    └─ T3 [P] ┤
              ├─ T8 ─ T9
T4 [P] ───────┤
T5 [P] ───────┤
T6 [P] ───────┤
T7 [P] ───────┘
   (T8 needs T2–T7; T9 needs T1–T8)
```

`[P]`: **T2 ∥ T3** (both need only T1); **T4, T5, T6, T7** need nothing new and
run fully in parallel with T2/T3 — ideal one-per-sub-agent fan-out. T8 gathers
the catalog + glue once all suites land; T9 is the final live verify + decision
log.

# Phase 5 — Data quality & testing

Earn trust in the data *and* the code. Phases 2–4 shipped the pipeline and its
**structural** correctness suite (grain `unique`, `not_null`, `relationships`,
`accepted_values`) plus a client/IO pytest suite. Phase 5 adds the layer that
catches *bad values and silent data loss* — range/plausibility tests, source
freshness, raw→staging reconciliation — and closes the remaining pytest gaps
(the pipeline orchestration, config, secrets, and seed modules are currently
untested). The headline deliverable is: **a deliberately bad row (negative
yield, out-of-range temperature) or a broken parse fails the relevant test**,
and a documented **test catalog** enumerating what each test guards.

Companion: [docs/IMPLEMENTATION_PLAN.md](../../../docs/IMPLEMENTATION_PLAN.md) §Phase 5,
[docs/DATA_MODEL.md](../../../docs/DATA_MODEL.md) §Grain & key tests.

## Inputs (from Phases 2–4)

- **dbt (Phase 3):** the `wcy` project — `staging` → `intermediate` → `marts` —
  with the full **structural** test suite already green (grain
  `dbt_utils.unique_combination_of_columns`, `not_null`, `relationships`
  `fips→dim_county` / `commodity→dim_commodity`, `accepted_values` on
  `commodity`). `packages.yml` pins **only `dbt_utils`**. `dbt/tests/` (singular
  tests) is empty. `_sources.yml` declares `raw.weather_daily` / `raw.nass_yield`
  with **no freshness rules** and no `loaded_at_field`.
- **raw layer (Phase 2):** both raw tables carry `_ingested_at`
  (`TIMESTAMP REQUIRED`, stamped once at land time) — the freshness candidate
  field. Bronze→raw loads are `WRITE_TRUNCATE` **straight from the bronze
  Parquet**, so bronze and raw row counts are equal by construction.
- **ingestion pytest (Phase 2):** `clients/` (http 429/retry, NASS count-gate +
  paging + agg-level filter, Open-Meteo batching/pacing) and `io/` (GCS
  partition writes + idempotent prefix-clear, BigQuery bronze-Parquet load) are
  covered. **Untested:** `pipelines/weather.py`, `pipelines/nass_yield.py`,
  `config.py`, `io/secrets.py`, `seed.py`.
- **Slice (inherited):** Core Corn Belt `IA, IL, IN, NE, MN`; `corn`, `soybeans`;
  **2025 only**; growing season Apr 1 – Oct 31 (**214 days**), GDD base 10 °C,
  heat-stress `Tmax > 30 °C`, dry day `precip < 1 mm`.

## Scope decisions (locked)

Resolved with the user before planning:

- **Range/plausibility via `dbt_expectations`.** Add the `dbt_expectations`
  package for declarative range tests (`expect_column_values_to_be_between`),
  with **singular SQL tests** only where a cross-column relationship is needed
  (e.g. `tmax ≥ tmin`). This is a second dbt dependency on top of the Phase 3
  `dbt_utils`-only stance — accepted for readability and as a recognizable,
  portfolio-worthy tool. Per-commodity yield bounds use a `row_condition` split
  (corn vs soybeans) and skip suppressed NULLs (`row_condition: yield_value is
  not null`).
- **Source freshness: stale IS the demonstration.** The 2025 slice is a **frozen
  one-shot load** (ingested ~early 2026; today is 2026-07-01), so
  `dbt source freshness` measured against `now()` will **always report stale**.
  Freshness rules (`loaded_at_field: _ingested_at`, `warn_after` / `error_after`)
  are configured anyway and the stale result is treated as the **intended
  demonstration** of the detection mechanism — matching the DoD "freshness fails
  when raw is stale." Freshness runs via a **separate `dbt source freshness`
  command**, never inside `dbt build`, so green builds are unaffected. Documented
  as by-design in the decision log.
- **Reconciliation is raw→staging in dbt only.** Row/key-count parity is checked
  **inside BigQuery via dbt singular tests** (no GCS reads, no new GCP surface).
  **Bronze→raw parity is not re-tested** — it is guaranteed by the
  `WRITE_TRUNCATE`-from-Parquet load and is instead *documented*. This keeps
  reconciliation lean and fully CI-friendly for Phase 6.
- **Fill the untested Python modules.** Add focused pytest coverage for
  `pipelines/` (orchestration + idempotent-load logic), `config.py` (`Settings`),
  `io/secrets.py` (mocked Secret Manager), and `seed.py` (Gazetteer build). This
  closes the "test idempotent load logic" gap the plan calls out. No coverage-gate
  tooling is introduced (deferred; CI enforcement is Phase 6).

Secondary defaults (resolvable inline, not user-blocking):

- **Plausibility bounds** (generous physical/agronomic limits, not tight fits):
  daily temperature ∈ **[−50, 55] °C**; `tmax ≥ tmin`; corn yield ∈ **(0, 400]**
  bu/acre, soybean yield ∈ **(0, 150]** bu/acre; `yield_value_t_ha ≥ 0`;
  `gdd ≥ 0`, `precip_total_mm ≥ 0`, `et0_total_mm ≥ 0`, `radiation_mean ≥ 0`;
  `heat_stress_days` and `dry_days` ∈ **[0, 214]** (season length).
- **Freshness thresholds** are nominal (e.g. `warn_after: 30 days`,
  `error_after: 60 days`) — enough that the frozen slice trips them, proving
  detection.

## In scope

- dbt: add `dbt_expectations` to `packages.yml`; range/plausibility tests
  (declarative + a few singular SQL) across weather and yield models.
- dbt: source freshness rules on `raw.weather_daily` / `raw.nass_yield`;
  `make dbt-freshness` target.
- dbt: raw→staging reconciliation singular tests (weather dedup parity, NASS
  filtered-count parity).
- pytest: cover `pipelines/weather.py`, `pipelines/nass_yield.py`, `config.py`,
  `io/secrets.py`, `seed.py`.
- Docs: a **test catalog** enumerating every test class and what it guards;
  Makefile/README wiring; decision-log entry.

## Out of scope

- **CI wiring** of any of the above (lint/test/build/freshness on PR, Slim CI,
  deferral) — **Phase 6**.
- Coverage-gate tooling (`pytest-cov` threshold) — deferred to Phase 6 if wanted.
- Bronze→raw reconciliation via GCS reads (documented, not tested — see decision).
- Cost/monitoring/observability (dashboards, budget alerts, runbook) — **Phase 7**.
- Any new data, states, commodities, or years beyond the frozen 2025 slice.

## Requirements

### dbt — range & plausibility (dbt_expectations)

- **FR-1** `dbt_expectations` is pinned in `dbt/packages.yml` and installed;
  `package-lock.yml` updated. **Done:** `make dbt-deps` installs both `dbt_utils`
  and `dbt_expectations`; `dbt` can resolve `dbt_expectations.*` macros.
- **FR-2** Range/plausibility tests exist on the value-bearing columns, using
  `dbt_expectations.expect_column_values_to_be_between` where a single-column
  bound fits and **singular SQL** where a cross-column relationship is needed:
  - **Weather (`stg_weather_daily`, mirrored on `fact_weather_daily`):**
    `temperature_2m_max/min/mean` ∈ [−50, 55] °C; `precipitation_sum ≥ 0`;
    `et0_fao_evapotranspiration ≥ 0`; `solar_radiation_mjm2 ≥ 0`; a **singular
    test** asserting `temperature_2m_max ≥ temperature_2m_min`.
  - **Growing-season features (`int_weather_growing_season`, mirrored on
    `weather_yield_analysis`):** `gdd ≥ 0`; `precip_total_mm ≥ 0`;
    `et0_total_mm ≥ 0`; `radiation_mean ≥ 0`; `heat_stress_days` and `dry_days`
    ∈ [0, 214].
  - **Yield (`stg_nass_yield`, mirrored on `fact_crop_yield` /
    `weather_yield_analysis`):** `yield_value` within per-commodity bounds via a
    `row_condition` split (corn ∈ (0, 400], soybeans ∈ (0, 150]), skipping
    suppressed NULLs (`row_condition: ... and yield_value is not null`);
    `yield_value_t_ha ≥ 0`.
  **Done:** these tests are green on the real 2025 slice, and a deliberately bad
  row (negative yield, 999 °C temperature) fails the corresponding test.

### dbt — source freshness

- **FR-3** `_sources.yml` sets `loaded_at_field: _ingested_at` and a `freshness`
  block (`warn_after` / `error_after`, nominal thresholds) on **both**
  `raw.weather_daily` and `raw.nass_yield`. A `make dbt-freshness` target runs
  `dbt source freshness` **standalone** (never inside `dbt build`). On the frozen
  2025 slice it **reports stale by design** — this is the detection demo, not a
  regression. **Done:** `make dbt-freshness` runs and flags both sources as
  stale; `dbt build` stays green (freshness is not part of it).

### dbt — reconciliation (raw→staging)

- **FR-4** Singular SQL tests under `dbt/tests/` assert **no silent row loss**
  from staging's parse/filter/dedup:
  - **Weather:** `count(stg_weather_daily)` equals `count(distinct (fips, date))`
    of `raw.weather_daily` (staging dedups on latest `_ingested_at`, so it must
    equal the distinct grain — no extra loss, no missing keys).
  - **NASS:** `count(stg_nass_yield)` equals the count of `raw.nass_yield` rows
    passing the documented staging filter (real county rows, `statisticcat_desc =
    'YIELD'`, `unit_desc = 'BU / ACRE'`), so the parse/filter drops exactly the
    intended rows and nothing more.
  Bronze→raw parity is **documented** (guaranteed by `WRITE_TRUNCATE` from the
  bronze Parquet), not re-tested. **Done:** both reconciliation tests pass on the
  real slice; a deliberate row drop in a staging model makes them fail.

### pytest — fill the untested modules

- **FR-5** Unit tests for `pipelines/weather.py` and `pipelines/nass_yield.py`
  (mocking `clients.*` and `io.*`): assert the **extract → land → load** ordering
  and argument wiring (bucket / prefix / dataset / `partition_by`), the **single
  uniform `_ingested_at` stamp** applied to every record (bronze == raw
  idempotency contract), the NASS **secret resource-name** construction, and
  `_load_centroids` CSV parsing. **Done:** `pytest` covers both `run()`
  entrypoints; a mis-stamped `_ingested_at` or wrong load ordering fails a test.
- **FR-6** Unit tests for `config.py` (`Settings` env loading with the `WCY_`
  prefix, defaults, `_discover_project_id` ADC fallback **and** its raise path),
  `io/secrets.py` (mocked `SecretManagerServiceClient`, payload decode), and
  `seed.py` (`build` filters to `target_states`, builds `fips` from `GEOID`,
  sorts deterministically — **idempotent output**; Gazetteer fetch mocked).
  **Done:** all three modules have tests; `make test` runs them green.

### Docs & repo glue

- **FR-7** `make` targets and docs are consistent: `make dbt-freshness` added;
  `make test` and `make dbt-test` documented as running the new suites; a note in
  `dbt/README.md` on running plausibility/freshness/reconciliation.
- **FR-8** A **test catalog** doc (`docs/TEST_CATALOG.md` or a DATA_MODEL
  section) enumerates every test class — structural, range/plausibility,
  freshness, reconciliation, and pytest — and states **what each guards** and how
  to run it. The Phase 5 decisions are recorded in `IMPLEMENTATION_PLAN` §8.

## Verification (DoD)

- **V-1** `make dbt-deps` installs `dbt_utils` + `dbt_expectations`; `dbt build`
  is **green** on the 2025 slice — structural **plus** the new range/plausibility
  and reconciliation tests all pass.
- **V-2** *(manual, needs GCP)* Injecting a bad row (negative/out-of-range yield
  or a 999 °C temperature) **fails** the corresponding range test; reverting
  restores green.
- **V-3** `make dbt-freshness` runs `dbt source freshness` standalone and
  **flags both sources as stale** on the frozen slice (detection demonstrated);
  `dbt build` remains green because freshness is not part of it.
- **V-4** The raw→staging reconciliation tests pass on the real slice, and a
  deliberate row drop in a staging model **makes them fail**.
- **V-5** `make test` (pytest) is green; `pipelines/`, `config.py`,
  `io/secrets.py`, and `seed.py` now have coverage.
- **V-6** A broken parse or a mis-stamped `_ingested_at` in a pipeline **fails**
  a pytest (the code-side counterpart to V-2).
- **V-7** `make lint` (ruff) and `make sql-lint` (sqlfluff, dbt templater) stay
  green with the new SQL tests.
- **V-8** The **test catalog** doc exists and covers every test class; the Phase 5
  decisions (dbt_expectations, freshness-stale-as-demo, raw→staging-only
  reconciliation, pytest gap-fill) are logged in `IMPLEMENTATION_PLAN` §8.

## Manual bootstrap (user — outside the code, needs GCP)

The dbt tests run against the **existing dev BigQuery target** (the 2025 slice
kept after the Phase 4 soft teardown). If the warehouse was hard-destroyed,
re-run `make dbt-build` first to repopulate it.

1. `make dbt-deps` — install `dbt_expectations`.
2. `make dbt-build` — confirm structural + new plausibility + reconciliation
   tests are all green.
3. `make dbt-freshness` — confirm both sources report **stale** (the demo).
4. Inject a bad row (e.g. a CTE override or a temporary seed edit) → confirm the
   matching range/reconciliation test fails; revert.
5. `make test` — confirm the pytest suite (including the new modules) is green.

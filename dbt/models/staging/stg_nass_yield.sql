WITH source AS (
    SELECT * FROM {{ source('raw', 'nass_yield') }}
),

filtered AS (
    SELECT *
    FROM source
    WHERE
        statisticcat_desc = 'YIELD'
        AND unit_desc = 'BU / ACRE'
        AND county_code NOT IN ('000', '998', '')
),

parsed AS (
    SELECT
        state_alpha,
        year,
        unit_desc AS unit,
        _ingested_at,
        LPAD(state_fips_code, 2, '0') || LPAD(county_code, 3, '0') AS fips,
        LOWER(commodity_desc) AS commodity,
        SAFE_CAST(REPLACE(value_raw, ',', '') AS FLOAT64) AS yield_value
    FROM filtered
)

SELECT
    fips,
    commodity,
    state_alpha,
    year,
    unit,
    yield_value,
    {{ bu_acre_to_t_ha('yield_value', 'commodity') }} AS yield_value_t_ha,
    _ingested_at
FROM parsed

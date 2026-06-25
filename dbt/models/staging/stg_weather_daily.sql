WITH source AS (
    SELECT * FROM {{ source('raw', 'weather_daily') }}
),

deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY fips, date
            ORDER BY _ingested_at DESC
        ) AS _row_number
    FROM source
)

SELECT
    fips,
    date,
    temperature_2m_max,
    temperature_2m_min,
    temperature_2m_mean,
    precipitation_sum,
    et0_fao_evapotranspiration,
    shortwave_radiation_sum AS solar_radiation_mjm2,
    windspeed_10m_max AS wind_speed_kmh,
    _ingested_at
FROM deduped
WHERE _row_number = 1

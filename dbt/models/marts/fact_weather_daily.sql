{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'date', 'data_type': 'date'},
    cluster_by=['fips'],
    unique_key=['fips', 'date']
) }}

SELECT
    fips,
    date,
    temperature_2m_max,
    temperature_2m_min,
    temperature_2m_mean,
    precipitation_sum,
    et0_fao_evapotranspiration,
    solar_radiation_mjm2,
    wind_speed_kmh,
    _ingested_at
FROM {{ ref('stg_weather_daily') }}
{% if is_incremental() %}
WHERE date >= (SELECT MAX(date) FROM {{ this }})
{% endif %}

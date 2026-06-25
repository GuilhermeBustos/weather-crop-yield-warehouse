WITH season AS (
    SELECT
        fips,
        temperature_2m_max,
        temperature_2m_min,
        precipitation_sum,
        et0_fao_evapotranspiration,
        solar_radiation_mjm2,
        EXTRACT(YEAR FROM date) AS year
    FROM {{ ref('stg_weather_daily') }}
    WHERE
        FORMAT_DATE('%m-%d', date) >= '{{ var("growing_season_start") }}'
        AND FORMAT_DATE('%m-%d', date) <= '{{ var("growing_season_end") }}'
)

SELECT
    fips,
    year,
    SUM(GREATEST(0, (temperature_2m_max + temperature_2m_min) / 2.0 - 10)) AS gdd,
    SUM(precipitation_sum) AS precip_total_mm,
    COUNTIF(temperature_2m_max > 30) AS heat_stress_days,
    COUNTIF(precipitation_sum < 1) AS dry_days,
    SUM(et0_fao_evapotranspiration) AS et0_total_mm,
    AVG(solar_radiation_mjm2) AS radiation_mean,
    AVG(temperature_2m_max) AS tmax_mean,
    AVG(temperature_2m_min) AS tmin_mean
FROM season
GROUP BY fips, year

{{ config(
    partition_by={
        'field': 'year',
        'data_type': 'int64',
        'range': {'start': 2020, 'end': 2031, 'interval': 1}
    },
    cluster_by=['state_alpha', 'commodity']
) }}

SELECT
    dc.fips,
    dc.state_alpha,
    dc.county_name,
    cy.commodity,
    cy.year,
    cy.yield_value,
    cy.yield_value_t_ha,
    cy.unit,
    ws.gdd,
    ws.precip_total_mm,
    ws.heat_stress_days,
    ws.dry_days,
    ws.et0_total_mm,
    ws.tmax_mean
FROM {{ ref('fact_crop_yield') }} AS cy
INNER JOIN {{ ref('int_weather_growing_season') }} AS ws
    ON
        cy.fips = ws.fips
        AND cy.year = ws.year
INNER JOIN {{ ref('dim_county') }} AS dc
    ON cy.fips = dc.fips

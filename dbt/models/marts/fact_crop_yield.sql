{{ config(
    partition_by={
        'field': 'year',
        'data_type': 'int64',
        'range': {'start': 2020, 'end': 2031, 'interval': 1}
    },
    cluster_by=['state_alpha', 'commodity']
) }}

SELECT
    fips,
    commodity,
    state_alpha,
    year,
    yield_value,
    yield_value_t_ha,
    unit,
    _ingested_at
FROM {{ ref('stg_nass_yield') }}

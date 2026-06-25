SELECT
    fips,
    state_alpha,
    county_name,
    lat,
    lon
FROM {{ ref('county_centroids') }}

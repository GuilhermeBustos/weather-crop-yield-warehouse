WITH dates AS (
    SELECT date
    FROM UNNEST(
        GENERATE_DATE_ARRAY('2025-01-01', '2025-12-31')
    ) AS date
)

SELECT
    date,
    EXTRACT(YEAR FROM date)      AS year,
    EXTRACT(MONTH FROM date)     AS month,
    EXTRACT(DAY FROM date)       AS day,
    EXTRACT(DAYOFYEAR FROM date) AS day_of_year,
    FORMAT_DATE('%m-%d', date) BETWEEN '{{ var("growing_season_start") }}'
        AND '{{ var("growing_season_end") }}'  AS is_growing_season
FROM dates

SELECT
    calendar_date AS `date`,
    EXTRACT(YEAR FROM calendar_date) AS year,
    EXTRACT(MONTH FROM calendar_date) AS month,
    EXTRACT(DAY FROM calendar_date) AS day,
    EXTRACT(DAYOFYEAR FROM calendar_date) AS day_of_year,
    FORMAT_DATE('%m-%d', calendar_date) BETWEEN '{{ var("growing_season_start") }}' AND '{{ var("growing_season_end") }}' AS is_growing_season  -- noqa: LT05
FROM UNNEST(GENERATE_DATE_ARRAY('2025-01-01', '2025-12-31')) AS calendar_date

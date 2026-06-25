SELECT
    commodity,
    display_name,
    gdd_base_c,
    bushel_weight_lb
FROM UNNEST([
    STRUCT(
        'corn' AS commodity,
        'Corn' AS display_name,
        10 AS gdd_base_c,
        56 AS bushel_weight_lb
    ),
    STRUCT(
        'soybeans' AS commodity,
        'Soybeans' AS display_name,
        10 AS gdd_base_c,
        60 AS bushel_weight_lb
    )
])

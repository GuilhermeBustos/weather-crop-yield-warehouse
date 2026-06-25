{% macro bu_acre_to_t_ha(yield_col, commodity_col) %}
    CASE LOWER({{ commodity_col }})
        WHEN 'corn' THEN {{ yield_col }} * 0.0627677
        WHEN 'soybeans' THEN {{ yield_col }} * 0.0672511
        ELSE NULL
    END
{% endmacro %}

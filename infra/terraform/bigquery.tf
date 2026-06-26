# Warehouse datasets (medallion: raw -> staging -> marts, plus an ephemeral CI dataset).
locals {
  datasets = {
    (var.raw_dataset)     = { description = "Bronze GCS files loaded into BigQuery, lightly typed.", default_table_expiration_days = null }
    (var.staging_dataset) = { description = "dbt staging views: renamed, cast, deduplicated.", default_table_expiration_days = null }
    (var.marts_dataset)   = { description = "dbt marts: modeled facts and dimensions for analysis.", default_table_expiration_days = null }
    (var.dbt_ci_dataset)  = { description = "Ephemeral dbt CI builds; tables auto-expire.", default_table_expiration_days = 7 }
  }
}

resource "google_bigquery_dataset" "this" {
  for_each = local.datasets

  dataset_id    = each.key
  friendly_name = each.key
  description   = each.value.description
  location      = var.bq_location

  delete_contents_on_destroy = var.dataset_force_destroy

  # Warehouse datasets keep tables indefinitely (null); dbt_ci auto-expires.
  default_table_expiration_ms = (
    each.value.default_table_expiration_days == null
    ? null
    : each.value.default_table_expiration_days * 24 * 60 * 60 * 1000
  )
}

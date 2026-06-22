# Warehouse datasets (medallion: raw -> staging -> marts, plus an ephemeral CI dataset).
resource "google_bigquery_dataset" "this" {
  for_each = var.datasets

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

from google.cloud import bigquery

_WEATHER_SCHEMA = [
    bigquery.SchemaField("fips", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("latitude", "FLOAT64"),
    bigquery.SchemaField("longitude", "FLOAT64"),
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("temperature_2m_max", "FLOAT64"),
    bigquery.SchemaField("temperature_2m_min", "FLOAT64"),
    bigquery.SchemaField("temperature_2m_mean", "FLOAT64"),
    bigquery.SchemaField("precipitation_sum", "FLOAT64"),
    bigquery.SchemaField("et0_fao_evapotranspiration", "FLOAT64"),
    bigquery.SchemaField("shortwave_radiation_sum", "FLOAT64"),
    bigquery.SchemaField("windspeed_10m_max", "FLOAT64"),
    bigquery.SchemaField("_ingested_at", "TIMESTAMP", mode="REQUIRED"),
]

_NASS_SCHEMA = [
    bigquery.SchemaField("state_alpha", "STRING"),
    bigquery.SchemaField("state_fips_code", "STRING"),
    bigquery.SchemaField("county_code", "STRING"),
    bigquery.SchemaField("county_name", "STRING"),
    bigquery.SchemaField("commodity_desc", "STRING"),
    bigquery.SchemaField("statisticcat_desc", "STRING"),
    bigquery.SchemaField("short_desc", "STRING"),
    bigquery.SchemaField("unit_desc", "STRING"),
    bigquery.SchemaField("year", "INTEGER"),
    bigquery.SchemaField("value_raw", "STRING"),
    bigquery.SchemaField("_ingested_at", "TIMESTAMP", mode="REQUIRED"),
]


def _load_parquet(
    *, bucket: str, prefix: str, table: str, schema: list, job_config_extra: dict, project: str
) -> None:
    """Load the bronze Parquet under `prefix` into `table`, replacing it (idempotent)."""
    client = bigquery.Client(project=project)
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        **job_config_extra,
    )
    job = client.load_table_from_uri(
        f"gs://{bucket}/{prefix}/*.parquet", table, job_config=job_config
    )
    job.result()


def load_weather(*, bucket: str, prefix: str, dataset: str, project: str) -> None:
    """Load bronze weather Parquet into raw.weather_daily (partition date, cluster fips)."""
    _load_parquet(
        bucket=bucket,
        prefix=prefix,
        table=f"{project}.{dataset}.weather_daily",
        schema=_WEATHER_SCHEMA,
        job_config_extra={
            "time_partitioning": bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY, field="date"
            ),
            "clustering_fields": ["fips"],
        },
        project=project,
    )


def load_nass_yield(*, bucket: str, prefix: str, dataset: str, project: str) -> None:
    """Load bronze NASS Parquet into raw.nass_yield (partition year, cluster state+commodity)."""
    _load_parquet(
        bucket=bucket,
        prefix=prefix,
        table=f"{project}.{dataset}.nass_yield",
        schema=_NASS_SCHEMA,
        job_config_extra={
            "range_partitioning": bigquery.RangePartitioning(
                field="year", range_=bigquery.PartitionRange(start=2000, end=2100, interval=1)
            ),
            "clustering_fields": ["state_alpha", "commodity_desc"],
        },
        project=project,
    )

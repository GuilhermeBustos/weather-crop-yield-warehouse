from datetime import UTC, datetime

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


def load_weather(records: list[dict], *, dataset: str, project: str) -> None:
    """Load weather records into raw.weather_daily (WRITE_TRUNCATE)."""
    ingested_at = datetime.now(UTC).isoformat()
    rows = [{**r, "_ingested_at": ingested_at} for r in records]

    client = bigquery.Client(project=project)
    job_config = bigquery.LoadJobConfig(
        schema=_WEATHER_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field="date"
        ),
        clustering_fields=["fips"],
    )
    job = client.load_table_from_json(
        rows, f"{project}.{dataset}.weather_daily", job_config=job_config
    )
    job.result()


def load_nass_yield(records: list[dict], *, dataset: str, project: str) -> None:
    """Load NASS yield records into raw.nass_yield (WRITE_TRUNCATE)."""
    ingested_at = datetime.now(UTC).isoformat()
    rows = [{**r, "_ingested_at": ingested_at} for r in records]

    client = bigquery.Client(project=project)
    job_config = bigquery.LoadJobConfig(
        schema=_NASS_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        range_partitioning=bigquery.RangePartitioning(
            field="year", range_=bigquery.PartitionRange(start=2000, end=2100, interval=1)
        ),
        clustering_fields=["state_alpha", "commodity_desc"],
    )
    job = client.load_table_from_json(
        rows, f"{project}.{dataset}.nass_yield", job_config=job_config
    )
    job.result()

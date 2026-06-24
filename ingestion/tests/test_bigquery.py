from unittest.mock import patch

from wcy_ingestion.io import bigquery as bq


def test_load_weather_reads_bronze_parquet():
    with patch("wcy_ingestion.io.bigquery.bigquery.Client") as mock_client_cls:
        client = mock_client_cls.return_value
        bq.load_weather(bucket="bkt", prefix="weather_daily", dataset="raw", project="proj")

    client.load_table_from_uri.assert_called_once()
    uri, table = client.load_table_from_uri.call_args.args
    job_config = client.load_table_from_uri.call_args.kwargs["job_config"]

    assert uri == "gs://bkt/weather_daily/*.parquet"
    assert table == "proj.raw.weather_daily"
    assert job_config.source_format == "PARQUET"
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    assert job_config.time_partitioning.field == "date"
    assert job_config.clustering_fields == ["fips"]
    # Load job is awaited
    client.load_table_from_uri.return_value.result.assert_called_once()


def test_load_nass_yield_reads_bronze_parquet():
    with patch("wcy_ingestion.io.bigquery.bigquery.Client") as mock_client_cls:
        client = mock_client_cls.return_value
        bq.load_nass_yield(bucket="bkt", prefix="nass_yield", dataset="raw", project="proj")

    client.load_table_from_uri.assert_called_once()
    uri, table = client.load_table_from_uri.call_args.args
    job_config = client.load_table_from_uri.call_args.kwargs["job_config"]

    assert uri == "gs://bkt/nass_yield/*.parquet"
    assert table == "proj.raw.nass_yield"
    assert job_config.source_format == "PARQUET"
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    assert job_config.range_partitioning.field == "year"
    assert job_config.clustering_fields == ["state_alpha", "commodity_desc"]
    client.load_table_from_uri.return_value.result.assert_called_once()

from unittest.mock import patch

from wcy_ingestion.io import bigquery as bq

_WEATHER = [{"fips": "19001", "date": "2025-04-01", "temperature_2m_max": 10.0}]
_NASS = [{"state_alpha": "IA", "commodity_desc": "CORN", "year": 2025, "value_raw": "201.0"}]


def test_load_weather_config_and_ingested_at():
    with patch("wcy_ingestion.io.bigquery.bigquery.Client") as mock_client_cls:
        client = mock_client_cls.return_value
        bq.load_weather(_WEATHER, dataset="raw", project="proj")

    client.load_table_from_json.assert_called_once()
    rows, table = client.load_table_from_json.call_args.args
    job_config = client.load_table_from_json.call_args.kwargs["job_config"]

    assert table == "proj.raw.weather_daily"
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    assert job_config.time_partitioning.field == "date"
    assert job_config.clustering_fields == ["fips"]
    assert all("_ingested_at" in row for row in rows)
    # Original records are not mutated
    assert "_ingested_at" not in _WEATHER[0]
    # Load job is awaited
    client.load_table_from_json.return_value.result.assert_called_once()


def test_load_nass_yield_config_and_ingested_at():
    with patch("wcy_ingestion.io.bigquery.bigquery.Client") as mock_client_cls:
        client = mock_client_cls.return_value
        bq.load_nass_yield(_NASS, dataset="raw", project="proj")

    client.load_table_from_json.assert_called_once()
    rows, table = client.load_table_from_json.call_args.args
    job_config = client.load_table_from_json.call_args.kwargs["job_config"]

    assert table == "proj.raw.nass_yield"
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    assert job_config.range_partitioning.field == "year"
    assert job_config.clustering_fields == ["state_alpha", "commodity_desc"]
    assert all("_ingested_at" in row for row in rows)
    client.load_table_from_json.return_value.result.assert_called_once()

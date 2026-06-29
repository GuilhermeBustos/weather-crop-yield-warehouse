from unittest.mock import MagicMock, patch

import pytest
from airflow.exceptions import AirflowSkipException
from ingest_yield import _ingest_or_skip, _year_already_loaded

# ---------------------------------------------------------------------------
# _year_already_loaded
# ---------------------------------------------------------------------------


def test_year_already_loaded_returns_true_when_rows_exist():
    mock_client = MagicMock()
    mock_client.query.return_value.result.return_value = [MagicMock()]
    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        assert _year_already_loaded("proj", "raw", 2025) is True


def test_year_already_loaded_returns_false_when_no_rows():
    mock_client = MagicMock()
    mock_client.query.return_value.result.return_value = []
    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        assert _year_already_loaded("proj", "raw", 2025) is False


# ---------------------------------------------------------------------------
# _ingest_or_skip
# ---------------------------------------------------------------------------


def test_ingest_or_skip_raises_when_year_already_loaded():
    mock_settings = MagicMock(project_id="proj", raw_dataset="raw", nass_year=2025)
    # Settings is imported lazily inside _ingest_or_skip; patch at the source module.
    with (
        patch("wcy_ingestion.config.Settings", return_value=mock_settings),
        patch("ingest_yield._year_already_loaded", return_value=True),
        pytest.raises(AirflowSkipException),
    ):
        _ingest_or_skip()


def test_ingest_or_skip_calls_pipeline_when_year_not_loaded():
    mock_settings = MagicMock(project_id="proj", raw_dataset="raw", nass_year=2025)
    mock_run = MagicMock()
    with (
        patch("wcy_ingestion.config.Settings", return_value=mock_settings),
        patch("ingest_yield._year_already_loaded", return_value=False),
        patch("ingest_yield.run_nass_yield", mock_run),
    ):
        _ingest_or_skip()

    mock_run.assert_called_once()

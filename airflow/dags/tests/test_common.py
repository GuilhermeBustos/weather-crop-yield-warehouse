from datetime import timedelta
from unittest.mock import MagicMock, patch

from airflow.sdk import Asset
from common import (
    _CENTROIDS_CSV,
    WEATHER_DATASET,
    YIELD_DATASET,
    _on_failure_alert,
    make_default_args,
    run_nass_yield,
    run_weather,
)


def test_make_default_args_required_keys():
    args = make_default_args()
    assert args["retries"] == 3
    assert isinstance(args["retry_delay"], timedelta)
    assert args["retry_exponential_backoff"] is True
    assert isinstance(args["execution_timeout"], timedelta)
    assert callable(args["on_failure_callback"])


def test_make_default_args_overrides():
    args = make_default_args(retries=1, execution_timeout=timedelta(minutes=30))
    assert args["retries"] == 1
    assert args["execution_timeout"] == timedelta(minutes=30)
    assert args["retry_exponential_backoff"] is True


def test_weather_dataset_uri():
    assert isinstance(WEATHER_DATASET, Asset)
    assert WEATHER_DATASET.uri == "raw.weather_daily"


def test_yield_dataset_uri():
    assert isinstance(YIELD_DATASET, Asset)
    assert YIELD_DATASET.uri == "raw.nass_yield"


def test_on_failure_alert_skips_when_no_email(monkeypatch):
    monkeypatch.delenv("WCY_ALERT_EMAIL", raising=False)
    with patch("airflow.utils.email.send_email") as mock_send:
        _on_failure_alert({"task_instance": MagicMock()})
    mock_send.assert_not_called()


def test_on_failure_alert_sends_email(monkeypatch):
    monkeypatch.setenv("WCY_ALERT_EMAIL", "alerts@example.com")
    ti = MagicMock()
    ti.dag_id = "ingest_weather"
    ti.task_id = "run"
    ti.run_id = "manual__2025-01-01"

    with patch("airflow.utils.email.send_email") as mock_send:
        _on_failure_alert({"task_instance": ti})

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == "alerts@example.com"
    assert "ingest_weather" in kwargs["subject"]
    assert "run" in kwargs["subject"]


def test_run_weather_calls_pipeline():
    mock_settings_cls = MagicMock()
    mock_run = MagicMock()
    with (
        patch("wcy_ingestion.config.Settings", mock_settings_cls),
        patch("wcy_ingestion.pipelines.weather.run", mock_run),
    ):
        run_weather()

    mock_run.assert_called_once_with(mock_settings_cls.return_value, centroids_csv=_CENTROIDS_CSV)


def test_run_nass_yield_calls_pipeline():
    mock_settings_cls = MagicMock()
    mock_run = MagicMock()
    with (
        patch("wcy_ingestion.config.Settings", mock_settings_cls),
        patch("wcy_ingestion.pipelines.nass_yield.run", mock_run),
    ):
        run_nass_yield()

    mock_run.assert_called_once_with(mock_settings_cls.return_value)

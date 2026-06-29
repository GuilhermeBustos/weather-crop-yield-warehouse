from datetime import date
from unittest.mock import MagicMock, patch

from common import run_nass_yield_year, run_weather_window

# ---------------------------------------------------------------------------
# run_weather_window
# ---------------------------------------------------------------------------


def test_run_weather_window_calls_pipeline_with_date_overrides():
    mock_settings_cls = MagicMock()
    mock_run = MagicMock()
    with (
        patch("wcy_ingestion.config.Settings", mock_settings_cls),
        patch("wcy_ingestion.pipelines.weather.run", mock_run),
    ):
        run_weather_window("2024-01-01", "2024-12-31")

    mock_settings_cls.assert_called_once_with(
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
    )
    mock_run.assert_called_once_with(mock_settings_cls.return_value)


def test_run_weather_window_parses_iso_dates():
    mock_settings_cls = MagicMock()
    with (
        patch("wcy_ingestion.config.Settings", mock_settings_cls),
        patch("wcy_ingestion.pipelines.weather.run"),
    ):
        run_weather_window("2025-04-01", "2025-10-31")

    _, kwargs = mock_settings_cls.call_args
    assert kwargs["start_date"] == date(2025, 4, 1)
    assert kwargs["end_date"] == date(2025, 10, 31)


# ---------------------------------------------------------------------------
# run_nass_yield_year
# ---------------------------------------------------------------------------


def test_run_nass_yield_year_calls_pipeline_with_year_override():
    mock_settings_cls = MagicMock()
    mock_run = MagicMock()
    with (
        patch("wcy_ingestion.config.Settings", mock_settings_cls),
        patch("wcy_ingestion.pipelines.nass_yield.run", mock_run),
    ):
        run_nass_yield_year(2024)

    mock_settings_cls.assert_called_once_with(nass_year=2024)
    mock_run.assert_called_once_with(mock_settings_cls.return_value)


def test_run_nass_yield_year_passes_integer():
    mock_settings_cls = MagicMock()
    with (
        patch("wcy_ingestion.config.Settings", mock_settings_cls),
        patch("wcy_ingestion.pipelines.nass_yield.run"),
    ):
        run_nass_yield_year(2025)

    _, kwargs = mock_settings_cls.call_args
    assert kwargs["nass_year"] == 2025
    assert isinstance(kwargs["nass_year"], int)


# ---------------------------------------------------------------------------
# backfill DAG params and structure
# ---------------------------------------------------------------------------


def test_backfill_dag_params_defaults():
    import backfill as _backfill_module

    dag = _backfill_module.backfill()
    params = dag.params

    assert params.get_param("weather_start").value == "2025-04-01"
    assert params.get_param("weather_end").value == "2025-10-31"
    assert params.get_param("nass_year").value == 2025


def test_backfill_dag_schedule_and_catchup():
    import backfill as _backfill_module

    dag = _backfill_module.backfill()
    assert dag.schedule is None
    assert dag.catchup is False


def test_backfill_dag_param_types():
    import backfill as _backfill_module

    dag = _backfill_module.backfill()
    params = dag.params

    assert params.get_param("weather_start").schema.get("type") == "string"
    assert params.get_param("weather_end").schema.get("type") == "string"
    assert params.get_param("nass_year").schema.get("type") == "integer"

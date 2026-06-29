"""Shared helpers for wcy DAGs: default_args factory, Asset objects, pipeline wrappers."""

import os
from datetime import timedelta
from pathlib import Path

from airflow.sdk import Asset

# Airflow Assets that coordinate ingest → transform scheduling.
# URI prefix must match the BigQuery dataset id (WCY_RAW_DATASET in Composer).
_RAW_DATASET = os.environ["WCY_RAW_DATASET"]
WEATHER_DATASET = Asset(f"{_RAW_DATASET}.weather_daily")
YIELD_DATASET = Asset(f"{_RAW_DATASET}.nass_yield")

# Shared dbt project paths — used by transform_dbt and backfill.
# DBT_PROFILES_DIR is set by Terraform (T1); fall back to the repo-relative location
# for local DAG parse/validation.
PROFILES_DIR = Path(
    os.environ.get(
        "DBT_PROFILES_DIR", str(Path(__file__).resolve().parents[2] / "dbt" / "profiles")
    )
)
DBT_PROJECT_DIR = PROFILES_DIR.parent
# weather.run's repo-relative default for this seed resolves wrong once wcy_ingestion is
# synced under dags/ (the src/ level is stripped); anchor it to the dbt project instead.
_CENTROIDS_CSV = DBT_PROJECT_DIR / "seeds" / "county_centroids.csv"


def _on_failure_alert(context: dict) -> None:
    recipient = os.environ.get("WCY_ALERT_EMAIL", "")
    if not recipient:
        return
    from airflow.utils.email import send_email

    ti = context["task_instance"]
    send_email(
        to=recipient,
        subject=f"[wcy] {ti.dag_id}.{ti.task_id} failed",
        html_content=(
            f"<p><b>{ti.dag_id}.{ti.task_id}</b> failed on run <code>{ti.run_id}</code>.</p>"
        ),
    )


def make_default_args(**overrides) -> dict:
    """Return task default_args with retries, exponential backoff, timeout, and alert."""
    args = {
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "execution_timeout": timedelta(hours=2),
        "on_failure_callback": _on_failure_alert,
    }
    args.update(overrides)
    return args


def run_weather() -> None:
    """Call weather.run(Settings()) in-process; suitable for PythonOperator / @task."""
    from wcy_ingestion.config import Settings
    from wcy_ingestion.pipelines import weather

    weather.run(Settings(), centroids_csv=_CENTROIDS_CSV)


def run_nass_yield() -> None:
    """Call nass_yield.run(Settings()) in-process; suitable for PythonOperator / @task."""
    from wcy_ingestion.config import Settings
    from wcy_ingestion.pipelines import nass_yield

    nass_yield.run(Settings())


def run_weather_window(start_date: str, end_date: str) -> None:
    """Run the weather pipeline for an explicit date window; used by the backfill DAG."""
    from datetime import date as _date

    from wcy_ingestion.config import Settings
    from wcy_ingestion.pipelines import weather

    weather.run(
        Settings(
            start_date=_date.fromisoformat(start_date), end_date=_date.fromisoformat(end_date)
        ),
        centroids_csv=_CENTROIDS_CSV,
    )


def run_nass_yield_year(year: int) -> None:
    """Run the NASS yield pipeline for an explicit year; used by the backfill DAG."""
    from wcy_ingestion.config import Settings
    from wcy_ingestion.pipelines import nass_yield

    nass_yield.run(Settings(nass_year=year))

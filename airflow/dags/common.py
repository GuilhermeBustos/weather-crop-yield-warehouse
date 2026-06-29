"""Shared helpers for wcy DAGs: default_args factory, Asset objects, pipeline wrappers."""

import os
from datetime import timedelta

from airflow.sdk import Asset

# Airflow Assets that coordinate ingest → transform scheduling.
# URI prefix must match the BigQuery dataset id (WCY_RAW_DATASET in Composer).
_RAW_DATASET = os.environ["WCY_RAW_DATASET"]
WEATHER_DATASET = Asset(f"{_RAW_DATASET}.weather_daily")
YIELD_DATASET = Asset(f"{_RAW_DATASET}.nass_yield")


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

    weather.run(Settings())


def run_nass_yield() -> None:
    """Call nass_yield.run(Settings()) in-process; suitable for PythonOperator / @task."""
    from wcy_ingestion.config import Settings
    from wcy_ingestion.pipelines import nass_yield

    nass_yield.run(Settings())

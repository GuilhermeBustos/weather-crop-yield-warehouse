"""DAG: ingest_yield — annual ingestion of NASS yield data into raw.nass_yield."""

from airflow.exceptions import AirflowSkipException
from airflow.sdk import dag, task
from common import YIELD_DATASET, make_default_args, run_nass_yield


def _year_already_loaded(project: str, raw_dataset: str, year: int) -> bool:
    """Query raw.nass_yield; return True if rows for the given year already exist.

    A missing table (fresh or cleaned warehouse) means the year isn't loaded yet, so treat
    NotFound as "not loaded" rather than letting it crash the guard.
    """
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    query = f"SELECT 1 FROM `{project}.{raw_dataset}.nass_yield` WHERE year = {year} LIMIT 1"
    try:
        return len(list(client.query(query).result())) > 0
    except NotFound:
        return False


def _ingest_or_skip() -> None:
    """Guard + pipeline call — extracted so it can be unit-tested without the TaskFlow runtime."""
    from wcy_ingestion.config import Settings

    s = Settings()
    if _year_already_loaded(s.project_id, s.raw_dataset, s.nass_year):
        raise AirflowSkipException(f"year {s.nass_year} already in raw.nass_yield — skipping")
    run_nass_yield()


@dag(
    dag_id="ingest_yield",
    schedule="0 0 1 11 *",  # NASS publishes county yield estimates in November
    catchup=False,
    default_args=make_default_args(),
    tags=["wcy", "ingestion"],
)
def ingest_yield():
    @task(outlets=[YIELD_DATASET])
    def run():
        _ingest_or_skip()

    run()


ingest_yield()

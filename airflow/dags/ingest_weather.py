"""DAG: ingest_weather — monthly ingestion of weather data into raw.weather_daily."""

from airflow.sdk import dag, task
from common import WEATHER_DATASET, make_default_args, run_weather


@dag(
    dag_id="ingest_weather",
    schedule="@monthly",
    catchup=False,
    default_args=make_default_args(),
    tags=["wcy", "ingestion"],
)
def ingest_weather():
    @task(outlets=[WEATHER_DATASET])
    def run():
        run_weather()

    run()


ingest_weather()

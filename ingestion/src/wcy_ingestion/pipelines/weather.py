import csv
import logging
from pathlib import Path

from wcy_ingestion.clients import openmeteo
from wcy_ingestion.config import Settings
from wcy_ingestion.io import bigquery, gcs

logger = logging.getLogger(__name__)

_WEATHER_PREFIX = "bronze/weather_daily"
_DEFAULT_CENTROIDS_CSV = Path(__file__).parents[4] / "dbt" / "seeds" / "county_centroids.csv"


def run(settings: Settings, *, centroids_csv: Path | None = None) -> None:
    csv_path = centroids_csv or _DEFAULT_CENTROIDS_CSV
    centroids = _load_centroids(csv_path)
    logger.info(
        "fetching weather for %d counties (%s–%s)",
        len(centroids),
        settings.start_date,
        settings.end_date,
    )

    records = openmeteo.fetch(
        centroids,
        start_date=settings.start_date,
        end_date=settings.end_date,
        variables=settings.daily_variables,
        batch_size=settings.batch_size,
        batch_delay_seconds=settings.openmeteo_batch_delay_seconds,
    )
    logger.info("fetched %d weather records", len(records))

    gcs.write_parquet(
        records,
        bucket=settings.bronze_bucket,
        prefix=_WEATHER_PREFIX,
        partition_by="date",
        project=settings.project_id,
    )
    logger.info("landed to gs://%s/%s", settings.bronze_bucket, _WEATHER_PREFIX)

    bigquery.load_weather(records, dataset=settings.raw_dataset, project=settings.project_id)
    logger.info("loaded into %s.weather_daily", settings.raw_dataset)


def _load_centroids(csv_path: Path) -> list[openmeteo.Centroid]:
    with csv_path.open() as f:
        return [(row["fips"], float(row["lat"]), float(row["lon"])) for row in csv.DictReader(f)]

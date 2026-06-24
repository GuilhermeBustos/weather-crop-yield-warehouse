import logging
from datetime import UTC, datetime

from wcy_ingestion.clients import nass
from wcy_ingestion.config import Settings
from wcy_ingestion.io import bigquery, gcs, secrets

logger = logging.getLogger(__name__)

# Bronze bucket root — the bucket is already the bronze layer, so no nested
# `bronze/` prefix. raw.nass_yield is loaded straight from this Parquet.
_NASS_PREFIX = "nass_yield"


def run(settings: Settings) -> None:
    resource_name = (
        f"projects/{settings.project_id}/secrets/{settings.nass_secret_id}/versions/latest"
    )
    api_key = secrets.get_secret(resource_name)

    logger.info(
        "fetching yields for %s × %s (%d)",
        settings.commodities,
        settings.target_states,
        settings.nass_year,
    )
    records = nass.fetch(
        api_key,
        commodities=settings.commodities,
        states=settings.target_states,
        year=settings.nass_year,
    )
    logger.info("fetched %d yield records", len(records))

    # Stamp once at land time so bronze and raw carry the same _ingested_at.
    ingested_at = datetime.now(UTC)
    records = [{**r, "_ingested_at": ingested_at} for r in records]

    gcs.write_parquet(
        records,
        bucket=settings.bronze_bucket,
        prefix=_NASS_PREFIX,
        partition_by="year",
        project=settings.project_id,
    )
    logger.info("landed to gs://%s/%s", settings.bronze_bucket, _NASS_PREFIX)

    bigquery.load_nass_yield(
        bucket=settings.bronze_bucket,
        prefix=_NASS_PREFIX,
        dataset=settings.raw_dataset,
        project=settings.project_id,
    )
    logger.info("loaded into %s.nass_yield", settings.raw_dataset)

import io
from unittest.mock import MagicMock, patch

import pyarrow.parquet as pq

from wcy_ingestion.io.gcs import _to_parquet_bytes, write_parquet

_RECORDS = [
    {"fips": "19001", "date": "2025-04-01", "temperature_2m_max": 10.0},
    {"fips": "17001", "date": "2025-04-01", "temperature_2m_max": 12.0},
    {"fips": "19001", "date": "2025-04-02", "temperature_2m_max": 11.0},
]


def _patched_bucket(existing_blobs=None):
    """Patch gcs.storage and return the mock bucket for assertions."""
    patcher = patch("wcy_ingestion.io.gcs.storage")
    mock_storage = patcher.start()
    bucket = MagicMock()
    bucket.list_blobs.return_value = existing_blobs or []
    mock_storage.Client.return_value.bucket.return_value = bucket
    return patcher, bucket


def test_writes_one_blob_per_partition_value():
    patcher, bucket = _patched_bucket()
    try:
        write_parquet(
            _RECORDS, bucket="b", prefix="bronze/weather_daily", partition_by="date", project="p"
        )
    finally:
        patcher.stop()

    blob_names = [call.args[0] for call in bucket.blob.call_args_list]
    assert blob_names == [
        "bronze/weather_daily/date=2025-04-01/part-0.parquet",
        "bronze/weather_daily/date=2025-04-02/part-0.parquet",
    ]


def test_clears_prefix_before_writing():
    sentinels = [MagicMock(), MagicMock()]
    patcher, bucket = _patched_bucket(existing_blobs=sentinels)
    try:
        write_parquet(
            _RECORDS, bucket="b", prefix="bronze/weather_daily", partition_by="date", project="p"
        )
    finally:
        patcher.stop()

    bucket.list_blobs.assert_called_once_with(prefix="bronze/weather_daily/")
    bucket.delete_blobs.assert_called_once_with(sentinels)


def test_empty_records_clears_prefix_and_writes_nothing():
    patcher, bucket = _patched_bucket()
    try:
        write_parquet(
            [], bucket="b", prefix="bronze/weather_daily", partition_by="date", project="p"
        )
    finally:
        patcher.stop()

    bucket.list_blobs.assert_called_once_with(prefix="bronze/weather_daily/")
    bucket.blob.assert_not_called()


def test_to_parquet_bytes_roundtrips():
    rows = [{"fips": "19001", "date": "2025-04-01", "temperature_2m_max": 10.5}]
    table = pq.read_table(io.BytesIO(_to_parquet_bytes(rows)))
    assert table.to_pylist() == rows

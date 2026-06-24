import io
from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import storage


def write_parquet(
    records: list[dict], *, bucket: str, prefix: str, partition_by: str, project: str
) -> None:
    """Write records as Hive-partitioned Parquet to GCS, replacing the prefix."""
    client = storage.Client(project=project)
    gcs_bucket = client.bucket(bucket)
    prefix = prefix.rstrip("/")

    _clear_prefix(gcs_bucket, prefix + "/")

    if not records:
        return

    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[str(record[partition_by])].append(record)

    for partition_val, rows in groups.items():
        blob_name = f"{prefix}/{partition_by}={partition_val}/part-0.parquet"
        gcs_bucket.blob(blob_name).upload_from_string(
            _to_parquet_bytes(rows), content_type="application/octet-stream"
        )


def _clear_prefix(bucket: storage.Bucket, prefix: str) -> None:
    blobs = list(bucket.list_blobs(prefix=prefix))
    if blobs:
        bucket.delete_blobs(blobs)


def _to_parquet_bytes(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buf)
    return buf.getvalue()

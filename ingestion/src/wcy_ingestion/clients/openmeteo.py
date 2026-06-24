import time
from datetime import date

import httpx

from .http import build_client, http_get

_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
_TIMEZONE = "America/Chicago"

# (fips, lat, lon)
Centroid = tuple[str, float, float]


def fetch(
    centroids: list[Centroid],
    *,
    start_date: date,
    end_date: date,
    variables: list[str],
    batch_size: int = 50,
    batch_delay_seconds: float = 0.0,
    client: httpx.Client | None = None,
) -> list[dict]:
    _client = client or build_client()
    records: list[dict] = []
    for n, i in enumerate(range(0, len(centroids), batch_size)):
        if n > 0 and batch_delay_seconds > 0:
            time.sleep(batch_delay_seconds)
        batch = centroids[i : i + batch_size]
        records.extend(
            _fetch_batch(
                batch, start_date=start_date, end_date=end_date, variables=variables, client=_client
            )
        )
    return records


def _fetch_batch(
    batch: list[Centroid],
    *,
    start_date: date,
    end_date: date,
    variables: list[str],
    client: httpx.Client,
) -> list[dict]:
    lats = ",".join(str(lat) for _, lat, _ in batch)
    lons = ",".join(str(lon) for _, _, lon in batch)

    response = http_get(
        client,
        _BASE_URL,
        params={
            "latitude": lats,
            "longitude": lons,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": ",".join(variables),
            "timezone": _TIMEZONE,
        },
    )

    data = response.json()
    if isinstance(data, dict):
        data = [data]

    records: list[dict] = []
    for (fips, _, _), point in zip(batch, data, strict=True):
        daily = point["daily"]
        for idx, date_str in enumerate(daily["time"]):
            row: dict = {
                "fips": fips,
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "date": date_str,
            }
            for var in variables:
                row[var] = daily[var][idx]
            records.append(row)

    return records

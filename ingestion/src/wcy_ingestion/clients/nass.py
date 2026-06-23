import httpx

from .http import build_client, http_get

_BASE_URL = "https://quickstats.nass.usda.gov/api"

# Columns kept from the raw NASS record (maps to raw.nass_yield schema).
# "Value" is renamed to value_raw; year is cast to int for BQ range partition.
_KEEP = frozenset(
    {
        "state_alpha",
        "state_fips_code",
        "county_code",
        "county_name",
        "commodity_desc",
        "statisticcat_desc",
        "short_desc",
        "unit_desc",
    }
)


def fetch(
    api_key: str,
    *,
    commodities: list[str],
    states: list[str],
    year: int,
    client: httpx.Client | None = None,
) -> list[dict]:
    _client = client or build_client()
    records: list[dict] = []
    for commodity in commodities:
        for state in states:
            params = {
                "key": api_key,
                "commodity_desc": commodity,
                "statisticcat_desc": "YIELD",
                "year": str(year),
                "state_alpha": state,
            }
            count = _get_count(_client, params)
            if count >= 50_000:
                raise RuntimeError(
                    f"NASS count {count} >= 50k for {commodity}/{state}/{year}; aborting"
                )
            response = http_get(_client, f"{_BASE_URL}/api_GET/", params=params)
            for raw in response.json().get("data", []):
                records.append(_project(raw))
    return records


def _get_count(client: httpx.Client, params: dict) -> int:
    response = http_get(client, f"{_BASE_URL}/get_counts/", params=params)
    return int(response.json()["count"])


def _project(raw: dict) -> dict:
    record: dict = {field: raw.get(field, "") for field in _KEEP}
    record["year"] = int(raw["year"]) if raw.get("year") else None
    record["value_raw"] = raw.get("Value", "")
    return record

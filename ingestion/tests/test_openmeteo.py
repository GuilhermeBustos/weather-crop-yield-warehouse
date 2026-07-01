from datetime import date

import httpx
import respx

from wcy_ingestion.clients import openmeteo

_URL = "https://archive-api.open-meteo.com/v1/archive"

_CENTROIDS = [("19001", 41.0, -94.0), ("17001", 40.0, -91.0), ("18001", 39.0, -85.0)]


def _point(lat, lon, highs):
    return {
        "latitude": lat,
        "longitude": lon,
        "daily": {"time": ["2025-04-01", "2025-04-02"], "temperature_2m_max": highs},
    }


@respx.mock
def test_batches_and_flattens_to_fips_date():
    # batch 1 returns a list (multi-coord); batch 2 returns a bare dict (single coord)
    route = respx.get(_URL).mock(
        side_effect=[
            httpx.Response(
                200, json=[_point(41.0, -94.0, [10.0, 11.0]), _point(40.0, -91.0, [12.0, 13.0])]
            ),
            httpx.Response(200, json=_point(39.0, -85.0, [14.0, 15.0])),
        ]
    )

    records = openmeteo.fetch(
        _CENTROIDS,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 2),
        variables=["temperature_2m_max"],
        batch_size=2,
    )

    # Two coords × two days + one coord × two days == 6 rows, one per (fips, date)
    assert len(records) == 6
    assert route.call_count == 2  # batched: ceil(3 / 2)

    assert route.calls[0].request.url.params["latitude"] == "41.0,40.0"
    assert route.calls[0].request.url.params["longitude"] == "-94.0,-91.0"
    assert route.calls[1].request.url.params["latitude"] == "39.0"

    assert records[0] == {
        "fips": "19001",
        "latitude": 41.0,
        "longitude": -94.0,
        "date": date(2025, 4, 1),  # a real date, not the ISO string
        "temperature_2m_max": 10.0,
    }
    assert {r["fips"] for r in records} == {"19001", "17001", "18001"}
    assert len({(r["fips"], r["date"]) for r in records}) == 6


@respx.mock
def test_paces_between_batches_without_sleeping_after_last(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(openmeteo.time, "sleep", slept.append)
    respx.get(_URL).mock(return_value=httpx.Response(200, json=_point(41.0, -94.0, [10.0, 11.0])))

    openmeteo.fetch(
        _CENTROIDS,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 2),
        variables=["temperature_2m_max"],
        batch_size=1,
        batch_delay_seconds=60.0,
    )

    # 3 centroids ÷ batch_size 1 == 3 batches → paced N−1 == 2 times, none after the last
    assert slept == [60.0, 60.0]


@respx.mock
def test_no_pacing_for_a_single_batch(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(openmeteo.time, "sleep", slept.append)
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                _point(41.0, -94.0, [10.0, 11.0]),
                _point(40.0, -91.0, [12.0, 13.0]),
                _point(39.0, -85.0, [14.0, 15.0]),
            ],
        )
    )

    openmeteo.fetch(
        _CENTROIDS,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 2),
        variables=["temperature_2m_max"],
        batch_size=50,
        batch_delay_seconds=60.0,
    )

    assert slept == []  # one batch → no inter-batch wait

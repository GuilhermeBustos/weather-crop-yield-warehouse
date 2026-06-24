import httpx
import pytest
import respx

from wcy_ingestion.clients import nass

_COUNTS_URL = "https://quickstats.nass.usda.gov/api/get_counts/"
_DATA_URL = "https://quickstats.nass.usda.gov/api/api_GET/"

_RAW = {
    "state_alpha": "IA",
    "state_fips_code": "19",
    "county_code": "001",
    "county_name": "ADAIR",
    "commodity_desc": "CORN",
    "statisticcat_desc": "YIELD",
    "short_desc": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE",
    "unit_desc": "BU / ACRE",
    "year": "2025",
    "Value": "201.0",
    "load_time": "2025-01-01 00:00:00",  # extraneous field, must be dropped
}


@respx.mock
def test_fetch_projects_record_when_under_gate():
    counts = respx.get(_COUNTS_URL).mock(return_value=httpx.Response(200, json={"count": 100}))
    data = respx.get(_DATA_URL).mock(return_value=httpx.Response(200, json={"data": [_RAW]}))

    records = nass.fetch("KEY", commodities=["CORN"], states=["IA"], year=2025)

    assert counts.call_count == 1
    assert data.call_count == 1
    assert records == [
        {
            "state_alpha": "IA",
            "state_fips_code": "19",
            "county_code": "001",
            "county_name": "ADAIR",
            "commodity_desc": "CORN",
            "statisticcat_desc": "YIELD",
            "short_desc": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE",
            "unit_desc": "BU / ACRE",
            "year": 2025,  # cast to int
            "value_raw": "201.0",  # renamed from "Value"
        }
    ]


@respx.mock
def test_count_gate_aborts_before_fetch():
    counts = respx.get(_COUNTS_URL).mock(return_value=httpx.Response(200, json={"count": 50_000}))
    data = respx.get(_DATA_URL).mock(return_value=httpx.Response(200, json={"data": []}))

    with pytest.raises(RuntimeError, match="50000"):
        nass.fetch("KEY", commodities=["CORN"], states=["IA"], year=2025)

    assert counts.call_count == 1
    assert data.call_count == 0  # never reaches the data endpoint


@respx.mock
def test_filters_to_county_and_state_agg_levels():
    counts = respx.get(_COUNTS_URL).mock(return_value=httpx.Response(200, json={"count": 10}))
    data = respx.get(_DATA_URL).mock(return_value=httpx.Response(200, json={"data": [_RAW]}))

    nass.fetch("KEY", commodities=["CORN"], states=["IA"], year=2025)

    # Both the gate and the fetch carry the agg_level_desc filter.
    for route in (counts, data):
        assert route.calls[0].request.url.params["agg_level_desc"] == "COUNTY,STATE"


@respx.mock
def test_paged_by_commodity_and_state():
    counts = respx.get(_COUNTS_URL).mock(return_value=httpx.Response(200, json={"count": 10}))
    data = respx.get(_DATA_URL).mock(return_value=httpx.Response(200, json={"data": [_RAW]}))

    nass.fetch("KEY", commodities=["CORN", "SOYBEANS"], states=["IA", "IL"], year=2025)

    # 2 commodities × 2 states == 4 gate checks and 4 fetches
    assert counts.call_count == 4
    assert data.call_count == 4

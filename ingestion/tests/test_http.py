from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from wcy_ingestion.clients.http import (
    _MAX_ATTEMPTS,
    _RATE_LIMIT_CAP_SECONDS,
    _retry_after_seconds,
    http_get,
)

_URL = "https://example.test/data"


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    # Capture (and neuter) tenacity's backoff: retry tests record the requested
    # delays instead of actually waiting.
    recorded: list[float] = []
    monkeypatch.setattr(http_get.retry, "sleep", recorded.append)
    return recorded


@respx.mock
def test_retries_on_429_then_succeeds(sleeps):
    route = respx.get(_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    with httpx.Client() as client:
        resp = http_get(client, _URL)

    assert resp.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_429_honors_retry_after_header(sleeps):
    route = respx.get(_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "120"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    with httpx.Client() as client:
        http_get(client, _URL)

    assert route.call_count == 2
    assert sleeps == [120.0]  # waits exactly the advertised delay


@respx.mock
def test_429_caps_outlier_retry_after(sleeps):
    route = respx.get(_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3600"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    with httpx.Client() as client:
        http_get(client, _URL)

    assert route.call_count == 2
    assert sleeps == [_RATE_LIMIT_CAP_SECONDS]  # clamped, not the advertised hour


@respx.mock
def test_429_without_retry_after_backs_off_at_least_a_minute(sleeps):
    route = respx.get(_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    with httpx.Client() as client:
        http_get(client, _URL)

    assert route.call_count == 2
    assert len(sleeps) == 1
    assert sleeps[0] >= 60.0  # rides out a full minute window


@respx.mock
def test_persistent_429_exhausts_attempts_riding_out_each_window(sleeps):
    route = respx.get(_URL).mock(return_value=httpx.Response(429))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        http_get(client, _URL)

    assert route.call_count == _MAX_ATTEMPTS
    assert len(sleeps) == _MAX_ATTEMPTS - 1
    assert all(s >= 60.0 for s in sleeps)  # every backoff outlasts a window


@respx.mock
def test_retries_exhausted_on_persistent_5xx(sleeps):
    route = respx.get(_URL).mock(return_value=httpx.Response(503))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        http_get(client, _URL)

    assert route.call_count == _MAX_ATTEMPTS
    assert sleeps[0] < 60.0  # 5xx keeps the fast sub-minute backoff, not the floor


@respx.mock
def test_non_retryable_status_raises_immediately(sleeps):
    route = respx.get(_URL).mock(return_value=httpx.Response(404))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        http_get(client, _URL)

    assert route.call_count == 1
    assert sleeps == []


def test_retry_after_seconds_parses_http_date():
    future = datetime.now(UTC) + timedelta(seconds=90)
    response = httpx.Response(429, headers={"Retry-After": format_datetime(future, usegmt=True)})
    assert 80.0 <= _retry_after_seconds(response) <= 90.0


def test_retry_after_seconds_none_when_header_absent():
    assert _retry_after_seconds(httpx.Response(429)) is None

import httpx
import pytest
import respx

from wcy_ingestion.clients.http import http_get

_URL = "https://example.test/data"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # Neuter tenacity's backoff so retry tests don't actually wait.
    monkeypatch.setattr(http_get.retry, "sleep", lambda _: None)


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.get(_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    with httpx.Client() as client:
        resp = http_get(client, _URL)

    assert resp.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_retries_exhausted_on_persistent_5xx():
    route = respx.get(_URL).mock(return_value=httpx.Response(503))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        http_get(client, _URL)

    assert route.call_count == 5  # stop_after_attempt(5)


@respx.mock
def test_non_retryable_status_raises_immediately():
    route = respx.get(_URL).mock(return_value=httpx.Response(404))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        http_get(client, _URL)

    assert route.call_count == 1

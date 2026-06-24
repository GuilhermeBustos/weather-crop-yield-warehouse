import logging
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# A 429 is Open-Meteo's per-minute, weight-based rate limit: the lockout holds
# until the current 60s window rolls over, so any sub-minute backoff just burns
# attempts without ever clearing it. Honour the server's Retry-After when it
# advertises one; otherwise wait out at least a full window. The attempt budget
# is raised so it can ride out several back-to-back minute lockouts. These stay
# constants — the inter-batch pacing knob is env-wired separately (T17).
_RATE_LIMIT_FLOOR_SECONDS = 60.0
_RATE_LIMIT_JITTER_SECONDS = 10.0
_MAX_ATTEMPTS = 8

# Transient 5xx / network errors recover fast — keep the original sub-minute,
# exponential-with-jitter backoff for them.
_transient_wait = wait_exponential_jitter(initial=1, max=60, jitter=10)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Seconds to wait per the `Retry-After` header, or None if absent/unparseable.

    Handles both forms the spec allows: delta-seconds (e.g. ``"120"``) and an
    HTTP-date. A date already in the past clamps to 0.
    """
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max((retry_at - datetime.now(UTC)).total_seconds(), 0.0)


def _wait_strategy(retry_state) -> float:
    """429 → ride out the rate-limit window; everything else → fast backoff.

    On 429 we honour `Retry-After` if present, else fall back to a ≥60s floor
    (jittered) so the wait always outlasts the minute window. Other retryable
    failures (5xx, network) keep the original exponential-with-jitter backoff.
    """
    outcome = retry_state.outcome
    if outcome is not None and outcome.failed:
        exc = outcome.exception()
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            advertised = _retry_after_seconds(exc.response)
            if advertised is not None:
                return advertised
            return _RATE_LIMIT_FLOOR_SECONDS + random.uniform(0, _RATE_LIMIT_JITTER_SECONDS)
    return _transient_wait(retry_state)


def build_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout)


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=_wait_strategy,
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def http_get(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response = client.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response

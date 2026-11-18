"""Shared bounded retry helpers for Yahoo Finance (yfinance) calls.

Rules (see project instructions): retry transient network/API issues and
entirely empty DataFrames; do NOT retry programming/config errors. Keep delays
bounded (exponential backoff + jitter, start ~1s).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Retry only these exception types (transient/network/API style). Anything else
# (e.g. TypeError, ValueError from bad args, AttributeError) is not retried.
_TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

try:
    import requests as _requests

    _TRANSIENT_EXCEPTIONS = _TRANSIENT_EXCEPTIONS + (
        _requests.exceptions.RequestException,
    )
except Exception:  # pragma: no cover
    _requests = None  # type: ignore[assignment]

try:
    from urllib3.exceptions import HTTPError as _Urllib3HTTPError
    from urllib3.exceptions import MaxRetryError as _Urllib3MaxRetryError

    _TRANSIENT_EXCEPTIONS = _TRANSIENT_EXCEPTIONS + (
        _Urllib3HTTPError,
        _Urllib3MaxRetryError,
    )
except Exception:  # pragma: no cover
    pass


def is_transient_exception(exc: BaseException) -> bool:
    return isinstance(exc, _TRANSIENT_EXCEPTIONS)


def _sleep_backoff(attempt: int) -> None:
    # attempt is 1-based for the *failed* attempt number before sleeping; delay
    # grows quickly but stays bounded.
    base = min(8.0, 1.0 * (2 ** max(0, attempt - 1)))
    delay = base + random.uniform(0.0, 0.5)
    time.sleep(delay)


def retry_call(
    *,
    fn: Callable[[], T],
    ticker: str,
    period: str | None = None,
    interval: str | None = None,
    max_attempts: int = 3,
    is_empty: Callable[[T], bool] | None = None,
    empty_is_retryable: bool = True,
) -> T:
    """Call ``fn`` up to ``max_attempts`` times.

    - Retries on transient exceptions (see ``is_transient_exception``).
    - If ``is_empty`` is provided and returns True, treats result as transient
      failure when ``empty_is_retryable`` is True.
    - Does not retry non-transient exceptions.
    """
    if max_attempts < 1:
        max_attempts = 1
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn()
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            if not is_transient_exception(exc):
                raise
            if attempt >= max_attempts:
                logger.error(
                    "yfinance call failed after %s attempts (ticker=%s period=%s interval=%s): %s",
                    attempt,
                    ticker,
                    period,
                    interval,
                    exc,
                )
                raise
            logger.warning(
                "yfinance transient error attempt %s/%s (ticker=%s period=%s interval=%s): %s",
                attempt,
                max_attempts,
                ticker,
                period,
                interval,
                exc,
            )
            _sleep_backoff(attempt)
            continue

        if is_empty is not None and empty_is_retryable and is_empty(result):
            if attempt >= max_attempts:
                logger.error(
                    "yfinance returned empty data after %s attempts (ticker=%s period=%s interval=%s)",
                    attempt,
                    ticker,
                    period,
                    interval,
                )
                raise ValueError(f"yfinance returned no data for {ticker}")
            logger.warning(
                "yfinance empty result attempt %s/%s (ticker=%s period=%s interval=%s); retrying",
                attempt,
                max_attempts,
                ticker,
                period,
                interval,
            )
            _sleep_backoff(attempt)
            continue

        return result

    # Should not be reached, but keep a clear failure.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry_call exhausted without result")

"""Tests for Yahoo retry helper behavior (mocked)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services import yahoo_retry


def test_retry_call_succeeds_first_try():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    out = yahoo_retry.retry_call(fn=fn, ticker="T", period="1d", interval="1d", max_attempts=3)
    assert out == "ok"
    assert calls["n"] == 1


def test_retry_call_retries_transient_then_succeeds():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("net down")
        return "ok"

    out = yahoo_retry.retry_call(fn=fn, ticker="T", period="1d", interval="1d", max_attempts=3)
    assert out == "ok"
    assert calls["n"] == 2


def test_retry_call_retries_two_failures_then_succeeds():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise TimeoutError("slow")
        return "ok"

    out = yahoo_retry.retry_call(fn=fn, ticker="T", period="1d", interval="1d", max_attempts=3)
    assert out == "ok"
    assert calls["n"] == 3


def test_retry_call_raises_after_exhausting_attempts():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ConnectionError("still down")

    with pytest.raises(ConnectionError):
        yahoo_retry.retry_call(fn=fn, ticker="T", period="1d", interval="1d", max_attempts=3)
    assert calls["n"] == 3


def test_retry_call_empty_dataframe_retried_then_fails():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return pd.DataFrame()

    with pytest.raises(ValueError, match="no data"):
        yahoo_retry.retry_call(
            fn=fn,
            ticker="T",
            period="1d",
            interval="1d",
            max_attempts=3,
            is_empty=lambda f: f is None or getattr(f, "empty", True),
        )
    assert calls["n"] == 3


def test_retry_call_non_transient_not_retried():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise TypeError("bad arg")

    with pytest.raises(TypeError):
        yahoo_retry.retry_call(fn=fn, ticker="T", period="1d", interval="1d", max_attempts=3)
    assert calls["n"] == 1

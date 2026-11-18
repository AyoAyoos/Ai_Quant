"""Focused tests for market_data download retry behavior (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services import market_data


def _ok_df():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [1000, 1100],
        },
        index=idx,
    )


def test_download_market_data_uses_nifty50_ticker_and_period(tmp_path, monkeypatch):
    assert market_data.MARKET_TICKERS["NIFTY50"] == "^NSEI"
    monkeypatch.setattr(market_data, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(market_data, "_DATA_PERIOD", "2y")

    import yfinance as yf

    with patch.object(yf, "download") as mock_dl:
        mock_dl.return_value = _ok_df()
        p = market_data.download_market_data("NIFTY50")
        assert p.exists()
        call = mock_dl.call_args
        assert call.kwargs["tickers"] == "^NSEI"
        assert call.kwargs["period"] == "2y"
        assert call.kwargs["interval"] == "1d"


def test_download_market_data_retries_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "_DATA_DIR", tmp_path)
    import yfinance as yf

    with patch.object(yf, "download") as mock_dl:
        mock_dl.side_effect = [ConnectionError("boom"), _ok_df()]
        p = market_data.download_market_data("NIFTY50")
        assert p.exists()
        assert mock_dl.call_count == 2


def test_download_market_data_all_empty_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "_DATA_DIR", tmp_path)
    import yfinance as yf

    with patch.object(yf, "download") as mock_dl:
        mock_dl.return_value = pd.DataFrame()
        with pytest.raises(market_data.MarketDataError, match="no data"):
            market_data.download_market_data("NIFTY50")
        assert mock_dl.call_count == 3

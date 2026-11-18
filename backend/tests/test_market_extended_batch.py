"""Focused tests for market_data_extended batch behavior (mocked)."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from app.services import market_data_extended


def test_download_batch_not_retried_by_wrapper_intent():
    # _download_batch is a thin wrapper; ensure it still calls yf.download once.
    import yfinance as yf

    with patch.object(yf, "download") as mock_dl:
        mock_dl.return_value = pd.DataFrame()
        out = market_data_extended._download_batch(["^NSEI"], period="1mo", interval="1d")
        assert mock_dl.call_count == 1
        assert out.empty

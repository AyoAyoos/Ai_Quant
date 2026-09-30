"""
Market data loading for backtests.

MVP scope is a single market (NIFTY 50). We pull daily OHLCV history from
Yahoo Finance via ``yfinance``, normalise it to the same
``Date,Open,High,Low,Close,Volume`` shape the strategy runner's CSV loader
expects, and cache it under ``backend/data/{market}.csv``.

The cache is refreshed only when stale (``market_data_refresh_days``), so a
backtest on a dev box that has seen data before still works offline.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from app.config import settings

# Yahoo Finance ticker per supported market (MVP: NIFTY 50 only).
MARKET_TICKERS = {
    "NIFTY50": "^NSEI",
}

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DATA_PERIOD = "2y"
_DATA_REFRESH_DAYS = settings.market_data_refresh_days

_OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class MarketDataError(RuntimeError):
    pass


def market_data_path(market: str) -> Path:
    return _DATA_DIR / f"{market.strip().upper()}.csv"


def is_fresh(path: Path, max_age_days: int = _DATA_REFRESH_DAYS) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(days=max_age_days)


def download_market_data(market: str) -> Path:
    """Download OHLCV for `market` from Yahoo Finance and cache it as CSV."""
    import yfinance as yf

    market_key = market.strip().upper()
    ticker = MARKET_TICKERS.get(market_key)
    if ticker is None:
        raise MarketDataError(f"no Yahoo Finance symbol configured for market={market!r}")

    frame = yf.download(
        tickers=ticker,
        period=_DATA_PERIOD,
        interval="1d",
        auto_adjust=False,
        group_by="column",
        progress=False,
    )
    if frame is None or frame.empty:
        raise MarketDataError(f"yfinance returned no data for {ticker}")

    # Single-ticker downloads can come back with a MultiIndex on the columns;
    # flatten to the plain OHLCV names the runner expects.
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)

    missing = set(_OHLCV_COLUMNS) - set(frame.columns)
    if missing:
        raise MarketDataError(f"downloaded data missing columns: {sorted(missing)}")

    frame = frame[_OHLCV_COLUMNS].copy()
    frame = frame.loc[~frame.index.duplicated(keep="first")]
    frame = frame.dropna()

    path = market_data_path(market_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.index.name = "Date"
    frame.sort_index().to_csv(path, date_format="%Y-%m-%d")
    return path


def ensure_market_data(market: str, max_age_days: int = _DATA_REFRESH_DAYS) -> Path:
    """Return a fresh cached CSV path for `market`, downloading if needed.

    A stale-but-present cache is reused if the refresh fails so a backtest
    never dies just because Yahoo is down or rate-limited.
    """
    path = market_data_path(market)
    if is_fresh(path, max_age_days=max_age_days):
        return path

    if path.exists():
        try:
            return download_market_data(market)
        except MarketDataError:
            return path

    return download_market_data(market)
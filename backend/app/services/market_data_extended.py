"""
Extended market data service for the Indian market dashboard.

Provides:
- Multiple Indian index quotes (NIFTY 50, BANK NIFTY, SENSEX, FINNIFTY, INDIA VIX, NIFTY IT)
- Historical chart data with multiple timeframes
- Top gainers / losers / most active (from a fixed, documented NSE universe)
- Sector performance (real NSE sector indices)
- Market breadth
- Market news aggregation

All data is sourced from Yahoo Finance via yfinance.  Nothing in this module
invents prices: when the provider has no usable row the caller receives an
explicit ``unavailable`` / empty result instead of a fabricated number.

A small in-process TTL cache keeps the dashboard from hammering Yahoo when
several sections request the same basket (pulse + breadth) at once.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")

# Yahoo Finance tickers for Indian indices
INDEX_TICKERS = {
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
    "INDIAVIX": "^INDIAVIX",
    "NIFTYIT": "^CNXIT",
}

INDEX_NAMES = {
    "NIFTY50": "NIFTY 50",
    "BANKNIFTY": "BANK NIFTY",
    "SENSEX": "SENSEX",
    "FINNIFTY": "FIN NIFTY",
    "INDIAVIX": "INDIA VIX",
    "NIFTYIT": "NIFTY IT",
}

# Real NSE sector indices (not representative stocks).
SECTOR_TICKERS = {
    "Banking": "^NSEBANK",
    "Information Technology": "^CNXIT",
    "Automobile": "^CNXAUTO",
    "Pharmaceuticals": "^CNXPHARMA",
    "FMCG": "^CNXFMCG",
    "Energy": "^CNXENERGY",
    "Metals": "^CNXMETAL",
    "Realty": "^CNXREALTY",
}

# Documented NSE stock universe used for gainers / losers / most active and
# breadth.  Keep names here so the UI never has to guess a company name.
INSTRUMENT_UNIVERSE = [
    {"symbol": "RELIANCE", "ticker": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy"},
    {"symbol": "TCS", "ticker": "TCS.NS", "name": "Tata Consultancy Services", "sector": "Information Technology"},
    {"symbol": "HDFCBANK", "ticker": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Banking"},
    {"symbol": "ICICIBANK", "ticker": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Banking"},
    {"symbol": "INFY", "ticker": "INFY.NS", "name": "Infosys", "sector": "Information Technology"},
    {"symbol": "HINDUNILVR", "ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"symbol": "ITC", "ticker": "ITC.NS", "name": "ITC", "sector": "FMCG"},
    {"symbol": "SBIN", "ticker": "SBIN.NS", "name": "State Bank of India", "sector": "Banking"},
    {"symbol": "BHARTIARTL", "ticker": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom"},
    {"symbol": "KOTAKBANK", "ticker": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "sector": "Banking"},
    {"symbol": "LT", "ticker": "LT.NS", "name": "Larsen & Toubro", "sector": "Capital Goods"},
    {"symbol": "AXISBANK", "ticker": "AXISBANK.NS", "name": "Axis Bank", "sector": "Banking"},
    {"symbol": "BAJFINANCE", "ticker": "BAJFINANCE.NS", "name": "Bajaj Finance", "sector": "Financial Services"},
    {"symbol": "ASIANPAINT", "ticker": "ASIANPAINT.NS", "name": "Asian Paints", "sector": "Consumer Goods"},
    {"symbol": "MARUTI", "ticker": "MARUTI.NS", "name": "Maruti Suzuki", "sector": "Automobile"},
    {"symbol": "SUNPHARMA", "ticker": "SUNPHARMA.NS", "name": "Sun Pharmaceutical", "sector": "Pharmaceuticals"},
    {"symbol": "TITAN", "ticker": "TITAN.NS", "name": "Titan Company", "sector": "Consumer Goods"},
    {"symbol": "ULTRACEMCO", "ticker": "ULTRACEMCO.NS", "name": "UltraTech Cement", "sector": "Cement"},
    {"symbol": "WIPRO", "ticker": "WIPRO.NS", "name": "Wipro", "sector": "Information Technology"},
    {"symbol": "NESTLEIND", "ticker": "NESTLEIND.NS", "name": "Nestle India", "sector": "FMCG"},
    {"symbol": "POWERGRID", "ticker": "POWERGRID.NS", "name": "Power Grid", "sector": "Utilities"},
    {"symbol": "NTPC", "ticker": "NTPC.NS", "name": "NTPC", "sector": "Energy"},
    {"symbol": "TECHM", "ticker": "TECHM.NS", "name": "Tech Mahindra", "sector": "Information Technology"},
    {"symbol": "TATASTEEL", "ticker": "TATASTEEL.NS", "name": "Tata Steel", "sector": "Metals"},
    {"symbol": "BAJAJFINSV", "ticker": "BAJAJFINSV.NS", "name": "Bajaj Finserv", "sector": "Financial Services"},
    {"symbol": "ADANIENT", "ticker": "ADANIENT.NS", "name": "Adani Enterprises", "sector": "Capital Goods"},
    {"symbol": "ADANIPORTS", "ticker": "ADANIPORTS.NS", "name": "Adani Ports", "sector": "Infrastructure"},
    {"symbol": "JSWSTEEL", "ticker": "JSWSTEEL.NS", "name": "JSW Steel", "sector": "Metals"},
    {"symbol": "HCLTECH", "ticker": "HCLTECH.NS", "name": "HCL Technologies", "sector": "Information Technology"},
    {"symbol": "GRASIM", "ticker": "GRASIM.NS", "name": "Grasim Industries", "sector": "Cement"},
    {"symbol": "DRREDDY", "ticker": "DRREDDY.NS", "name": "Dr Reddy's Laboratories", "sector": "Pharmaceuticals"},
    {"symbol": "CIPLA", "ticker": "CIPLA.NS", "name": "Cipla", "sector": "Pharmaceuticals"},
    {"symbol": "COALINDIA", "ticker": "COALINDIA.NS", "name": "Coal India", "sector": "Energy"},
    {"symbol": "BPCL", "ticker": "BPCL.NS", "name": "Bharat Petroleum", "sector": "Energy"},
    {"symbol": "ONGC", "ticker": "ONGC.NS", "name": "Oil & Natural Gas Corp", "sector": "Energy"},
    {"symbol": "M&M", "ticker": "M&M.NS", "name": "Mahindra & Mahindra", "sector": "Automobile"},
    {"symbol": "EICHERMOT", "ticker": "EICHERMOT.NS", "name": "Eicher Motors", "sector": "Automobile"},
    {"symbol": "HEROMOTOCO", "ticker": "HEROMOTOCO.NS", "name": "Hero MotoCorp", "sector": "Automobile"},
    {"symbol": "BRITANNIA", "ticker": "BRITANNIA.NS", "name": "Britannia Industries", "sector": "FMCG"},
    {"symbol": "DIVISLAB", "ticker": "DIVISLAB.NS", "name": "Divi's Laboratories", "sector": "Pharmaceuticals"},
    {"symbol": "APOLLOHOSP", "ticker": "APOLLOHOSP.NS", "name": "Apollo Hospitals", "sector": "Healthcare"},
    {"symbol": "SBILIFE", "ticker": "SBILIFE.NS", "name": "SBI Life Insurance", "sector": "Financial Services"},
    {"symbol": "HDFCLIFE", "ticker": "HDFCLIFE.NS", "name": "HDFC Life Insurance", "sector": "Financial Services"},
    {"symbol": "INDUSINDBK", "ticker": "INDUSINDBK.NS", "name": "IndusInd Bank", "sector": "Banking"},
]

_UNIVERSE_BY_TICKER = {item["ticker"]: item for item in INSTRUMENT_UNIVERSE}

# Timeframe mapping for yfinance
TIMEFRAME_MAP = {
    "1m": {"period": "1d", "interval": "1m"},
    "5m": {"period": "5d", "interval": "5m"},
    "15m": {"period": "5d", "interval": "15m"},
    "30m": {"period": "1mo", "interval": "30m"},
    "1h": {"period": "1mo", "interval": "60m"},
    "1d": {"period": "2y", "interval": "1d"},
    "1w": {"period": "5y", "interval": "1wk"},
}

# Maximum bars per timeframe to avoid huge responses
MAX_BARS = {
    "1m": 375,  # 6.25 hours * 60
    "5m": 375,
    "15m": 375,
    "30m": 375,
    "1h": 375,
    "1d": 500,
    "1w": 260,
}

# NSE cash session, IST.
_OPEN_MINUTES = 9 * 60 + 15
_PRE_OPEN_MINUTES = 9 * 60
_CLOSE_MINUTES = 15 * 60 + 30

# Official NSE equity trading holidays for calendar 2026 (exchange circular
# CMTR71775).  Weekends are handled separately.  Keeping this explicit is
# better than pretending every weekday is a trading day: on a holiday the
# dashboard must say CLOSED, not "next open today at 09:15".
_NSE_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 15): "Municipal Corporation Elections in Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Eid",
    date(2026, 6, 26): "Moharram",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}

_NSE_HOLIDAYS = _NSE_HOLIDAYS_2026


def _is_nse_holiday(day: date) -> bool:
    return day in _NSE_HOLIDAYS


class MarketDataError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = asyncio.Lock()


def _cache_get(key: str, ttl_seconds: float) -> Any:
    item = _CACHE.get(key)
    if item is None:
        return None
    stored_at, value = item
    if time.monotonic() - stored_at > ttl_seconds:
        return None
    return value


def _cache_put(key: str, value: Any) -> None:
    _CACHE[key] = (time.monotonic(), value)


def clear_market_cache() -> None:
    """Drop every cached provider response (used by tests / manual refresh)."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------


def _normalize_frame(frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Return a clean OHLC frame or ``None``.

    Yahoo sometimes appends a trailing all-NaN row for the current session.
    Taking ``iloc[-1]`` without dropping it was the root cause of the
    dashboard's ``+0.00%`` sector cards and empty movers lists.
    """
    if frame is None or frame.empty:
        return None
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.copy()
        frame.columns = frame.columns.get_level_values(0)
    required = ["Open", "High", "Low", "Close"]
    if not all(col in frame.columns for col in required):
        return None
    cleaned = frame.dropna(subset=required).copy()
    cleaned = cleaned[~cleaned.index.duplicated(keep="last")].sort_index()
    return cleaned if len(cleaned) else None


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _row_snapshot(frame: Optional[pd.DataFrame]) -> Optional[dict]:
    """Latest close vs previous close from a cleaned frame."""
    if frame is None or frame.empty:
        return None
    last = frame.iloc[-1]
    prev = frame.iloc[-2] if len(frame) > 1 else last
    close = _finite(last.get("Close"))
    prev_close = _finite(prev.get("Close"))
    if close is None or prev_close in (None, 0):
        return None
    change = close - prev_close
    change_pct = (change / prev_close) * 100.0
    return {
        "price": round(close, 2),
        "prev_close": round(prev_close, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 4),
        "high": _finite(last.get("High")),
        "low": _finite(last.get("Low")),
        "volume": int(_finite(last.get("Volume")) or 0),
        "timestamp": int(frame.index[-1].timestamp()),
    }


def _normalize_symbol(symbol: str) -> str:
    """Normalize symbol for yfinance."""
    return symbol.strip().upper()


def _get_ticker(symbol: str) -> str:
    """Get Yahoo Finance ticker for a symbol."""
    normalized = _normalize_symbol(symbol)
    if normalized in INDEX_TICKERS:
        return INDEX_TICKERS[normalized]
    if normalized in SECTOR_TICKERS:
        return SECTOR_TICKERS[normalized]
    if normalized in _UNIVERSE_BY_TICKER:
        return normalized
    return f"{normalized}.NS"


def interval_is_intraday(interval: str) -> bool:
    """Check if interval is intraday (minutes/hours)."""
    return interval.endswith("m") or interval.endswith("h")


def _fetch_ticker_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch data from yfinance in a worker thread."""
    frame = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if frame is None or frame.empty:
        raise ValueError(f"yfinance returned no data for {ticker}")
    return frame


def _download_batch(tickers: Iterable[str], period: str, interval: str) -> pd.DataFrame:
    """One batched Yahoo request for many tickers (much kinder than 45 calls)."""
    return yf.download(
        list(tickers),
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )


def _sub_frame(batch: Optional[pd.DataFrame], ticker: str) -> Optional[pd.DataFrame]:
    if batch is None or batch.empty:
        return None
    try:
        if isinstance(batch.columns, pd.MultiIndex):
            if ticker not in batch.columns.get_level_values(0):
                return None
            return batch[ticker]
        return batch
    except Exception:
        return None


def _process_ohlcv_frame(frame: pd.DataFrame, interval: str) -> list[dict]:
    """Process OHLCV DataFrame to list of dicts with standardized fields."""
    cleaned = _normalize_frame(frame)
    if cleaned is None:
        raise ValueError("No usable OHLC rows")

    bars: list[dict] = []
    for ts, row in cleaned.iterrows():
        unix = int(ts.timestamp())
        open_ = _finite(row.get("Open"))
        high = _finite(row.get("High"))
        low = _finite(row.get("Low"))
        close = _finite(row.get("Close"))
        if None in (open_, high, low, close):
            continue
        bar = {
            "time": unix - (unix % 60) if interval_is_intraday(interval) else unix,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        }
        volume = _finite(row.get("Volume"))
        bar["volume"] = int(volume or 0)
        bars.append(bar)

    if not bars:
        raise ValueError("No usable OHLC rows")
    return bars


# ---------------------------------------------------------------------------
# Market session
# ---------------------------------------------------------------------------


def _next_open_datetime(now: datetime) -> datetime:
    minutes = now.hour * 60 + now.minute
    candidate = now
    if now.weekday() > 4 or minutes >= _OPEN_MINUTES or _is_nse_holiday(now.date()):
        candidate = now + timedelta(days=1)
    while candidate.weekday() > 4 or _is_nse_holiday(candidate.date()):
        candidate = candidate + timedelta(days=1)
    return candidate.replace(hour=9, minute=15, second=0, microsecond=0)


def get_market_status(now: Optional[datetime] = None) -> dict:
    """Current NSE cash-session status in IST.

    PRE-OPEN is the 09:00–09:15 window only.  Earlier mornings are CLOSED,
    which is the behaviour a trader expects (the old implementation labelled
    every pre-09:15 moment, including midnight, as PRE-OPEN).  Exchange
    holidays are CLOSED for the whole day and the next open skips them.
    """
    current = now or datetime.now(_IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_IST)
    current = current.astimezone(_IST)

    weekday = current.weekday()  # 0=Mon, 4=Fri
    minutes = current.hour * 60 + current.minute
    holiday_name = _NSE_HOLIDAYS.get(current.date())

    if holiday_name:
        status = "CLOSED"
        reason = f"NSE holiday — {holiday_name}"
    elif weekday > 4:
        status, reason = "CLOSED", "Weekend — NSE cash market closed"
    elif minutes < _PRE_OPEN_MINUTES:
        status, reason = "CLOSED", "Before the NSE pre-open window"
    elif minutes < _OPEN_MINUTES:
        status, reason = "PRE-OPEN", "NSE pre-open session (09:00–09:15 IST)"
    elif minutes < _CLOSE_MINUTES:
        status, reason = "OPEN", "NSE cash session (09:15–15:30 IST)"
    else:
        status, reason = "CLOSED", "After the NSE cash session"

    next_open = _next_open_datetime(current)
    return {
        "status": status,
        "reason": reason,
        "is_open": status == "OPEN",
        "is_holiday": bool(holiday_name),
        "holiday": holiday_name,
        "session": "NSE cash market",
        "timezone": "Asia/Kolkata",
        "as_of": current.isoformat(),
        "as_of_unix": int(current.timestamp()),
        "next_open": next_open.isoformat(),
        "next_open_label": next_open.strftime("%a %d %b, 09:15 IST"),
    }


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------


async def fetch_index_quote(symbol: str) -> dict:
    """Fetch the latest quote for a single Indian index.

    Prefers the freshest intraday bar, falls back to the latest daily close.
    Never returns a NaN price.
    """
    key = f"quote:{symbol.upper()}"
    cached = _cache_get(key, 10)
    if cached is not None:
        return dict(cached)

    ticker = _get_ticker(symbol)
    daily_frame_raw = None
    try:
        daily_frame_raw = await asyncio.to_thread(_fetch_ticker_data, ticker, "5d", "1d")
    except Exception as exc:
        logger.debug("Daily quote fallback failed for %s: %s", symbol, exc)
    daily_frame = _normalize_frame(daily_frame_raw)

    intraday_raw = None
    try:
        intraday_raw = await asyncio.to_thread(_fetch_ticker_data, ticker, "1d", "1m")
    except Exception as exc:
        logger.debug("Intraday quote failed for %s: %s", symbol, exc)
    intraday_frame = _normalize_frame(intraday_raw)

    source_frame = intraday_frame if intraday_frame is not None else daily_frame
    snapshot = _row_snapshot(source_frame)
    if snapshot is None:
        raise MarketDataError(f"Provider returned no usable quote for {symbol}")

    # Previous close always comes from daily closes, not the intraday series.
    prev_close = None
    if daily_frame is not None and len(daily_frame) >= 2:
        prev_close = _finite(daily_frame.iloc[-2].get("Close"))
    if prev_close is None:
        prev_close = _finite(daily_frame.iloc[-1].get("Close")) if daily_frame is not None else None
    if prev_close in (None, 0):
        prev_close = snapshot["price"]

    change = snapshot["price"] - prev_close
    change_pct = (change / prev_close) * 100.0 if prev_close else 0.0

    quote = {
        "symbol": symbol.upper(),
        "name": INDEX_NAMES.get(symbol.upper(), symbol.upper()),
        "price": round(snapshot["price"], 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 4),
        "high": snapshot.get("high"),
        "low": snapshot.get("low"),
        "prev_close": round(prev_close, 2),
        "timestamp": snapshot["timestamp"],
        "source": "yfinance",
        "status": "ok",
    }
    _cache_put(key, quote)
    return dict(quote)


async def fetch_multiple_index_quotes(symbols: list[str]) -> list[dict]:
    """Fetch quotes for multiple indices concurrently."""
    tasks = [fetch_index_quote(s) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[dict] = []
    for symbol, result in zip(symbols, results):
        if isinstance(result, Exception):
            output.append(
                {
                    "symbol": symbol.upper(),
                    "name": INDEX_NAMES.get(symbol.upper(), symbol.upper()),
                    "error": str(result),
                    "status": "unavailable",
                }
            )
        else:
            output.append(result)
    return output


# ---------------------------------------------------------------------------
# Chart history
# ---------------------------------------------------------------------------


async def fetch_chart_history(symbol: str, timeframe: str = "1d", limit: int = 500) -> list[dict]:
    """Fetch historical chart data for a symbol with specified timeframe."""
    timeframe = timeframe.lower()
    if timeframe not in TIMEFRAME_MAP:
        raise MarketDataError(
            f"Unsupported timeframe: {timeframe}. Supported: {list(TIMEFRAME_MAP.keys())}"
        )

    ticker = _get_ticker(symbol)
    config = TIMEFRAME_MAP[timeframe]
    max_bars = min(limit, MAX_BARS.get(timeframe, 500))

    try:
        frame = await asyncio.to_thread(
            _fetch_ticker_data, ticker, config["period"], config["interval"]
        )
        bars = _process_ohlcv_frame(frame, config["interval"])
        return bars[-max_bars:] if len(bars) > max_bars else bars
    except Exception as exc:
        logger.warning("Failed to fetch chart history for %s (%s): %s", symbol, timeframe, exc)
        raise MarketDataError(f"Failed to fetch chart history: {exc}") from exc


# ---------------------------------------------------------------------------
# NSE basket (gainers / losers / most active / breadth)
# ---------------------------------------------------------------------------

_BASKET_LOCK = asyncio.Lock()


def _records_from_batch(batch: Optional[pd.DataFrame], tickers: Iterable[str]) -> list[dict]:
    records: list[dict] = []
    for ticker in tickers:
        sub = _sub_frame(batch, ticker)
        snapshot = _row_snapshot(_normalize_frame(sub))
        if snapshot is None:
            continue
        meta = _UNIVERSE_BY_TICKER.get(ticker, {"symbol": ticker.replace(".NS", ""), "name": ticker})
        records.append(
            {
                "symbol": meta.get("symbol", ticker.replace(".NS", "")),
                "name": meta.get("name", meta.get("symbol", ticker)),
                "sector": meta.get("sector"),
                "ticker": ticker,
                **snapshot,
            }
        )
    return records


async def _fetch_individual_records(tickers: list[str]) -> list[dict]:
    """Fallback when a batched download fails: bounded concurrent requests."""
    semaphore = asyncio.Semaphore(8)

    async def one(ticker: str):
        async with semaphore:
            try:
                frame = await asyncio.to_thread(_fetch_ticker_data, ticker, "1mo", "1d")
                snapshot = _row_snapshot(_normalize_frame(frame))
                if snapshot is None:
                    return None
                meta = _UNIVERSE_BY_TICKER.get(
                    ticker, {"symbol": ticker.replace(".NS", ""), "name": ticker}
                )
                return {
                    "symbol": meta.get("symbol", ticker.replace(".NS", "")),
                    "name": meta.get("name", meta.get("symbol", ticker)),
                    "sector": meta.get("sector"),
                    "ticker": ticker,
                    **snapshot,
                }
            except Exception:
                return None

    results = await asyncio.gather(*[one(t) for t in tickers], return_exceptions=True)
    return [r for r in results if r and not isinstance(r, Exception)]


async def _basket_records() -> list[dict]:
    """Cached snapshot of the documented NSE universe."""
    cached = _cache_get("basket", 60)
    if cached is not None:
        return list(cached)

    async with _BASKET_LOCK:
        cached = _cache_get("basket", 60)
        if cached is not None:
            return list(cached)

        tickers = [item["ticker"] for item in INSTRUMENT_UNIVERSE]
        records: list[dict] = []
        try:
            batch = await asyncio.to_thread(_download_batch, tickers, "1mo", "1d")
            records = _records_from_batch(batch, tickers)
        except Exception as exc:
            logger.warning("Batched NSE basket download failed: %s", exc)

        if not records:
            logger.info("Falling back to individual NSE basket downloads")
            records = await _fetch_individual_records(tickers)

        _cache_put("basket", records)
        return records


async def fetch_gainers_losers_active(limit: int = 10) -> dict:
    """Top gainers, losers and most active from the documented NSE universe.

    Only genuine positive movers appear under gainers and only genuine
    negative movers under losers.  Most active is sorted by traded volume,
    never by price movement.
    """
    records = await _basket_records()
    gainers = sorted(
        (r for r in records if r["change_pct"] > 0),
        key=lambda r: r["change_pct"],
        reverse=True,
    )[:limit]
    losers = sorted(
        (r for r in records if r["change_pct"] < 0),
        key=lambda r: r["change_pct"],
    )[:limit]
    most_active = sorted(records, key=lambda r: r["volume"], reverse=True)[:limit]

    return {
        "gainers": gainers,
        "losers": losers,
        "most_active": most_active,
        "universe_size": len(records),
        "status": "ok" if records else "unavailable",
        "source": "yfinance",
        "timestamp": int(time.time()),
    }


async def fetch_sector_performance() -> list[dict]:
    """Sector performance using the real NSE sector indices."""
    cached = _cache_get("sectors", 120)
    if cached is not None:
        return list(cached)

    tickers = list(SECTOR_TICKERS.values())
    batch = None
    try:
        batch = await asyncio.to_thread(_download_batch, tickers, "1mo", "1d")
    except Exception as exc:
        logger.warning("Sector batch download failed: %s", exc)

    output: list[dict] = []
    for name, ticker in SECTOR_TICKERS.items():
        snapshot = _row_snapshot(_normalize_frame(_sub_frame(batch, ticker)))
        if snapshot is None:
            # One retry per sector keeps a single bad ticker from blanking the grid.
            try:
                frame = await asyncio.to_thread(_fetch_ticker_data, ticker, "1mo", "1d")
                snapshot = _row_snapshot(_normalize_frame(frame))
            except Exception as exc:
                logger.debug("Sector fetch failed for %s: %s", name, exc)
                snapshot = None

        if snapshot is None:
            output.append(
                {
                    "sector": name,
                    "symbol": ticker,
                    "status": "unavailable",
                    "error": "Provider returned no usable data",
                    "change_pct": None,
                    "price": None,
                }
            )
        else:
            output.append(
                {
                    "sector": name,
                    "symbol": ticker,
                    **snapshot,
                    "status": "ok",
                    "source": "yfinance",
                }
            )

    _cache_put("sectors", output)
    return list(output)


async def fetch_market_breadth() -> dict:
    """Market breadth from the same documented NSE universe as Market Pulse."""
    records = await _basket_records()

    advancing = sum(1 for r in records if r["change_pct"] > 0.005)
    declining = sum(1 for r in records if r["change_pct"] < -0.005)
    unchanged = sum(1 for r in records if abs(r["change_pct"]) <= 0.005)
    total = len(records)

    return {
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "total": total,
        "advance_decline_ratio": round(advancing / declining, 2) if declining > 0 else None,
        "advance_decline_ratio_display": (
            f"{advancing / declining:.2f}" if declining > 0 else ("∞" if advancing > 0 else None)
        ),
        "universe_size": len(INSTRUMENT_UNIVERSE),
        "status": "ok" if total else "unavailable",
        "source": "yfinance",
        "timestamp": int(time.time()),
    }


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

_NEWS_TICKERS = ["^NSEI", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
_NEWS_LOCK = asyncio.Lock()


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _parse_pub_date(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
            return int(parsed.timestamp())
        except ValueError:
            pass
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
            return int(parsed.timestamp())
        except (TypeError, ValueError):
            return None
    return None


def _parse_news_item(item: dict, retrieved_at: int) -> Optional[dict]:
    """Handle both the legacy flat yfinance news shape and the nested one."""
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    body = content or item

    title = (body.get("title") or item.get("title") or "").strip()
    if not title:
        return None

    summary = (body.get("summary") or body.get("description") or "") or ""
    summary = re.sub(r"\s+", " ", summary).strip()[:320]

    provider = body.get("provider")
    if isinstance(provider, dict):
        publisher = provider.get("displayName") or provider.get("name") or "Unknown"
    else:
        publisher = body.get("publisher") or body.get("source") or "Unknown"

    canonical = body.get("canonicalUrl") or body.get("clickThroughUrl")
    if isinstance(canonical, dict):
        url = canonical.get("url") or ""
    else:
        url = body.get("link") or body.get("url") or ""

    published_at = _parse_pub_date(
        body.get("pubDate")
        or body.get("providerPublishTime")
        or body.get("published_at")
    )

    related = body.get("relatedTickers") or body.get("related_symbols") or []
    if not isinstance(related, list):
        related = []
    inferred_symbols, inferred_sectors = _infer_topics(title)

    return {
        "title": title,
        "summary": summary,
        "source": str(publisher),
        "url": str(url),
        "published_at": published_at,
        "retrieved_at": retrieved_at,
        "related_symbols": ([str(s) for s in related] or inferred_symbols)[:5],
        "related_sectors": inferred_sectors,
        "origin": "Yahoo Finance",
    }


_RSS_URL = "https://news.google.com/rss/search"
_RSS_QUERY = '(NSE OR BSE OR RBI OR Sensex OR Nifty OR "Indian stock market") when:2d'

_SECTOR_KEYWORDS = {
    "Banking": ("bank", "rbi", "repo rate", "lending", "npa"),
    "Information Technology": ("infosys", "tcs", "wipro", "tech mahindra", "hcl", "it sector"),
    "Automobile": ("auto", "car", "suv", "maruti", "mahindra"),
    "Pharmaceuticals": ("pharma", "drug", "cipla", "sun pharma", "dr reddy"),
    "FMCG": ("fmcg", "hindustan unilever", "itc", "nestle", "britannia"),
    "Energy": ("oil", "gas", "reliance", "ongc", "ntpc", "power"),
    "Metals": ("steel", "metal", "tata steel", "jsw"),
    "Realty": ("realty", "real estate", "housing"),
    "Financial Services": ("insurance", "mutual fund", "nbfc", "bajaj finance"),
}

_MARKET_NEWS_KEYWORDS = (
    "nifty",
    "sensex",
    "bse",
    "nse",
    "rbi",
    "sebi",
    "stock",
    "share",
    "equit",
    "market",
    "bank",
    "rupee",
    "inflation",
    "gdp",
    "economy",
    "ipo",
    "mutual fund",
    "earnings",
    "quarter",
    "oil",
    "gold",
    "dalal street",
    "fii",
    "dii",
    "bond",
    "yield",
    "sebi",
)

_NEWS_JUNK_PATTERNS = (
    "premier news agency",
    "latest news",
    "breaking news",
    "top headlines",
    "news live",
    "watch live",
)


def _looks_like_market_headline(title: str) -> bool:
    text = (title or "").lower()
    if not text or any(pattern in text for pattern in _NEWS_JUNK_PATTERNS):
        return False
    return any(keyword in text for keyword in _MARKET_NEWS_KEYWORDS)


def _is_near_duplicate_title(first: str, second: str) -> bool:
    """Catch the same story re-headlined by different outlets.

    Google News often carries near-identical headlines from several
    publications.  Exact-title dedupe misses those, so compare normalised
    text with a conservative similarity threshold that still keeps genuinely
    different market wraps apart.
    """
    if first == second:
        return True
    if len(first) < 25 or len(second) < 25:
        return False
    ratio = SequenceMatcher(None, first, second).ratio()
    if ratio >= 0.55:
        return True
    if ratio < 0.5:
        return False
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    if not first_tokens or not second_tokens:
        return False
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens) >= 0.5


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _infer_topics(title: str) -> tuple[list[str], list[str]]:
    """Infer related NSE symbols / sectors from a headline (no guessing)."""
    text = (title or "").lower()
    symbols: list[str] = []
    for item in INSTRUMENT_UNIVERSE:
        symbol = item["symbol"].lower()
        name = item["name"].lower()
        symbol_hit = len(symbol) >= 3 and re.search(rf"\b{re.escape(symbol)}\b", text)
        name_hit = len(name) >= 4 and name in text
        if symbol_hit or name_hit:
            symbols.append(item["symbol"])

    sectors = [
        sector
        for sector, keywords in _SECTOR_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    return symbols[:4], sectors[:2]


async def _fetch_yahoo_news(retrieved_at: int) -> list[dict]:
    async def fetch_ticker_news(ticker: str):
        try:
            ticker_obj = yf.Ticker(ticker)
            return await asyncio.to_thread(lambda: ticker_obj.news)
        except Exception:
            return []

    results = await asyncio.gather(
        *[fetch_ticker_news(t) for t in _NEWS_TICKERS], return_exceptions=True
    )

    parsed: list[dict] = []
    for result in results:
        if not isinstance(result, list):
            continue
        for raw in result:
            if not isinstance(raw, dict):
                continue
            item = _parse_news_item(raw, retrieved_at)
            if item is not None:
                parsed.append(item)
    return parsed


async def _fetch_rss_news(retrieved_at: int, limit: int) -> list[dict]:
    """Secondary real-news source used only when Yahoo's news API is unavailable."""
    params = {"q": _RSS_QUERY, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; QuantNiti/1.0)"}
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
        response = await client.get(_RSS_URL, params=params)
        response.raise_for_status()
        root = ET.fromstring(response.text)

    items: list[dict] = []
    for node in root.findall(".//item")[: max(limit * 2, 10)]:
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        source = (node.findtext("source") or "Google News").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        if not _looks_like_market_headline(title):
            continue

        summary = _strip_html(node.findtext("description") or "")[:320]
        if summary and source and summary.endswith(f" {source}"):
            summary = summary[: -(len(source) + 1)].strip()
        title_key = _normalize_title(title)
        summary_key = _normalize_title(summary)
        if not summary or summary_key == title_key or title_key.startswith(summary_key) and len(summary_key) < 12:
            summary = ""
        link = (node.findtext("link") or "").strip()
        published_at = _parse_pub_date(node.findtext("pubDate"))
        symbols, sectors = _infer_topics(title)
        items.append(
            {
                "title": title,
                "summary": summary,
                "source": source,
                "url": link,
                "published_at": published_at,
                "retrieved_at": retrieved_at,
                "related_symbols": symbols,
                "related_sectors": sectors,
                "origin": "Google News RSS",
            }
        )
    return items


async def fetch_market_news(limit: int = 10) -> list[dict]:
    """Fetch Indian financial market news from Yahoo Finance, with an RSS fallback.

    Deduplicates by normalised title and URL, keeps the original article
    link, and timestamps each item with both publication and retrieval time.
    No headline is ever generated locally.
    """
    cached = _cache_get("news", 300)
    if cached is not None:
        return list(cached)[:limit]

    async with _NEWS_LOCK:
        cached = _cache_get("news", 300)
        if cached is not None:
            return list(cached)[:limit]

        retrieved_at = int(time.time())
        yahoo_items, rss_items = await asyncio.gather(
            _fetch_yahoo_news(retrieved_at),
            _fetch_rss_news(retrieved_at, limit),
            return_exceptions=True,
        )
        if isinstance(yahoo_items, Exception):
            logger.info("Yahoo news unavailable: %s", yahoo_items)
            yahoo_items = []
        if isinstance(rss_items, Exception):
            logger.info("RSS news unavailable: %s", rss_items)
            rss_items = []

        seen_titles: set[str] = set()
        seen_urls: set[str] = set()
        unique: list[dict] = []
        for parsed in list(yahoo_items) + list(rss_items):
            if not isinstance(parsed, dict):
                continue
            title_key = _normalize_title(parsed["title"])
            url_key = parsed["url"].split("?")[0].strip().lower()
            if title_key in seen_titles or (url_key and url_key in seen_urls):
                continue
            if any(_is_near_duplicate_title(title_key, seen) for seen in seen_titles):
                continue
            seen_titles.add(title_key)
            if url_key:
                seen_urls.add(url_key)
            unique.append(parsed)

        unique.sort(key=lambda n: n.get("published_at") or 0, reverse=True)
        _cache_put("news", unique)
        return unique[:limit]

"""Public market-data endpoints (no login required).

The landing page polls these for an optional *real* NIFTY 50 feed. When the
market is closed (or Yahoo is unreachable) the endpoint answers 503 and the
frontend keeps its local simulator running ΓÇö the chart never goes blank.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.yahoo_retry import retry_call

router = APIRouter(
    prefix="/market",
    tags=["market"],
)

_IST = ZoneInfo("Asia/Kolkata")
_TICKER = "^NSEI"
# NSE cash-market session, IST, Monday(0)ΓÇôFriday(4).
_OPEN_MINUTES = 9 * 60 + 15
_CLOSE_MINUTES = 15 * 60 + 30


class NiftyLiveOut(BaseModel):
    time: int  # unix seconds, start of the 1-minute bar
    open: float
    high: float
    low: float
    close: float
    market_open: bool
    source: str = "yfinance"


class NiftyHistoryOut(BaseModel):
    time: int  # unix seconds, start of the 1-minute bar
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


def market_is_open(now: datetime | None = None) -> bool:
    """True during the NSE cash session (MonΓÇôFri, 09:15ΓÇô15:30 IST)."""
    now = now or datetime.now(_IST)
    if now.weekday() > 4:
        return False
    minutes = now.hour * 60 + now.minute
    return _OPEN_MINUTES <= minutes < _CLOSE_MINUTES


def _fetch_latest_1m() -> dict:
    """Blocking yfinance call ΓÇö always executed in a worker thread."""
    import yfinance as yf

    def _do():
        frame = yf.Ticker(_TICKER).history(period="1d", interval="1m")
        if frame is None or frame.empty:
            raise ValueError("yfinance returned no 1-minute bars for ^NSEI")
        return frame

    frame = retry_call(
        fn=_do,
        ticker=_TICKER,
        period="1d",
        interval="1m",
        max_attempts=3,
        is_empty=lambda f: f is None or getattr(f, "empty", True),
    )
    row = frame.iloc[-1]
    ts = int(frame.index[-1].timestamp())
    return {
        "time": ts - (ts % 60),
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
    }


def _fetch_1m_bars(ticker: str, limit: int = 150) -> list[dict]:
    """Blocking yfinance call ΓÇö always executed in a worker thread."""
    import yfinance as yf

    def _do():
        frame = yf.Ticker(ticker).history(period="1d", interval="1m")
        if frame is None or frame.empty:
            raise ValueError(f"yfinance returned no 1-minute bars for {ticker}")
        return frame

    frame = retry_call(
        fn=_do,
        ticker=ticker,
        period="1d",
        interval="1m",
        max_attempts=3,
        is_empty=lambda f: f is None or getattr(f, "empty", True),
    )
    frame = frame.dropna().tail(limit)
    bars = []
    for ts, row in frame.iterrows():
        unix = int(ts.timestamp())
        bars.append(
            {
                "time": unix - (unix % 60),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row.get("Volume", 0) or 0),
            }
        )
    if not bars:
        raise ValueError(f"yfinance returned no usable 1-minute bars for {ticker}")
    return bars


@router.get("/nifty-live", response_model=NiftyLiveOut)
async def nifty_live() -> NiftyLiveOut:
    """Latest 1-minute ^NSEI candle.

    503 when the market is closed or Yahoo has no fresh bar ΓÇö the caller
    must fall back to simulated data.
    """
    open_now = market_is_open()
    try:
        bar = await asyncio.to_thread(_fetch_latest_1m)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"live Nifty 50 feed unavailable: {exc}",
        ) from exc
    return NiftyLiveOut(market_open=open_now, **bar)


@router.get("/nifty-history", response_model=list[NiftyHistoryOut])
async def nifty_history(limit: int = 150) -> list[NiftyHistoryOut]:
    """Today's NIFTY 50 (^NSEI) 1-minute bars (oldest ΓåÆ newest), capped at `limit`.

    The frontend loads this once on mount to populate the chart, then keeps
    the live edge fresh via /market/nifty-live. 503 when Yahoo has nothing
    usable ΓÇö the caller must fall back to simulated data.
    """
    try:
        bars = await asyncio.to_thread(_fetch_1m_bars, _TICKER, max(1, min(limit, 375)))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"NIFTY 50 history unavailable: {exc}",
        ) from exc
    return [NiftyHistoryOut(**bar) for bar in bars]

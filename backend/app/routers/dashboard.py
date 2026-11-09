"""Dashboard API endpoints for the Indian market intelligence terminal.

Everything here is read-only market intelligence plus a *monitor* over the
existing paper-trading engine.  No endpoint invents prices, and no endpoint
places a real order.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import statistics
import time
from datetime import datetime, timedelta
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, verify_user
from app.database import get_db
from app.models import (
    BacktestResult,
    Conversation,
    DeploymentStatus,
    PaperDeployment,
    PaperEquitySnapshot,
    PaperOrder,
    PaperPosition,
    PaperTrade,
    Strategy,
    StrategyStatus,
)
from app.services.llm_errors import LLMNotConfiguredError
from app.services.llm_service import chat_completion
from app.services.market_data_extended import (
    INDEX_NAMES,
    INDEX_TICKERS,
    TIMEFRAME_MAP,
    MarketDataError,
    fetch_chart_history,
    fetch_gainers_losers_active,
    fetch_index_quote,
    fetch_market_breadth,
    fetch_market_news,
    fetch_multiple_index_quotes,
    fetch_sector_performance,
    get_market_status,
)
from app.services.paper_bars import PaperBarsError, load_bars
from app.services.paper_engine import account_snapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_IST = ZoneInfo("Asia/Kolkata")


def _now_ist() -> datetime:
    return datetime.now(_IST)


# ============================================================
# User-scoped query helpers
# ============================================================


def _get_user_strategy_ids(db: Session, user_id: str) -> List[str]:
    """Get all strategy IDs for a user."""
    return [
        s.id
        for s in db.query(Strategy.id)
        .join(Conversation)
        .filter(Conversation.user_id == user_id)
        .all()
    ]


def _get_user_conversation_ids(db: Session, user_id: str) -> List[str]:
    """Get all conversation IDs for a user."""
    return [
        c.id for c in db.query(Conversation.id).filter(Conversation.user_id == user_id).all()
    ]


def _get_user_deployment_ids(db: Session, strategy_ids: List[str]) -> List[str]:
    """Get all deployment IDs for given strategy IDs."""
    if not strategy_ids:
        return []
    return [
        d.id
        for d in db.query(PaperDeployment.id)
        .filter(PaperDeployment.strategy_id.in_(strategy_ids))
        .all()
    ]


# ============================================================
# Status helpers
# ============================================================


def _derive_data_status(timestamp: Optional[int], market_status: dict) -> str:
    """Classify a provider timestamp against the current Indian session.

    Only an open session with a genuinely recent print can be LIVE.  A
    closed session is always HISTORICAL — the dashboard must never label
    last session's candles as live.
    """
    if not timestamp:
        return "UNAVAILABLE"

    age = max(0, int(time.time()) - int(timestamp))
    phase = (market_status or {}).get("status")

    if phase == "OPEN":
        if age <= 120:
            return "LIVE"
        if age <= 900:
            return "DELAYED"
        return "STALE"
    if phase == "PRE-OPEN":
        return "PRE_OPEN"
    if phase == "CLOSED":
        return "HISTORICAL"
    return "UNAVAILABLE"


def _decorate_quote(quote: dict, market_status: dict) -> dict:
    enriched = dict(quote)
    enriched["data_status"] = _derive_data_status(quote.get("timestamp"), market_status)
    if quote.get("timestamp"):
        enriched["data_age_seconds"] = max(0, int(time.time()) - int(quote["timestamp"]))
    else:
        enriched["data_age_seconds"] = None
    enriched["market_status"] = (market_status or {}).get("status", "UNKNOWN")
    enriched.setdefault("source", "yfinance")
    return enriched


# ============================================================
# Market Overview
# ============================================================


@router.get("/market/overview")
async def market_overview():
    """Overview of the major Indian indices, with a consistent session status."""
    symbols = list(INDEX_TICKERS.keys())
    quotes = await fetch_multiple_index_quotes(symbols)
    market_status = get_market_status()

    indices = []
    for quote in quotes:
        if quote.get("status") == "unavailable" or "price" not in quote:
            indices.append(
                {
                    "symbol": quote.get("symbol"),
                    "name": quote.get("name") or INDEX_NAMES.get(quote.get("symbol", ""), ""),
                    "status": "unavailable",
                    "data_status": "UNAVAILABLE",
                    "error": quote.get("error"),
                    "source": "yfinance",
                }
            )
        else:
            indices.append(_decorate_quote(quote, market_status))

    return {
        "indices": indices,
        "market_status": market_status,
        "timestamp": int(time.time()),
        "source": "yfinance",
    }


@router.get("/market/quote/{symbol}")
async def market_quote(symbol: str):
    """Detailed quote for a single symbol with data-freshness metadata."""
    symbol = symbol.upper()
    if symbol not in INDEX_TICKERS:
        raise HTTPException(status_code=404, detail=f"Unknown index: {symbol}")

    try:
        quote = await fetch_index_quote(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _decorate_quote(quote, get_market_status())


# ============================================================
# Technical Indicators
# ============================================================


def compute_sma(prices: list[float], period: int) -> list[Optional[float]]:
    """Simple moving average, aligned to the input length."""
    out: list[Optional[float]] = [None] * len(prices)
    if period <= 0 or len(prices) < period:
        return out
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1 : i + 1]
        out[i] = sum(window) / period
    return out


def compute_ema(prices: list[float], period: int) -> list[Optional[float]]:
    """Exponential moving average, aligned to the input length."""
    out: list[Optional[float]] = [None] * len(prices)
    if period <= 0 or len(prices) < period:
        return out
    multiplier = 2 / (period + 1)
    first = sum(prices[:period]) / period
    out[period - 1] = first
    previous = first
    for i in range(period, len(prices)):
        previous = (prices[i] * multiplier) + (previous * (1 - multiplier))
        out[i] = previous
    return out


def compute_rsi(prices: list[float], period: int = 14) -> list[Optional[float]]:
    """Wilder's RSI, aligned to the input length."""
    out: list[Optional[float]] = [None] * len(prices)
    if len(prices) < period + 1:
        return out

    gains = [0.0] * len(prices)
    losses = [0.0] * len(prices)
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains[i] = change
        else:
            losses[i] = -change

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period

    def rsi_value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    out[period] = rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = rsi_value(avg_gain, avg_loss)
    return out


def compute_macd(
    prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, list[Optional[float]]]:
    """MACD line, signal line and histogram, aligned to the input length."""
    ema_fast = compute_ema(prices, fast)
    ema_slow = compute_ema(prices, slow)

    macd_line: list[Optional[float]] = [None] * len(prices)
    for i in range(len(prices)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    signal_line: list[Optional[float]] = [None] * len(prices)
    histogram: list[Optional[float]] = [None] * len(prices)

    valid = [value for value in macd_line if value is not None]
    if len(valid) >= signal:
        signal_ema = compute_ema(valid, signal)
        valid_positions = [i for i, value in enumerate(macd_line) if value is not None]
        for idx, position in enumerate(valid_positions):
            value = signal_ema[idx]
            if value is not None:
                signal_line[position] = value
                histogram[position] = macd_line[position] - value

    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def _build_indicators(bars: list[dict]) -> dict:
    closes = [float(bar["close"]) for bar in bars]
    macd = compute_macd(closes)
    return {
        "ema9": compute_ema(closes, 9),
        "ema21": compute_ema(closes, 21),
        "ema50": compute_ema(closes, 50),
        "ema200": compute_ema(closes, 200),
        "sma20": compute_sma(closes, 20),
        "rsi": compute_rsi(closes, 14),
        "macd": macd["macd"],
        "macd_signal": macd["signal"],
        "macd_histogram": macd["histogram"],
    }


@router.get("/market/chart/{symbol}")
async def market_chart(
    symbol: str,
    timeframe: str = Query("1d", pattern="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(500, ge=1, le=1000),
    include_indicators: bool = Query(True),
):
    """Historical candles plus indicators calculated from those exact candles."""
    symbol = symbol.upper()
    if symbol not in INDEX_TICKERS:
        raise HTTPException(status_code=404, detail=f"Unknown index: {symbol}")

    if timeframe not in TIMEFRAME_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")

    try:
        bars = await fetch_chart_history(symbol, timeframe, limit)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not bars:
        raise HTTPException(
            status_code=503,
            detail=f"The provider returned no {timeframe} candles for {symbol}.",
        )

    market_status = get_market_status()
    last_bar_time = bars[-1]["time"]

    payload: dict[str, Any] = {
        "symbol": symbol,
        "name": INDEX_NAMES.get(symbol, symbol),
        "timeframe": timeframe,
        "bars": bars,
        "count": len(bars),
        "last_bar_time": last_bar_time,
        "data_status": _derive_data_status(last_bar_time, market_status),
        "market_status": market_status,
        "source": "yfinance",
    }
    if include_indicators:
        payload["indicators"] = _build_indicators(bars)
    return payload


@router.get("/market/indicators/{symbol}")
async def market_indicators(
    symbol: str,
    timeframe: str = Query("1d", pattern="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(500, ge=50, le=1000),
):
    """Indicators only (kept for callers that do not need the candles)."""
    symbol = symbol.upper()
    if symbol not in INDEX_TICKERS:
        raise HTTPException(status_code=404, detail=f"Unknown index: {symbol}")

    if timeframe not in TIMEFRAME_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")

    try:
        bars = await fetch_chart_history(symbol, timeframe, limit)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not bars:
        raise HTTPException(status_code=503, detail="No data available")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "timestamps": [bar["time"] for bar in bars],
        "closes": [bar["close"] for bar in bars],
        "volumes": [bar.get("volume", 0) for bar in bars],
        "indicators": _build_indicators(bars),
        "source": "yfinance",
    }


# ============================================================
# Market Pulse
# ============================================================


@router.get("/market/pulse")
async def market_pulse():
    """Gainers, losers, most active, sector performance and breadth."""
    try:
        gainers_losers, sectors, breadth = await asyncio.gather(
            fetch_gainers_losers_active(10),
            fetch_sector_performance(),
            fetch_market_breadth(),
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "gainers": gainers_losers["gainers"],
        "losers": gainers_losers["losers"],
        "most_active": gainers_losers["most_active"],
        "sectors": sectors,
        "breadth": breadth,
        "market_status": get_market_status(),
        "universe_size": gainers_losers.get("universe_size", 0),
        "status": gainers_losers.get("status", "unavailable"),
        "source": "yfinance",
        "timestamp": int(time.time()),
    }


# ============================================================
# Market News
# ============================================================


@router.get("/market/news")
async def market_news(limit: int = Query(20, ge=1, le=50)):
    """Indian financial market news, deduplicated and timestamped."""
    try:
        news = await fetch_market_news(limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to fetch news: {exc}") from exc

    return {
        "news": news,
        "count": len(news),
        "status": "ok" if news else "unavailable",
        "source": ", ".join(sorted({str(n.get("origin")) for n in news if n.get("origin")}))
        or "yfinance",
        "sources": sorted({str(n.get("origin")) for n in news if n.get("origin")}),
        "retrieved_at": int(time.time()),
        "timestamp": int(time.time()),
    }


# ============================================================
# AI Market Briefing
# ============================================================

BRIEFING_MODES = {"concise", "detailed", "explain"}

_BRIEFING_CACHE: dict[str, tuple[float, dict]] = {}
_BRIEFING_CACHE_TTL = 120


class BriefingRequest(BaseModel):
    mode: str = "concise"
    force: bool = False


BRIEFING_SYSTEM_PROMPT = """You are QuantNiti AI, a careful Indian market analyst.

You receive a JSON fact sheet containing index quotes, sector performance,
market breadth, movers, volatility (INDIA VIX) and news headlines.  Some
fields may be null or marked unavailable.

Return ONLY a valid JSON object with exactly these keys:
{
  "sentiment": "Bullish" | "Bearish" | "Sideways" | "Mixed" | "Insufficient Data",
  "market_direction": "one short paragraph",
  "sector_analysis": {
    "strong": [{"sector": "...", "change_pct": number}],
    "weak": [{"sector": "...", "change_pct": number}],
    "unusual": ["short observation"]
  },
  "volatility_analysis": "one short paragraph",
  "observations": ["3-5 short factual observations"],
  "risk_alerts": ["0-5 short alerts"],
  "interpretation": "one short educational paragraph"
}

Rules:
- Use ONLY the supplied facts. Never invent a price, index level, news item or indicator.
- If a fact is missing, say it is unavailable instead of guessing.
- Distinguish facts from interpretation. Do not predict a direction with confidence.
- The interpretation explains what the data suggests; it is not a trading signal.
- Keep the whole response under 320 words. No markdown fences, no extra keys.
"""


def _usable_quote(quote: dict) -> bool:
    return bool(quote) and quote.get("status") != "unavailable" and quote.get("price") is not None


def _derive_sentiment(main_moves: list[float]) -> str:
    if not main_moves:
        return "Insufficient Data"
    positives = [m for m in main_moves if m > 0.15]
    negatives = [m for m in main_moves if m < -0.15]
    if positives and negatives:
        if max(main_moves) > 0.3 and min(main_moves) < -0.3:
            return "Mixed"
    if len(positives) >= 2 and not negatives:
        return "Bullish"
    if len(negatives) >= 2 and not positives:
        return "Bearish"
    average = sum(main_moves) / len(main_moves)
    if average > 0.25:
        return "Bullish"
    if average < -0.25:
        return "Bearish"
    return "Sideways"


def _rule_briefing(
    quotes: list[dict],
    sectors: list[dict],
    breadth: dict,
    movers: dict,
    news: list[dict],
    market_status: dict,
    mode: str,
) -> dict:
    """Deterministic, clearly-labelled fallback built only from facts."""
    main_symbols = ["NIFTY50", "BANKNIFTY", "SENSEX"]
    by_symbol = {q.get("symbol"): q for q in quotes if _usable_quote(q)}
    main_quotes = [by_symbol[s] for s in main_symbols if s in by_symbol]
    main_moves = [float(q.get("change_pct") or 0) for q in main_quotes]
    sentiment = _derive_sentiment(main_moves)

    if main_quotes:
        direction_bits = [
            f"{q.get('name') or q['symbol']} {float(q.get('change_pct') or 0):+.2f}%"
            for q in main_quotes
        ]
        market_direction = (
            "Major indices: " + ", ".join(direction_bits) + ". "
            + ("All three are moving in the same direction." if len({m > 0 for m in main_moves}) == 1
               else "The major indices are not moving uniformly.")
        )
    else:
        market_direction = (
            "Index data is unavailable from the provider, so market direction cannot be established."
        )

    usable_sectors = [
        s for s in sectors
        if s.get("status") == "ok" and s.get("change_pct") is not None
    ]
    ranked = sorted(usable_sectors, key=lambda s: float(s["change_pct"]), reverse=True)
    strong = [
        {"sector": s["sector"], "change_pct": round(float(s["change_pct"]), 2)}
        for s in ranked[:3]
        if float(s["change_pct"]) > 0
    ]
    weak = [
        {"sector": s["sector"], "change_pct": round(float(s["change_pct"]), 2)}
        for s in ranked[::-1][:3]
        if float(s["change_pct"]) < 0
    ]
    unusual = [
        f"{s['sector']} moved {float(s['change_pct']):+.2f}%"
        for s in ranked
        if abs(float(s["change_pct"])) >= 1.5
    ][:3]
    sector_analysis = {
        "strong": strong,
        "weak": weak,
        "unusual": unusual or (["No unusual sector move exceeded 1.5%."] if usable_sectors else []),
    }

    vix_quote = by_symbol.get("INDIAVIX")
    if _usable_quote(vix_quote):
        vix_level = float(vix_quote.get("price") or 0)
        vix_change = float(vix_quote.get("change_pct") or 0)
        if vix_level < 13:
            volatility_level = "Low"
        elif vix_level < 20:
            volatility_level = "Moderate"
        else:
            volatility_level = "High"
        volatility_analysis = (
            f"INDIA VIX is at {vix_level:,.2f} ({vix_change:+.2f}%), a {volatility_level.lower()} "
            "volatility reading based on the latest available quote."
        )
    else:
        volatility_level = "Unavailable"
        volatility_analysis = (
            "Volatility analysis cannot be completed because INDIA VIX data was not returned by the provider."
        )

    observations: list[str] = []
    if main_quotes:
        strongest = max(main_quotes, key=lambda q: abs(float(q.get("change_pct") or 0)))
        observations.append(
            f"{strongest.get('name') or strongest['symbol']} is the largest mover among the three headline indices "
            f"at {float(strongest.get('change_pct') or 0):+.2f}%."
        )
    if breadth.get("status") == "ok" and breadth.get("total"):
        observations.append(
            f"Breadth across the tracked NSE universe: {breadth['advancing']} advancing, "
            f"{breadth['declining']} declining, {breadth['unchanged']} unchanged."
        )
    else:
        observations.append("Market breadth is unavailable, so participation cannot be assessed.")
    if movers.get("gainers"):
        top = movers["gainers"][0]
        observations.append(
            f"Top gainer: {top['name']} ({top['symbol']}) at {float(top['change_pct']):+.2f}%."
        )
    if movers.get("losers"):
        bottom = movers["losers"][0]
        observations.append(
            f"Top loser: {bottom['name']} ({bottom['symbol']}) at {float(bottom['change_pct']):+.2f}%."
        )
    if strong:
        observations.append(
            f"Strongest sector: {strong[0]['sector']} ({strong[0]['change_pct']:+.2f}%)."
        )
    if market_status.get("status") == "CLOSED":
        observations.append("The market is closed; these figures reflect the latest completed session.")
    if mode in {"detailed", "explain"} and usable_sectors:
        missing = [s["sector"] for s in sectors if s.get("status") != "ok"]
        if missing:
            observations.append(f"Sector data unavailable for: {', '.join(missing)}.")
    observations = observations[:5]

    risk_alerts: list[str] = []
    if market_status.get("status") == "CLOSED":
        risk_alerts.append("Market is closed — data is historical, not a live exchange feed.")
    if not _usable_quote(vix_quote):
        risk_alerts.append("INDIA VIX is unavailable, so volatility risk cannot be measured.")
    if breadth.get("status") != "ok" or not breadth.get("total"):
        risk_alerts.append("Market breadth is unavailable or incomplete.")
    elif breadth.get("total", 0) < 10:
        risk_alerts.append("The breadth sample is small; treat the advance/decline reading cautiously.")
    if main_moves and max(main_moves) > 0.3 and min(main_moves) < -0.3:
        risk_alerts.append("The major indices are moving in opposite directions.")
    if any(abs(m) >= 2.0 for m in main_moves):
        risk_alerts.append("At least one headline index moved 2% or more.")
    stale = [
        q.get("name") or q.get("symbol")
        for q in quotes
        if q.get("data_status") in {"STALE", "UNAVAILABLE"}
    ]
    if stale:
        risk_alerts.append(f"Stale or unavailable data: {', '.join(str(s) for s in stale)}.")
    if not news:
        risk_alerts.append("No recent news headlines were returned by the provider.")
    risk_alerts = risk_alerts[:5]

    if sentiment == "Insufficient Data":
        interpretation = (
            "There is not enough reliable market data to explain the current session. "
            "No directional conclusion is drawn. This is not a forecast or a trading recommendation."
        )
    else:
        breadth_text = (
            "breadth is positive" if breadth.get("advancing", 0) > breadth.get("declining", 0)
            else "breadth is negative" if breadth.get("declining", 0) > breadth.get("advancing", 0)
            else "breadth is balanced"
        )
        interpretation = (
            f"Based on the latest available data, the market reads as {sentiment.lower()}, and "
            f"{breadth_text}. {volatility_analysis} This is an educational interpretation of "
            "observed data, not a forecast or a trading recommendation."
        )
        if mode == "explain":
            interpretation += (
                " Index moves show where large-cap money is leaning; sector and breadth data show "
                "whether that move is broad or concentrated."
            )
        elif mode == "detailed":
            interpretation += (
                " A detailed read should also consider news flow, upcoming events and the "
                "difference between intraday and end-of-session data."
            )

    return {
        "sentiment": sentiment,
        "market_direction": market_direction,
        "sector_analysis": sector_analysis,
        "volatility_analysis": volatility_analysis,
        "volatility_level": volatility_level,
        "observations": observations,
        "risk_alerts": risk_alerts,
        "interpretation": interpretation,
    }


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("sector") or item.get("text")
            if label:
                out.append(str(label))
        if len(out) >= limit:
            break
    return out


def _coerce_sector_list(
    value: Any,
    limit: int,
    known: Optional[dict[str, float]] = None,
    direction: int = 0,
) -> list[dict]:
    """Keep only sector entries that correspond to real supplied sector facts."""
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        sector = str(item.get("sector") or "").strip()
        if not sector:
            continue
        if known is not None:
            if sector not in known:
                continue
            change_pct = known[sector]
        else:
            try:
                change_pct = float(item.get("change_pct"))
            except (TypeError, ValueError):
                continue
        if direction > 0 and change_pct <= 0:
            continue
        if direction < 0 and change_pct >= 0:
            continue
        out.append({"sector": sector, "change_pct": round(float(change_pct), 2)})
        if len(out) >= limit:
            break
    return out


def _merge_llm_briefing(
    llm: dict, fallback: dict, known_sectors: Optional[dict[str, float]] = None
) -> dict:
    sentiment = str(llm.get("sentiment") or "").strip().title()
    if sentiment not in {"Bullish", "Bearish", "Sideways", "Mixed", "Insufficient Data"}:
        sentiment = fallback["sentiment"]

    sector = llm.get("sector_analysis")
    if not isinstance(sector, dict):
        sector = fallback["sector_analysis"]
    else:
        strong = _coerce_sector_list(sector.get("strong"), 3, known_sectors, direction=1)
        weak = _coerce_sector_list(sector.get("weak"), 3, known_sectors, direction=-1)
        unusual = sector.get("unusual")
        sector = {
            "strong": strong or fallback["sector_analysis"]["strong"],
            "weak": weak or fallback["sector_analysis"]["weak"],
            "unusual": _coerce_string_list(unusual, 3) or fallback["sector_analysis"]["unusual"],
        }

    observations = _coerce_string_list(llm.get("observations"), 5) or fallback["observations"]
    risk_alerts = _coerce_string_list(llm.get("risk_alerts"), 5)

    volatility_text = llm.get("volatility_analysis")
    if not isinstance(volatility_text, str) or not volatility_text.strip():
        volatility_text = fallback["volatility_analysis"]

    interpretation = llm.get("interpretation")
    if not isinstance(interpretation, str) or not interpretation.strip():
        interpretation = fallback["interpretation"]

    direction = llm.get("market_direction")
    if not isinstance(direction, str) or not direction.strip():
        direction = fallback["market_direction"]

    return {
        "sentiment": sentiment,
        "market_direction": direction.strip(),
        "sector_analysis": sector,
        "volatility_analysis": volatility_text.strip(),
        "volatility_level": fallback["volatility_level"],
        "observations": observations,
        "risk_alerts": risk_alerts or fallback["risk_alerts"],
        "interpretation": interpretation.strip(),
    }


def _facts_for_prompt(
    quotes: list[dict], sectors: list[dict], breadth: dict, movers: dict, news: list[dict], market_status: dict
) -> dict:
    return {
        "generated_at_ist": _now_ist().isoformat(),
        "market_status": market_status,
        "indices": [
            {
                "symbol": q.get("symbol"),
                "name": q.get("name"),
                "price": q.get("price"),
                "change": q.get("change"),
                "change_pct": q.get("change_pct"),
                "timestamp": q.get("timestamp"),
                "data_status": q.get("data_status"),
            }
            for q in quotes
            if _usable_quote(q)
        ],
        "sectors": [
            {
                "sector": s.get("sector"),
                "change_pct": s.get("change_pct"),
                "status": s.get("status"),
            }
            for s in sectors
        ],
        "breadth": breadth,
        "gainers": movers.get("gainers", [])[:5],
        "losers": movers.get("losers", [])[:5],
        "most_active": movers.get("most_active", [])[:5],
        "news": [n.get("title") for n in news[:5]],
    }


@router.post("/ai/briefing")
async def ai_market_briefing(payload: Optional[BriefingRequest] = None):
    """Structured AI market briefing.

    Facts are fetched first and sent to the LLM.  The LLM only explains those
    facts.  When the LLM is not configured or returns unusable JSON, a
    clearly-labelled rule-based briefing built from the same facts is returned
    rather than an invented narrative.
    """
    mode = (payload.mode if payload else "concise").lower()
    force = bool(payload.force) if payload else False
    if mode not in BRIEFING_MODES:
        raise HTTPException(status_code=400, detail=f"Unsupported briefing mode: {mode}")

    cached = _BRIEFING_CACHE.get(mode)
    if not force and cached and time.monotonic() - cached[0] < _BRIEFING_CACHE_TTL:
        response = dict(cached[1])
        response["cached"] = True
        return response

    market_status = get_market_status()
    try:
        quotes, sectors, breadth, movers, news = await asyncio.gather(
            fetch_multiple_index_quotes(list(INDEX_TICKERS.keys())),
            fetch_sector_performance(),
            fetch_market_breadth(),
            fetch_gainers_losers_active(5),
            fetch_market_news(5),
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {exc}") from exc

    quotes = [_decorate_quote(q, market_status) if _usable_quote(q) else q for q in quotes]
    facts = _facts_for_prompt(quotes, sectors, breadth, movers, news, market_status)
    fallback = _rule_briefing(
        quotes, sectors, breadth, movers, news, market_status, mode
    )

    usable_indices = sum(1 for q in quotes if _usable_quote(q))
    has_any_facts = usable_indices > 0 or bool(breadth.get("total")) or any(
        s.get("status") == "ok" for s in sectors
    )

    briefing = fallback
    generated_by = "rules"
    ai_available = False
    note = None

    if has_any_facts:
        mode_instruction = {
            "concise": "Keep it concise: 3-5 observations, short interpretation.",
            "detailed": "Provide a more detailed sector and volatility read; up to 5 observations.",
            "explain": "Focus on explaining *why* the observed moves may be happening, using only the facts.",
        }[mode]
        try:
            raw = await chat_completion(
                [
                    {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Analysis mode: {mode}. {mode_instruction}\n\n"
                            "FACT SHEET (JSON):\n"
                            + json.dumps(facts, ensure_ascii=False, default=str)
                        ),
                    },
                ]
            )
            parsed = _extract_json_object(raw)
            if parsed:
                known_sectors = {
                    str(s.get("sector")): float(s.get("change_pct"))
                    for s in sectors
                    if s.get("status") == "ok" and s.get("change_pct") is not None
                }
                briefing = _merge_llm_briefing(parsed, fallback, known_sectors)
                generated_by = "llm"
                ai_available = True
            else:
                note = "The AI response was not valid JSON; a factual summary is shown instead."
        except LLMNotConfiguredError:
            note = (
                "The LLM is not configured, so this briefing is a rule-based summary of the "
                "available market facts."
            )
        except Exception as exc:  # network / provider error
            note = f"The AI provider failed ({exc}); a factual summary is shown instead."
    else:
        note = "Insufficient market data was available to generate a briefing."

    response = {
        "briefing": briefing,
        "facts": {
            "indices": facts["indices"],
            "breadth": breadth,
            "sectors": sectors,
        },
        "mode": mode,
        "generated_by": generated_by,
        "ai_available": ai_available,
        "note": note,
        "data_sources": [
            "Yahoo Finance via yfinance (indices, stocks, sectors, breadth)",
            (
                "Yahoo Finance news / Google News RSS (headlines)"
                if news
                else "No news provider returned headlines in this cycle"
            ),
        ],
        "timestamp": int(time.time()),
        "timestamp_ist": _now_ist().isoformat(),
        "market_status": market_status,
        "disclaimer": (
            "Educational market analysis only. Not investment advice, not a buy/sell signal, "
            "and not a guarantee of future direction."
        ),
        "cached": False,
    }
    _BRIEFING_CACHE[mode] = (time.monotonic(), response)
    return response


# ============================================================
# Algorithmic Trading Simulation — monitor over the paper engine
# ============================================================


def _last_close_for(strategy: Optional[Strategy], deployment: PaperDeployment) -> Optional[float]:
    """Latest cached bar close the engine has processed, if available."""
    if strategy is None or not deployment.last_bar_date:
        return None
    try:
        bars = load_bars((strategy.market or "NIFTY50"))
    except PaperBarsError:
        return None
    match = next((b for b in bars if b["date"] == deployment.last_bar_date), None)
    return float(match["close"]) if match else None


def _sharpe_from_snapshots(snapshots: list[PaperEquitySnapshot]) -> Optional[float]:
    """Annualised Sharpe from per-bar equity snapshots (no risk-free rate)."""
    equities = [float(s.equity) for s in snapshots if s.equity is not None]
    if len(equities) < 3:
        return None
    returns = []
    for previous, current in zip(equities, equities[1:]):
        if previous:
            returns.append(current / previous - 1.0)
    if len(returns) < 2:
        return None
    mean = statistics.fmean(returns)
    stdev = statistics.stdev(returns)
    if stdev == 0:
        return None
    return round((mean / stdev) * math.sqrt(252), 2)


@router.get("/simulation")
async def simulation_summary(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Truthful monitor of the existing paper-trading deployments.

    This endpoint does not run a second engine.  It aggregates the same
    deployment, position, trade and equity-snapshot records the Paper Trading
    page uses, and computes win rate / Sharpe from those records only.
    """
    strategy_ids = _get_user_strategy_ids(db, user.id)
    market_status = get_market_status()

    available_strategies = []
    if strategy_ids:
        approved = (
            db.query(Strategy)
            .filter(
                Strategy.id.in_(strategy_ids),
                Strategy.status == StrategyStatus.approved,
            )
            .order_by(desc(Strategy.created_at))
            .all()
        )
        available_strategies = [
            {
                "id": s.id,
                "name": s.name,
                "market": s.market or "NIFTY50",
                "status": s.status.value,
            }
            for s in approved
        ]

    deployments = []
    if strategy_ids:
        deployments = (
            db.query(PaperDeployment)
            .filter(PaperDeployment.strategy_id.in_(strategy_ids))
            .all()
        )

    active = [d for d in deployments if d.status == DeploymentStatus.active]
    chosen = None
    if active:
        chosen = max(active, key=lambda d: d.deployed_at or datetime.min)
    elif deployments:
        chosen = max(deployments, key=lambda d: d.deployed_at or datetime.min)

    base = {
        "market_status": market_status,
        "available_strategies": available_strategies,
        "has_any_deployment": bool(deployments),
        "source": "paper-trading engine (virtual)",
        "timestamp": int(time.time()),
    }

    if chosen is None:
        return {
            **base,
            "status": "not_started",
            "deployment": None,
            "account": None,
            "win_rate": None,
            "total_trades": 0,
            "sharpe": None,
        }

    strategy = db.query(Strategy).filter(Strategy.id == chosen.strategy_id).first()
    positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.deployment_id == chosen.id)
        .all()
    )
    trades = (
        db.query(PaperTrade)
        .filter(PaperTrade.deployment_id == chosen.id)
        .order_by(desc(PaperTrade.created_at))
        .all()
    )
    snapshots = (
        db.query(PaperEquitySnapshot)
        .filter(PaperEquitySnapshot.deployment_id == chosen.id)
        .order_by(PaperEquitySnapshot.bar_date.asc())
        .all()
    )

    last_close = _last_close_for(strategy, chosen)
    account = account_snapshot(chosen, positions, len(trades), last_close)

    total_trades = len(trades)
    winning = sum(1 for t in trades if (t.pnl_net or 0) > 0)
    win_rate = round((winning / total_trades) * 100, 2) if total_trades else None

    if chosen.status == DeploymentStatus.stopped:
        status = "stopped"
    elif chosen.last_error:
        status = "waiting_for_data"
    else:
        status = "running"

    return {
        **base,
        "status": status,
        "deployment": {
            "id": chosen.id,
            "strategy_id": chosen.strategy_id,
            "strategy_name": strategy.name if strategy else None,
            "market": (strategy.market if strategy else None) or "NIFTY50",
            "status": chosen.status.value,
            "deployed_at": chosen.deployed_at.isoformat() if chosen.deployed_at else None,
            "stopped_at": chosen.stopped_at.isoformat() if chosen.stopped_at else None,
            "stop_reason": chosen.stop_reason,
            "last_bar_date": chosen.last_bar_date,
            "last_error": chosen.last_error,
        },
        "account": account,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "sharpe": _sharpe_from_snapshots(snapshots),
        "equity_points": len(snapshots),
        "open_positions": len(positions),
    }


# ============================================================
# Trading Performance (user-scoped)
# ============================================================


@router.get("/performance/summary")
async def performance_summary(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Trading performance summary for the user."""
    strategy_ids = _get_user_strategy_ids(db, user.id)

    if not strategy_ids:
        return {
            "total_pnl": 0,
            "realized_pnl": 0,
            "unrealized_pnl": 0,
            "win_rate": 0,
            "total_trades": 0,
            "active_deployments": 0,
            "profit_factor": 0,
            "max_drawdown": 0,
            "equity_curve": [],
        }

    deployment_ids = _get_user_deployment_ids(db, strategy_ids)

    active_deployments = (
        db.query(PaperDeployment)
        .filter(
            PaperDeployment.strategy_id.in_(strategy_ids),
            PaperDeployment.status == DeploymentStatus.active,
        )
        .all()
    )

    all_trades = (
        db.query(PaperTrade)
        .filter(PaperTrade.deployment_id.in_(deployment_ids))
        .all()
    )

    total_realized = sum((t.pnl_net or 0) for t in all_trades)
    winning_trades = [t for t in all_trades if (t.pnl_net or 0) > 0]
    losing_trades = [t for t in all_trades if (t.pnl_net or 0) < 0]

    total_trades = len(all_trades)
    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

    gross_profit = sum((t.pnl_net or 0) for t in winning_trades)
    gross_loss = abs(sum((t.pnl_net or 0) for t in losing_trades))
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else (float("inf") if gross_profit > 0 else 0)
    )

    equity_snapshots = (
        db.query(PaperEquitySnapshot)
        .filter(PaperEquitySnapshot.deployment_id.in_(deployment_ids))
        .order_by(PaperEquitySnapshot.bar_date)
        .all()
    )

    equity_curve = [
        {"date": s.bar_date, "equity": float(s.equity)} for s in equity_snapshots
    ]

    unrealized = 0.0
    for dep in active_deployments:
        positions = (
            db.query(PaperPosition)
            .filter(PaperPosition.deployment_id == dep.id)
            .all()
        )
        if not positions:
            continue
        strategy = db.query(Strategy).filter(Strategy.id == dep.strategy_id).first()
        last_close = _last_close_for(strategy, dep)
        if last_close is None:
            continue
        unrealized += sum(
            (last_close - float(pos.avg_price)) * int(pos.quantity) for pos in positions
        )

    return {
        "total_pnl": round(total_realized + unrealized, 2),
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(unrealized, 2),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "active_deployments": len(active_deployments),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
        "max_drawdown": 0,
        "equity_curve": equity_curve,
    }


# ============================================================
# My Strategies
# ============================================================


@router.get("/strategies")
async def dashboard_strategies(
    status_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Get user's strategies with enhanced info for dashboard."""
    strategy_ids = _get_user_strategy_ids(db, user.id)

    if not strategy_ids:
        return {"strategies": [], "count": 0}

    query = db.query(Strategy).filter(Strategy.id.in_(strategy_ids))
    if status_filter:
        query = query.filter(Strategy.status == status_filter)
    strategies = query.order_by(desc(Strategy.created_at)).all()

    result = []
    for s in strategies:
        latest_bt = (
            db.query(BacktestResult)
            .filter(BacktestResult.strategy_id == s.id)
            .order_by(desc(BacktestResult.created_at))
            .first()
        )
        active_dep = (
            db.query(PaperDeployment)
            .filter(
                PaperDeployment.strategy_id == s.id,
                PaperDeployment.status == DeploymentStatus.active,
            )
            .first()
        )
        result.append(
            {
                "strategy_id": s.id,
                "name": s.name,
                "description": s.description,
                "market": s.market,
                "status": s.status.value,
                "status_note": s.status_note,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "latest_backtest": {
                    "total_return_pct": latest_bt.total_return_pct,
                    "win_rate_pct": latest_bt.win_rate_pct,
                    "max_drawdown_pct": latest_bt.max_drawdown_pct,
                    "num_trades": latest_bt.num_trades,
                    "created_at": latest_bt.created_at.isoformat() if latest_bt.created_at else None,
                }
                if latest_bt
                else None,
                "deployment": {
                    "id": active_dep.id,
                    "status": active_dep.status.value,
                    "equity": active_dep.cash_balance if active_dep.cash_balance is not None else active_dep.cash,
                    "realized_pnl": active_dep.realized_pnl,
                    "deployed_at": active_dep.deployed_at.isoformat() if active_dep.deployed_at else None,
                }
                if active_dep
                else None,
            }
        )
    return {"strategies": result, "count": len(result)}


# ============================================================
# Paper Trading Portfolio
# ============================================================


@router.get("/paper/portfolio")
async def paper_portfolio(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Consolidated paper-trading portfolio across the user's deployments."""
    strategy_ids = _get_user_strategy_ids(db, user.id)
    deployment_ids = _get_user_deployment_ids(db, strategy_ids)

    active_deps = (
        db.query(PaperDeployment)
        .filter(
            PaperDeployment.strategy_id.in_(strategy_ids),
            PaperDeployment.status == DeploymentStatus.active,
        )
        .all()
        if strategy_ids
        else []
    )

    if not active_deps:
        return {
            "initial_capital": 0,
            "available_balance": 0,
            "invested_capital": 0,
            "realized_pnl": 0,
            "unrealized_pnl": 0,
            "open_positions": 0,
            "active_deployments": 0,
            "recent_trades": [],
            "deployments": [],
        }

    total_cash = sum(float(d.cash) for d in active_deps)
    total_realized = sum(float(d.realized_pnl or 0) for d in active_deps)
    total_cash_balance = sum(
        float(d.cash_balance) if d.cash_balance is not None else float(d.cash)
        for d in active_deps
    )

    all_positions = []
    unrealized = 0.0
    for dep in active_deps:
        positions = (
            db.query(PaperPosition)
            .filter(PaperPosition.deployment_id == dep.id)
            .all()
        )
        strategy = db.query(Strategy).filter(Strategy.id == dep.strategy_id).first()
        last_close = _last_close_for(strategy, dep)
        for pos in positions:
            market_value = (
                last_close * int(pos.quantity) if last_close is not None else None
            )
            position_unrealized = (
                (last_close - float(pos.avg_price)) * int(pos.quantity)
                if last_close is not None
                else None
            )
            if position_unrealized is not None:
                unrealized += position_unrealized
            all_positions.append(
                {
                    "deployment_id": dep.id,
                    "strategy_id": dep.strategy_id,
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_price": float(pos.avg_price),
                    "entry_date": pos.entry_date,
                    "market_value": market_value,
                    "unrealized_pnl": position_unrealized,
                }
            )

    recent_trades = (
        db.query(PaperTrade)
        .filter(PaperTrade.deployment_id.in_(deployment_ids))
        .order_by(desc(PaperTrade.created_at))
        .limit(20)
        .all()
    )
    trades_list = [
        {
            "id": t.id,
            "deployment_id": t.deployment_id,
            "symbol": t.symbol,
            "quantity": t.quantity,
            "entry_price": float(t.entry_price),
            "exit_price": float(t.exit_price),
            "pnl": float(t.pnl),
            "pnl_net": float(t.pnl_net),
            "entry_date": t.entry_date,
            "exit_date": t.exit_date,
            "status": "closed",
        }
        for t in recent_trades
    ]

    deployments_list = [
        {
            "id": d.id,
            "strategy_id": d.strategy_id,
            "cash": float(d.cash),
            "cash_balance": float(d.cash_balance) if d.cash_balance is not None else float(d.cash),
            "realized_pnl": float(d.realized_pnl or 0),
            "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
        }
        for d in active_deps
    ]

    invested = sum(
        float(p["avg_price"]) * int(p["quantity"]) for p in all_positions
    )

    return {
        "initial_capital": round(total_cash, 2),
        "available_balance": round(total_cash_balance, 2),
        "invested_capital": round(invested, 2),
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(unrealized, 2),
        "open_positions": len(all_positions),
        "active_deployments": len(active_deps),
        "recent_trades": trades_list,
        "open_positions_detail": all_positions,
        "deployments": deployments_list,
    }


# ============================================================
# Recent Activity
# ============================================================


@router.get("/activity/recent")
async def recent_activity(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Get recent activity for the user."""
    strategy_ids = _get_user_strategy_ids(db, user.id)
    deployment_ids = _get_user_deployment_ids(db, strategy_ids)
    conversation_ids = _get_user_conversation_ids(db, user.id)

    activities = []

    recent_strategies = (
        db.query(Strategy)
        .filter(Strategy.id.in_(strategy_ids))
        .order_by(desc(Strategy.created_at))
        .limit(limit)
        .all()
    )
    for s in recent_strategies:
        activities.append(
            {
                "type": "strategy_created",
                "title": f"Strategy created: {s.name}",
                "description": s.description[:100] if s.description else "",
                "timestamp": s.created_at.isoformat() if s.created_at else None,
                "ref_id": s.id,
                "ref_type": "strategy",
            }
        )

    recent_backtests = (
        db.query(BacktestResult)
        .filter(BacktestResult.strategy_id.in_(strategy_ids))
        .order_by(desc(BacktestResult.created_at))
        .limit(limit)
        .all()
    )
    for bt in recent_backtests:
        ret_pct = bt.total_return_pct if bt.total_return_pct is not None else 0.0
        wr_pct = bt.win_rate_pct if bt.win_rate_pct is not None else 0.0
        activities.append(
            {
                "type": "backtest_completed",
                "title": f"Backtest completed: {ret_pct:.2f}% return",
                "description": f"Win rate: {wr_pct:.1f}%, Trades: {bt.num_trades}",
                "timestamp": bt.created_at.isoformat() if bt.created_at else None,
                "ref_id": bt.id,
                "ref_type": "backtest",
            }
        )

    recent_deps = (
        db.query(PaperDeployment)
        .filter(PaperDeployment.id.in_(deployment_ids))
        .order_by(desc(PaperDeployment.deployed_at))
        .limit(limit)
        .all()
    )
    for dep in recent_deps:
        activities.append(
            {
                "type": "deployment_started",
                "title": "Paper deployment started",
                "description": f"Strategy: {dep.strategy_id}, Cash: ₹{dep.cash:,.0f}",
                "timestamp": dep.deployed_at.isoformat() if dep.deployed_at else None,
                "ref_id": dep.id,
                "ref_type": "deployment",
            }
        )

    recent_trades = (
        db.query(PaperTrade)
        .filter(PaperTrade.deployment_id.in_(deployment_ids))
        .order_by(desc(PaperTrade.created_at))
        .limit(limit)
        .all()
    )
    for t in recent_trades:
        activities.append(
            {
                "type": "paper_trade",
                "title": f"Paper trade: {t.symbol} {t.quantity} @ ₹{t.entry_price:.2f}",
                "description": f"P&L: ₹{t.pnl_net:.2f}",
                "timestamp": t.created_at.isoformat() if t.created_at else None,
                "ref_id": t.id,
                "ref_type": "trade",
            }
        )

    recent_convs = (
        db.query(Conversation)
        .filter(Conversation.id.in_(conversation_ids))
        .order_by(desc(Conversation.created_at))
        .limit(limit)
        .all()
    )
    for conv in recent_convs:
        activities.append(
            {
                "type": "conversation_created",
                "title": f"New conversation: {conv.title}",
                "description": "",
                "timestamp": conv.created_at.isoformat() if conv.created_at else None,
                "ref_id": conv.id,
                "ref_type": "conversation",
            }
        )

    activities.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return {"activities": activities[:limit]}

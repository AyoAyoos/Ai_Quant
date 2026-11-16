"""Unit tests for the dashboard market helpers.

These tests do not touch the network. They cover the failure modes that made
the original Market Pulse render zeros: a trailing all-NaN Yahoo row, a closed
session being mislabeled as live, and malformed LLM/news payloads.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.routers.dashboard import (
    _derive_data_status,
    _derive_sentiment,
    _extract_json_object,
    _merge_llm_briefing,
    _rule_briefing,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_sma,
)
from app.services.market_data_extended import (
    _is_near_duplicate_title,
    _looks_like_market_headline,
    _normalize_frame,
    _normalize_title,
    _parse_news_item,
    _row_snapshot,
    get_market_status,
)

IST = ZoneInfo("Asia/Kolkata")


# --------------------------------------------------------------------------- #
# Provider frame cleaning
# --------------------------------------------------------------------------- #


def _frame(rows):
    index = pd.to_datetime([r[0] for r in rows], utc=True).tz_convert(IST)
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=index,
    )


def test_normalize_frame_drops_trailing_nan_row():
    frame = _frame(
        [
            ("2026-11-06 00:00", 100.0, 105.0, 99.0, 104.0, 1000),
            ("2026-11-09 00:00", float("nan"), float("nan"), float("nan"), float("nan"), 0),
        ]
    )
    cleaned = _normalize_frame(frame)
    assert cleaned is not None
    assert len(cleaned) == 1
    snapshot = _row_snapshot(cleaned)
    assert snapshot is not None
    assert snapshot["price"] == 104.0
    # A single usable row means the previous close is the same row, never NaN.
    assert snapshot["change"] == 0.0
    assert snapshot["change_pct"] == 0.0


def test_row_snapshot_uses_previous_valid_close():
    frame = _frame(
        [
            ("2026-11-06 00:00", 100.0, 105.0, 99.0, 100.0, 1000),
            ("2026-11-09 00:00", 101.0, 110.0, 100.0, 110.0, 2500),
            ("2026-11-10 00:00", float("nan"), float("nan"), float("nan"), float("nan"), 0),
        ]
    )
    snapshot = _row_snapshot(_normalize_frame(frame))
    assert snapshot is not None
    assert snapshot["price"] == 110.0
    assert snapshot["change"] == 10.0
    assert snapshot["change_pct"] == 10.0
    assert snapshot["volume"] == 2500


# --------------------------------------------------------------------------- #
# Market session / data freshness
# --------------------------------------------------------------------------- #


def test_market_status_pre_open_is_only_the_0915_window():
    pre_open = get_market_status(datetime(2026, 11, 11, 9, 5, tzinfo=IST))
    assert pre_open["status"] == "PRE-OPEN"

    early_morning = get_market_status(datetime(2026, 11, 11, 2, 0, tzinfo=IST))
    assert early_morning["status"] == "CLOSED"
    assert "pre-open" in early_morning["reason"].lower()


def test_market_status_open_and_closed():
    open_status = get_market_status(datetime(2026, 11, 11, 10, 0, tzinfo=IST))
    assert open_status["status"] == "OPEN"
    assert open_status["is_open"] is True

    after = get_market_status(datetime(2026, 11, 11, 16, 0, tzinfo=IST))
    assert after["status"] == "CLOSED"

    weekend = get_market_status(datetime(2026, 11, 14, 11, 0, tzinfo=IST))
    assert weekend["status"] == "CLOSED"
    assert "weekend" in weekend["reason"].lower()


def test_market_status_marks_nse_holidays_and_skips_them_for_next_open():
    holiday = get_market_status(datetime(2026, 11, 10, 10, 0, tzinfo=IST))
    assert holiday["status"] == "CLOSED"
    assert holiday["is_holiday"] is True
    assert "diwali" in holiday["reason"].lower()
    # 10 Nov 2026 is Diwali-Balipratipada; the next session is 11 Nov.
    assert holiday["next_open"].startswith("2026-11-11T09:15")

    before_open = get_market_status(datetime(2026, 11, 10, 2, 0, tzinfo=IST))
    assert before_open["status"] == "CLOSED"
    assert "holiday" in before_open["reason"].lower()
    assert before_open["next_open"].startswith("2026-11-11T09:15")


def test_closed_market_data_is_never_labelled_live():
    import time

    now = int(time.time())
    assert _derive_data_status(now, {"status": "CLOSED"}) == "HISTORICAL"
    assert _derive_data_status(now, {"status": "OPEN"}) == "LIVE"
    assert _derive_data_status(now - 10_000, {"status": "OPEN"}) == "STALE"
    assert _derive_data_status(None, {"status": "OPEN"}) == "UNAVAILABLE"


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #


def test_indicator_lengths_match_input():
    prices = [float(i) for i in range(1, 61)]
    assert len(compute_sma(prices, 20)) == len(prices)
    assert len(compute_ema(prices, 9)) == len(prices)
    assert len(compute_rsi(prices, 14)) == len(prices)
    macd = compute_macd(prices)
    assert len(macd["macd"]) == len(prices)
    assert len(macd["signal"]) == len(prices)
    assert len(macd["histogram"]) == len(prices)


def test_ema_seeds_from_sma_and_rsi_stays_in_range():
    prices = [10.0, 11.0, 10.5, 12.0, 13.0, 12.5, 14.0, 15.0, 14.5, 16.0, 17.0, 16.5, 18.0, 19.0, 18.5]
    ema = compute_ema(prices, 5)
    assert ema[:4] == [None, None, None, None]
    assert ema[4] == sum(prices[:5]) / 5

    rsi = compute_rsi(prices, 14)
    values = [v for v in rsi if v is not None]
    assert values
    assert all(0.0 <= v <= 100.0 for v in values)


# --------------------------------------------------------------------------- #
# Briefing helpers
# --------------------------------------------------------------------------- #


def test_extract_json_object_handles_markdown_fences():
    assert _extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json_object("prefix {\"sentiment\": \"Bullish\"} suffix")["sentiment"] == "Bullish"
    assert _extract_json_object("not json") is None


def test_sentiment_is_conservative_with_missing_data():
    assert _derive_sentiment([]) == "Insufficient Data"
    assert _derive_sentiment([0.05]) == "Sideways"
    assert _derive_sentiment([0.8, 0.6, 0.5]) == "Bullish"
    assert _derive_sentiment([-0.8, -0.6, -0.5]) == "Bearish"
    assert _derive_sentiment([0.9, -0.9, 0.1]) == "Mixed"


def test_llm_merge_rejects_invented_sentiment_and_keeps_fact_fallback():
    fallback = {
        "sentiment": "Insufficient Data",
        "market_direction": "Index data is unavailable.",
        "sector_analysis": {"strong": [], "weak": [], "unusual": []},
        "volatility_analysis": "VIX unavailable.",
        "volatility_level": "Unavailable",
        "observations": ["No quote data."],
        "risk_alerts": ["Market data unavailable."],
        "interpretation": "No directional conclusion is drawn.",
    }
    merged = _merge_llm_briefing({"sentiment": "Definitely Bullish"}, fallback)
    assert merged["sentiment"] == "Insufficient Data"
    assert merged["observations"] == ["No quote data."]


def test_llm_merge_rejects_wrong_sign_or_invented_sector_numbers():
    fallback = {
        "sentiment": "Mixed",
        "market_direction": "Facts.",
        "sector_analysis": {
            "strong": [{"sector": "Banking", "change_pct": 1.25}],
            "weak": [{"sector": "Metals", "change_pct": -0.75}],
            "unusual": [],
        },
        "volatility_analysis": "VIX available.",
        "volatility_level": "Moderate",
        "observations": ["Fact."],
        "risk_alerts": ["Risk."],
        "interpretation": "Interpretation.",
    }
    known = {"Banking": 1.25, "Information Technology": 0.42, "Metals": -0.75}
    merged = _merge_llm_briefing(
        {
            "sector_analysis": {
                "strong": [
                    {"sector": "Banking", "change_pct": 999.0},
                    {"sector": "Invented Sector", "change_pct": 4.0},
                ],
                "weak": [{"sector": "Information Technology", "change_pct": 0.42}],
                "unusual": [],
            }
        },
        fallback,
        known,
    )
    assert merged["sector_analysis"]["strong"] == [
        {"sector": "Banking", "change_pct": 1.25}
    ]
    # A positive sector claimed as "weak" is rejected, falling back to real weak facts.
    assert merged["sector_analysis"]["weak"] == [{"sector": "Metals", "change_pct": -0.75}]


def test_rule_briefing_does_not_invent_prices_when_data_missing():
    briefing = _rule_briefing(
        quotes=[],
        sectors=[],
        breadth={"status": "unavailable", "total": 0},
        movers={"gainers": [], "losers": [], "most_active": []},
        news=[],
        market_status={"status": "CLOSED"},
        mode="concise",
    )
    assert briefing["sentiment"] == "Insufficient Data"
    assert "unavailable" in briefing["market_direction"].lower()
    assert any("unavailable" in alert.lower() for alert in briefing["risk_alerts"])
    assert "not a forecast" in briefing["interpretation"].lower()


# --------------------------------------------------------------------------- #
# News parsing
# --------------------------------------------------------------------------- #


def test_parse_news_item_handles_nested_yfinance_shape():
    item = {
        "id": "abc",
        "content": {
            "title": "RBI holds repo rate",
            "summary": "The central bank kept rates unchanged.",
            "pubDate": "2026-11-10T08:30:00Z",
            "provider": {"displayName": "Example Wire"},
            "canonicalUrl": {"url": "https://example.com/rbi"},
            "relatedTickers": ["HDFCBANK.NS"],
        },
    }
    parsed = _parse_news_item(item, retrieved_at=1_700_000_000)
    assert parsed is not None
    assert parsed["title"] == "RBI holds repo rate"
    assert parsed["source"] == "Example Wire"
    assert parsed["url"] == "https://example.com/rbi"
    assert parsed["published_at"] == int(datetime(2026, 11, 10, 8, 30, tzinfo=ZoneInfo("UTC")).timestamp())
    assert parsed["retrieved_at"] == 1_700_000_000
    assert parsed["related_symbols"] == ["HDFCBANK.NS"]


def test_news_headline_filter_rejects_generic_non_market_items():
    assert _looks_like_market_headline("Sensex gains 107 points as bank stocks rally")
    assert _looks_like_market_headline("RBI holds repo rate at 5.5%")
    assert not _looks_like_market_headline(
        "Asia's Premier News Agency - India News, Business & Political"
    )
    assert not _looks_like_market_headline("Watch live: evening bulletin")


def test_news_near_duplicate_titles_are_collapsed():
    a = "RBI extends Abhyudaya Bank supersession by another year"
    b = "RBI extends supersession of Abhyudaya Co-operative Bank board by one year"
    same_story = "Nifty 50 trails S&P 500 by 3.1 points over 10 years"
    other = "Sensex gains 107 points, Nifty reclaims 25,000 amid easing oil prices"
    assert _is_near_duplicate_title(_normalize_title(a), _normalize_title(b))
    assert _is_near_duplicate_title(
        _normalize_title("Nifty 50 Trails S&P 500 by 3.1 Points Over Decade"),
        _normalize_title(same_story),
    )
    assert not _is_near_duplicate_title(
        _normalize_title(other),
        _normalize_title("Sensex, Nifty close higher as banking stocks lead gains"),
    )

"""Route-level tests for the dashboard market endpoints.

The market provider is patched in every test: these tests verify the API
contract, the freshness labels and the no-invention behaviour without making
network calls.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import dashboard as dashboard_router
from app.services.llm_errors import LLMNotConfiguredError


@pytest.fixture()
def client():
    return TestClient(app)


def _quote(symbol, name, price, change, change_pct):
    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "open": price - change,
        "high": price + 10,
        "low": price - 20,
        "previous_close": price - change,
        "volume": 1000,
        "timestamp": int(time.time()),
        "source": "yfinance",
        "status": "ok",
    }


def _patch_market(monkeypatch, *, phase="CLOSED"):
    market_status = {
        "status": phase,
        "reason": "Test session",
        "is_open": phase == "OPEN",
        "session": "NSE cash market",
        "timezone": "Asia/Kolkata",
        "as_of": "2026-11-10T10:00:00+05:30",
        "next_open_label": "Tue 10 Nov, 09:15 IST",
    }

    async def quotes(symbols):
        return [
            _quote("NIFTY50", "NIFTY 50", 25000.0, 100.0, 0.4),
            _quote("BANKNIFTY", "BANK NIFTY", 60000.0, -200.0, -0.33),
            {
                "symbol": "SENSEX",
                "name": "SENSEX",
                "status": "unavailable",
                "error": "provider returned no rows",
            },
        ]

    async def movers(limit):
        return {
            "gainers": [
                {
                    "symbol": "SBIN",
                    "name": "State Bank of India",
                    "price": 800.0,
                    "change": 12.0,
                    "change_pct": 1.5,
                    "volume": 5000000,
                }
            ],
            "losers": [],
            "most_active": [
                {
                    "symbol": "HDFCBANK",
                    "name": "HDFC Bank",
                    "price": 1700.0,
                    "change": -4.0,
                    "change_pct": -0.2,
                    "volume": 9000000,
                }
            ],
            "universe_size": 44,
            "status": "ok",
        }

    async def sectors():
        return [
            {"sector": "Banking", "status": "ok", "change_pct": 1.25},
            {"sector": "Metals", "status": "ok", "change_pct": -0.75},
            {"sector": "Realty", "status": "unavailable", "change_pct": None},
        ]

    async def breadth():
        return {
            "advancing": 20,
            "declining": 24,
            "unchanged": 0,
            "total": 44,
            "advance_decline_ratio": 0.83,
            "advance_decline_ratio_display": "0.83",
            "universe_size": 44,
            "status": "ok",
        }

    async def news(limit):
        return [
            {
                "title": "RBI holds repo rate",
                "summary": "The central bank kept rates unchanged.",
                "source": "Example Wire",
                "url": "https://example.com/rbi",
                "published_at": 1794247200,
                "retrieved_at": int(time.time()),
                "related_symbols": ["HDFCBANK.NS"],
                "related_sectors": ["Banking"],
                "origin": "Google News RSS",
            }
        ][:limit]

    async def chart(symbol, timeframe, limit):
        now = int(time.time())
        return [
            {
                "time": now - (limit - i) * 86400,
                "open": 100.0 + i,
                "high": 102.0 + i,
                "low": 99.0 + i,
                "close": 101.0 + i,
                "volume": 1000 + i,
            }
            for i in range(limit)
        ]

    monkeypatch.setattr(dashboard_router, "get_market_status", lambda: dict(market_status))
    monkeypatch.setattr(dashboard_router, "fetch_multiple_index_quotes", quotes)
    monkeypatch.setattr(dashboard_router, "fetch_gainers_losers_active", movers)
    monkeypatch.setattr(dashboard_router, "fetch_sector_performance", sectors)
    monkeypatch.setattr(dashboard_router, "fetch_market_breadth", breadth)
    monkeypatch.setattr(dashboard_router, "fetch_market_news", news)
    monkeypatch.setattr(dashboard_router, "fetch_chart_history", chart)
    return market_status


def test_overview_keeps_three_headline_indices_and_marks_unavailable(client, monkeypatch):
    _patch_market(monkeypatch)

    response = client.get("/dashboard/market/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["market_status"]["status"] == "CLOSED"
    by_symbol = {index["symbol"]: index for index in body["indices"]}

    assert by_symbol["NIFTY50"]["data_status"] == "HISTORICAL"
    assert by_symbol["NIFTY50"]["market_status"] == "CLOSED"
    assert by_symbol["BANKNIFTY"]["data_status"] == "HISTORICAL"

    sensex = by_symbol["SENSEX"]
    assert sensex["data_status"] == "UNAVAILABLE"
    assert "price" not in sensex
    assert sensex["error"] == "provider returned no rows"


def test_chart_returns_aligned_indicators(client, monkeypatch):
    _patch_market(monkeypatch)

    response = client.get("/dashboard/market/chart/NIFTY50?timeframe=1d&limit=60")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 60
    assert body["data_status"] == "HISTORICAL"
    assert body["market_status"]["status"] == "CLOSED"
    for key in (
        "ema9",
        "ema21",
        "ema50",
        "ema200",
        "sma20",
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
    ):
        assert len(body["indicators"][key]) == 60


def test_chart_rejects_unknown_symbol(client, monkeypatch):
    _patch_market(monkeypatch)
    response = client.get("/dashboard/market/chart/NOT_AN_INDEX")
    assert response.status_code == 404


def test_pulse_returns_movers_sectors_and_breadth(client, monkeypatch):
    _patch_market(monkeypatch)

    response = client.get("/dashboard/market/pulse")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["universe_size"] == 44
    assert body["gainers"][0]["symbol"] == "SBIN"
    assert body["most_active"][0]["symbol"] == "HDFCBANK"
    assert body["sectors"][2]["status"] == "unavailable"
    assert body["breadth"]["advancing"] == 20
    assert body["breadth"]["declining"] == 24


def test_news_keeps_publication_and_retrieval_time_and_origin(client, monkeypatch):
    _patch_market(monkeypatch)

    response = client.get("/dashboard/market/news?limit=5")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 1
    assert body["source"] == "Google News RSS"
    item = body["news"][0]
    assert item["published_at"] == 1794247200
    assert item["retrieved_at"] > 0
    assert item["related_symbols"] == ["HDFCBANK.NS"]


def test_briefing_falls_back_to_rules_when_llm_is_not_configured(client, monkeypatch):
    _patch_market(monkeypatch)
    dashboard_router._BRIEFING_CACHE.clear()

    async def raise_not_configured(messages):
        raise LLMNotConfiguredError()

    monkeypatch.setattr(dashboard_router, "chat_completion", raise_not_configured)

    response = client.post("/dashboard/ai/briefing", json={"mode": "concise"})
    assert response.status_code == 200
    body = response.json()
    assert body["generated_by"] == "rules"
    assert body["ai_available"] is False
    assert body["briefing"]["sentiment"] in {
        "Bullish",
        "Bearish",
        "Sideways",
        "Mixed",
        "Insufficient Data",
    }
    assert body["briefing"]["observations"]
    assert body["briefing"]["risk_alerts"]
    assert "not investment advice" in body["disclaimer"].lower()
    assert body["cached"] is False

    # The second call is served from the in-process briefing cache.
    second = client.post("/dashboard/ai/briefing", json={"mode": "concise"})
    assert second.status_code == 200
    assert second.json()["cached"] is True

    # Refresh must bypass the cache and rebuild the briefing.
    forced = client.post(
        "/dashboard/ai/briefing", json={"mode": "concise", "force": True}
    )
    assert forced.status_code == 200
    assert forced.json()["cached"] is False

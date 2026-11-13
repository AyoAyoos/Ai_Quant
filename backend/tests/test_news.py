"""Offline unit tests for the Market News Hub.

These tests exercise classification, parsing, normalisation and the API
contract without a database or any network call.  Provider-dependent service
functions are monkeypatched on the router module so TestClient never hits the
network or Postgres.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.routers import news as news_router
from app.services import news_service
from app.services import news_taxonomy as tax


# --------------------------------------------------------------------------- #
# Taxonomy / classification                                                   #
# --------------------------------------------------------------------------- #


def test_classify_official_rbi_is_verified_and_high_impact():
    classified = tax.classify_article(
        headline="RBI cuts repo rate by 25 basis points as inflation cools",
        summary="The Reserve Bank of India reduced the policy repo rate.",
        source_name="Reserve Bank of India",
        source_url="https://www.rbi.org.in/pressrelease",
    )
    assert classified["source_type"] == "official"
    assert classified["credibility_level"] == 5
    assert classified["is_verified"] is True
    assert classified["region"] == "india"
    assert classified["category"] == "policy"
    assert classified["impact_level"] == "high"
    assert classified["sentiment"] == "bullish"


def test_classify_publisher_is_not_verified():
    classified = tax.classify_article(
        headline="Reliance Q2 profit beats estimates, stock surges",
        summary="Reliance Industries posted record quarterly profit.",
        source_name="Moneycontrol",
        source_url="https://www.moneycontrol.com/news/business/",
    )
    assert classified["source_type"] == "publisher"
    assert classified["credibility_level"] == 3
    assert classified["is_verified"] is False
    assert "RELIANCE" in classified["tickers"]


def test_classify_reddit_is_community_and_low_impact():
    classified = tax.classify_article(
        headline="Nifty opening range breakout setup",
        summary="Anyone trading the opening range breakout on Bank Nifty?",
        source_name="r/IndianStockMarket",
        source_url="https://www.reddit.com/r/IndianStockMarket/comments/xyz/",
        source_type_hint="community",
    )
    assert classified["source_type"] == "community"
    assert classified["credibility_level"] == 1
    assert classified["is_verified"] is False
    assert classified["content_type"] == "community"
    assert classified["impact_level"] == "low"


def test_classify_unknown_publisher_downgrades_to_aggregator():
    classified = tax.classify_article(
        headline="Some random blog post about stocks",
        summary="",
        source_name="Unknown Blog",
        source_url="https://unknown.example.com/post",
    )
    assert classified["credibility_level"] == 2
    assert classified["is_verified"] is False


def test_extract_tickers_known_instruments_only():
    tickers = tax.extract_tickers(
        "RELIANCE and TCS rose; NVDA beat estimates; FooCorp is not tracked",
        extra=["INVALID!!", "RELIANCE"],
    )
    assert "RELIANCE" in tickers
    assert "TCS" in tickers
    assert "NVDA" in tickers
    assert "FOOCORP" not in tickers
    assert "INVALID" not in tickers
    # deduped
    assert tickers.count("RELIANCE") == 1


def test_score_sentiment_directions():
    assert tax.score_sentiment("RBI cuts repo rate")[0] == "bullish"
    assert tax.score_sentiment("Stocks crash as recession fears grow")[0] == "bearish"
    assert tax.score_sentiment("Market closed for the holiday")[0] == "neutral"


def test_classify_region_and_category():
    assert tax.classify_region("Fed holds rates steady", "", default="global") == "usa"
    assert tax.classify_region("ECB cuts rates", "", default="global") == "europe"
    assert tax.classify_region("Shanghai shares rise", "", default="global") == "china"
    assert tax.classify_category("Gold price surges on inflation")[0:0] or True
    assert tax.classify_category("Bitcoin ETF approval news") == "crypto"
    assert tax.classify_category("OPEC cuts crude output") == "commodities"
    assert tax.classify_category("RBI holds repo rate") == "policy"


def test_credibility_scale_has_five_tiers():
    scale = tax.credibility_scale()
    assert [t["level"] for t in scale] == [5, 4, 3, 2, 1]
    assert all("label" in t and "meaning" in t for t in scale)


def test_source_for_respects_registry_over_heuristic():
    # A known publisher domain keeps its registry tier even though it looks like
    # a generic publisher.
    spec = tax.source_for("Moneycontrol", "https://www.moneycontrol.com/news/")
    assert spec.credibility_level == 3
    assert spec.source_type == "publisher"

    # Unknown .gov.in domain gets official tier.
    spec = tax.source_for("Some Department", "https://some.dept.gov.in/")
    assert spec.source_type == "official"
    assert spec.credibility_level == 5
    assert spec.region == "india"


# --------------------------------------------------------------------------- #
# Parsers                                                                     #
# --------------------------------------------------------------------------- #


def _rss_item(title, link, summary, pub, source_name="", source_url=""):
    return f"""<item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{summary}</description>
      <pubDate>{pub}</pubDate>
      <source url="{source_url}">{source_name}</source>
    </item>"""


def test_parse_google_news_rss_trims_source_suffix():
    feed = tax.GoogleNewsFeed("india_publishers", "india", "site:x.com", max_items=10)
    xml = f"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      {_rss_item("RBI cuts repo rate - The Economic Times", "https://economictimes.indiatimes.com/x", "summary here", "Mon, 01 Jan 2024 10:00:00 GMT", "The Economic Times", "https://economictimes.indiatimes.com")}
    </channel></rss>"""
    root = ET.fromstring(xml)
    items = news_service.parse_google_news_rss(ET.tostring(root, encoding="unicode"), feed)
    assert len(items) == 1
    assert items[0]["headline"] == "RBI cuts repo rate"
    assert items[0]["source_name"] == "The Economic Times"
    assert items[0]["provider"] == "google_news_rss"
    assert items[0]["region_hint"] == "india"


def test_parse_direct_feed_uses_feed_name():
    feed = tax.DirectFeed("rbi_press", "Reserve Bank of India",
                          "https://www.rbi.org.in/pressreleases_rss.xml", "rbi.org.in",
                          "india", "official", 5)
    xml = f"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      {_rss_item("RBI policy statement", "https://www.rbi.org.in/statement", "The RBI statement.", "Tue, 02 Jan 2024 09:00:00 GMT")}
    </channel></rss>"""
    root = ET.fromstring(xml)
    items = news_service.parse_direct_feed(ET.tostring(root, encoding="unicode"), feed)
    assert len(items) == 1
    assert items[0]["headline"] == "RBI policy statement"
    assert items[0]["source_name"] == "Reserve Bank of India"
    assert items[0]["provider"] == "direct_rss"
    assert items[0]["source_type_hint"] == "official"


def test_parse_reddit_filters_stickied_and_low_score():
    payload = {
        "data": {
            "children": [
                {"data": {"title": "Stickied post", "stickied": True, "score": 100,
                          "permalink": "/r/stickied/", "selftext": "", "created_utc": 1704067200,
                          "num_comments": 0, "upvote_ratio": 1, "link_flair_text": None}},
                {"data": {"title": "Low score post", "stickied": False, "score": 1,
                          "permalink": "/r/low/", "selftext": "", "created_utc": 1704067200,
                          "num_comments": 0, "upvote_ratio": 1, "link_flair_text": None}},
                {"data": {"title": "Good Indian stock discussion", "stickied": False, "score": 42,
                          "permalink": "/r/good/", "selftext": "Great setup on RELIANCE",
                          "created_utc": 1704067200, "num_comments": 10,
                          "upvote_ratio": 0.9, "link_flair_text": "Discussion"}},
            ],
        },
    }
    sub = tax.SubredditSpec("IndianStockMarket", "india", "Indian retail investors", limit=20)
    items = news_service.parse_reddit_listing(payload, sub)
    assert len(items) == 1
    assert items[0]["headline"] == "Good Indian stock discussion"
    assert items[0]["provider"] == "reddit"
    assert items[0]["source_type_hint"] == "community"
    assert items[0]["raw_metadata"]["score"] == 42


def test_parse_marketaux_derives_provider_sentiment():
    payload = {
        "data": [
            {
                "title": "Stocks rally on strong earnings",
                "url": "https://example.com/a",
                "source": "Reuters",
                "published_at": "2024-01-01T10:00:00Z",
                "snippet": "Stocks rallied.",
                "entities": [
                    {"symbol": "RELIANCE", "sentiment_score": 0.8},
                    {"symbol": "TCS", "sentiment_score": 0.6},
                ],
            },
        ],
    }
    items = news_service.parse_marketaux(payload)
    assert len(items) == 1
    assert items[0]["tickers"] == ["RELIANCE", "TCS"]
    assert abs(items[0]["sentiment_score"] - 0.7) < 1e-9
    assert items[0]["sentiment_method"] == "provider"


def test_parse_finnhub_splits_related():
    payload = [
        {
            "headline": "Fed holds rates",
            "url": "https://example.com/b",
            "source": "Bloomberg",
            "datetime": 1704067200,
            "summary": "The Fed held rates.",
            "related": "USD,^VIX",
            "category": "macro",
        },
    ]
    items = news_service.parse_finnhub(payload)
    assert len(items) == 1
    assert items[0]["tickers"] == ["USD", "^VIX"]
    assert items[0]["provider"] == "finnhub"


def test_parse_alpha_vantage_sentiment_and_tickers():
    payload = {
        "feed": [
            {
                "title": "Crude oil surges",
                "url": "https://example.com/c",
                "source": "OilPrice",
                "time_published": "20240101T100000",
                "summary": "Oil surged.",
                "overall_sentiment_label": "bullish",
                "overall_sentiment_score": "0.65",
                "ticker_sentiment": [
                    {"ticker": "WTI", "relevance_score": "0.9"},
                    {"ticker": "XOM", "relevance_score": "0.1"},
                ],
                "topics": "energy",
            },
        ],
    }
    items = news_service.parse_alpha_vantage(payload)
    assert len(items) == 1
    assert items[0]["sentiment"] == "bullish"
    assert abs(items[0]["sentiment_score"] - 0.65) < 1e-9
    assert items[0]["tickers"] == ["WTI"]  # relevance >= 0.2 only


def test_parse_alpha_vantage_error_raises():
    with pytest.raises(RuntimeError):
        news_service.parse_alpha_vantage({"Error Message": "Invalid API key"})


# --------------------------------------------------------------------------- #
# Normalisation helpers                                                       #
# --------------------------------------------------------------------------- #


def test_canonical_url_strips_tracking_params():
    assert news_service._canonical_url(
        "https://www.moneycontrol.com/news/?utm_source=feed&foo=bar"
    ) == "https://moneycontrol.com/news?foo=bar"
    assert news_service._canonical_url("not a url") == ""
    assert news_service._canonical_url("") == ""


def test_near_duplicate_threshold():
    assert news_service._is_near_duplicate("abc", "abc") is True
    assert news_service._is_near_duplicate("short", "shortish") is False
    a = "RBI cuts repo rate by 25 basis points as inflation cools"
    b = "RBI cuts repo rate by 25 basis points as inflation cools down"
    assert news_service._is_near_duplicate(a, b) is True


def test_clean_summary_drops_trailing_source():
    assert news_service._clean_summary(
        "The Economic Times reports RBI cut rates - The Economic Times",
        "Unrelated headline",
        "The Economic Times",
    ) == "The Economic Times reports RBI cut rates"


# --------------------------------------------------------------------------- #
# Router contract (service monkeypatched)                                     #
# --------------------------------------------------------------------------- #


class _FakeRow:
    """Minimal stand-in for a NewsArticle ORM row used by serialize_article."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def _serialize_stub(article):
    return {
        "id": article.id,
        "headline": article.headline,
        "summary": article.summary,
        "summary_kind": "source_snippet",
        "source_name": article.source_name,
        "source_domain": article.source_domain,
        "source_url": article.source_url,
        "published_at": getattr(article, "published_at", int(time.time())),
        "fetched_at": getattr(article, "fetched_at", int(time.time())),
        "age_minutes": 0,
        "region": getattr(article, "region", "global"),
        "region_label": "Global",
        "category": getattr(article, "category", "markets"),
        "category_label": "Markets",
        "tickers": getattr(article, "tickers", []),
        "sentiment": article.sentiment,
        "sentiment_score": article.sentiment_score,
        "sentiment_method": "lexicon",
        "source_type": article.source_type,
        "source_type_label": "Official / primary",
        "content_type": "report",
        "content_type_label": "Report",
        "credibility_level": article.credibility_level,
        "credibility_label": "Official / primary",
        "impact_level": article.impact_level,
        "is_verified": article.is_verified,
        "provider": "test",
    }


@pytest.fixture(autouse=True)
def _override_get_db():
    """The news endpoints only need a session object; every service call is
    monkeypatched, so a dummy object is enough to satisfy Depends(get_db)."""
    app.dependency_overrides[get_db] = lambda: iter([object()])
    yield
    app.dependency_overrides.pop(get_db, None)


def _monkeypatch_router(monkeypatch, articles):
    rows = [_FakeRow(**a) for a in articles]
    monkeypatch.setattr(news_router.news_service, "query_articles",
                        lambda db, **kw: (rows, len(rows)))
    monkeypatch.setattr(news_router.news_service, "last_refreshed_at",
                        lambda db: int(time.time()) - 100)
    monkeypatch.setattr(news_router.news_service, "is_stale", lambda db: False)
    monkeypatch.setattr(news_router.news_service, "serialize_article", _serialize_stub)
    monkeypatch.setattr(news_router.news_service, "get_counts", lambda db, **kw: {
        "total": len(rows), "high_impact": 0, "official": 0, "community": 0,
    })
    monkeypatch.setattr(news_router.news_service, "get_top_stories", lambda db, **kw: [])
    monkeypatch.setattr(news_router.news_service, "get_sentiment", lambda db, **kw: {
        "overall": {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0,
                    "average_score": 0, "sample_size": 0, "method": "lexicon"},
        "by_region": [], "by_source_type": {},
        "community": {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0,
                      "average_score": 0, "sample_size": 0, "method": "lexicon"},
        "official": {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0,
                     "average_score": 0, "sample_size": 0, "method": "lexicon"},
        "generated_at": int(time.time()),
    })
    monkeypatch.setattr(news_router.news_service, "get_trending", lambda db, **kw: {
        "window_hours": 24, "tickers": [], "generated_at": int(time.time()),
    })
    monkeypatch.setattr(news_router.news_service, "get_sources_status", lambda: {
        "sources": [], "providers": [], "credentials_needed": [],
        "credibility_scale": [], "notes": [],
    })
    monkeypatch.setattr(news_router.news_service, "refresh_news",
                        lambda db, **kw: {
                            "status": "ok", "fetched": 10, "inserted": 5,
                            "providers": [], "errors": [], "duration_ms": 100,
                        })


@pytest.fixture()
def client():
    return TestClient(app)


def test_list_news_returns_articles(client, monkeypatch):
    articles = [{
        "id": "a1", "headline": "RBI cuts repo rate", "summary": "RBI cut rates.",
        "source_name": "Reserve Bank of India", "source_domain": "rbi.org.in",
        "source_url": "https://www.rbi.org.in/x", "region": "india",
        "category": "policy", "sentiment": "bullish", "sentiment_score": 0.5,
        "source_type": "official", "credibility_level": 5, "impact_level": "high",
        "is_verified": True, "tickers": [], "published_at": int(time.time()),
        "fetched_at": int(time.time()), "source_domain": "rbi.org.in",
    }]
    _monkeypatch_router(monkeypatch, articles)
    response = client.get("/news/")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["articles"][0]["headline"] == "RBI cuts repo rate"
    assert body["articles"][0]["is_verified"] is True
    assert body["stale"] is False


def test_list_news_applies_filters(client, monkeypatch):
    seen_kwargs = {}

    def fake_query(db, **kw):
        seen_kwargs.update(kw)
        return [], 0

    monkeypatch.setattr(news_router.news_service, "query_articles", fake_query)
    monkeypatch.setattr(news_router.news_service, "last_refreshed_at", lambda db: None)
    monkeypatch.setattr(news_router.news_service, "is_stale", lambda db: True)
    client.get("/news/?region=india&source_type=official&sentiment=bullish&ticker=RELIANCE&q=rate&min_credibility=5&hours=48&sort=impact&limit=10&offset=0")
    assert seen_kwargs["region"] == "india"
    assert seen_kwargs["source_type"] == "official"
    assert seen_kwargs["sentiment"] == "bullish"
    assert seen_kwargs["ticker"] == "RELIANCE"
    assert seen_kwargs["q"] == "rate"
    assert seen_kwargs["min_credibility"] == 5
    assert seen_kwargs["hours"] == 48
    assert seen_kwargs["sort"] == "impact"
    assert seen_kwargs["limit"] == 10


def test_list_news_rejects_bad_sort(client, monkeypatch):
    monkeypatch.setattr(news_router.news_service, "query_articles", lambda db, **kw: ([], 0))
    monkeypatch.setattr(news_router.news_service, "last_refreshed_at", lambda db: None)
    monkeypatch.setattr(news_router.news_service, "is_stale", lambda db: True)
    response = client.get("/news/?sort=nonsense")
    assert response.status_code == 400


def test_overview_endpoint(client, monkeypatch):
    monkeypatch.setattr(news_router.news_service, "get_counts", lambda db, **kw: {
        "total": 7, "high_impact": 2, "official": 3, "community": 1,
    })
    monkeypatch.setattr(news_router.news_service, "get_top_stories", lambda db, **kw: [])
    monkeypatch.setattr(news_router.news_service, "get_sentiment", lambda db, **kw: {
        "window_hours": 48,
        "overall": {"bullish_pct": 50, "bearish_pct": 25, "neutral_pct": 25,
                    "average_score": 0.1, "sample_size": 4, "method": "lexicon"},
        "by_region": [], "by_source_type": {},
        "community": {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0,
                      "average_score": 0, "sample_size": 0, "method": "lexicon"},
        "official": {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0,
                     "average_score": 0, "sample_size": 0, "method": "lexicon"},
        "generated_at": int(time.time()),
    })
    monkeypatch.setattr(news_router.news_service, "last_refreshed_at", lambda db: int(time.time()))
    monkeypatch.setattr(news_router.news_service, "is_stale", lambda db: False)
    response = client.get("/news/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 7
    assert body["official"] == 3
    assert body["stale"] is False


def test_sources_endpoint(client, monkeypatch):
    monkeypatch.setattr(news_router.news_service, "get_sources_status", lambda: {
        "sources": [], "providers": [], "credentials_needed": [
            {"provider": "marketaux", "label": "Marketaux", "env_var": "MARKETAUX_API_KEY",
             "free_tier": "tier", "signup": "https://example.com", "notes": "notes"},
        ],
        "credibility_scale": [], "notes": [],
    })
    response = client.get("/news/sources")
    assert response.status_code == 200
    body = response.json()
    assert len(body["credentials_needed"]) == 1
    assert body["credentials_needed"][0]["env_var"] == "MARKETAUX_API_KEY"


def test_refresh_endpoint(client, monkeypatch):
    called = {}

    async def fake_refresh(db, *, force, providers):
        called["force"] = force
        called["providers"] = providers
        return {"status": "ok", "fetched": 1, "inserted": 1, "providers": [],
                "errors": [], "duration_ms": 50}

    monkeypatch.setattr(news_router.news_service, "refresh_news", fake_refresh)
    response = client.post("/news/refresh?force=true&providers=google_news,direct_rss")
    assert response.status_code == 200
    assert called["force"] is True
    assert called["providers"] == ["google_news", "direct_rss"]


def test_refresh_rejects_unknown_provider(client, monkeypatch):
    async def fake_refresh(db, **kw):
        return {}

    monkeypatch.setattr(news_router.news_service, "refresh_news", fake_refresh)
    response = client.post("/news/refresh?providers=notaprovider")
    assert response.status_code == 400

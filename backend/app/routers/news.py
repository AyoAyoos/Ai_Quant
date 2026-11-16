"""Market News Hub API.

Read endpoints never hit the network: they serve whatever the ingestion
pipeline has already classified and stored.  ``POST /news/refresh`` performs
one ingestion pass and is the only endpoint that fetches upstream sources.

Credibility is assigned by :mod:`app.services.news_taxonomy`, never by an
upstream provider.  Only headline, a short source snippet and the link are
stored — full article text and publisher images are not copied.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    NewsListOut,
    NewsOverviewOut,
    NewsRefreshOut,
    NewsSentimentOut,
    NewsTrendingOut,
)
from app.services import news_service
from app.services import news_taxonomy as tax

router = APIRouter(prefix="/news", tags=["news"])

_SORTS = ("recent", "impact", "credibility")


def _check(value: Optional[str], allowed: tuple[str, ...], field: str) -> Optional[str]:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported {field} '{value}'. Allowed: {', '.join(allowed)}",
        )
    return value


@router.get("/", response_model=NewsListOut)
def list_news(
    region: Optional[str] = Query(None, description="india|usa|china|europe|japan|global"),
    category: Optional[str] = Query(None, description="markets|stocks|economy|policy|..."),
    source_type: Optional[str] = Query(None, description="official|newswire|publisher|aggregator|community"),
    content_type: Optional[str] = Query(None, description="report|analysis|opinion|community"),
    sentiment: Optional[str] = Query(None, description="bullish|bearish|neutral"),
    ticker: Optional[str] = Query(None, description="Filter by a known ticker, e.g. RELIANCE"),
    q: Optional[str] = Query(None, max_length=120, description="Search headline, summary or source"),
    min_credibility: Optional[int] = Query(None, ge=1, le=5),
    hours: int = Query(168, ge=1, le=24 * 30),
    sort: str = Query("recent", description="recent|impact|credibility"),
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List stored articles, newest first by default."""
    rows, total = news_service.query_articles(
        db,
        region=_check(region, tax.REGIONS, "region"),
        category=_check(category, tax.CATEGORIES, "category"),
        source_type=_check(source_type, tax.SOURCE_TYPES, "source_type"),
        content_type=_check(content_type, tax.CONTENT_TYPES, "content_type"),
        sentiment=_check(sentiment, tax.SENTIMENTS, "sentiment"),
        ticker=ticker,
        q=q,
        min_credibility=min_credibility,
        hours=hours,
        sort=_check(sort, _SORTS, "sort") or "recent",
        limit=limit,
        offset=offset,
    )
    return {
        "articles": [news_service.serialize_article(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "window_hours": hours,
        "refreshed_at": news_service.last_refreshed_at(db),
        "stale": news_service.is_stale(db),
        "generated_at": int(time.time()),
    }


@router.get("/overview", response_model=NewsOverviewOut)
def news_overview(
    hours: int = Query(48, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
):
    """Hub header: counts, top stories, sentiment and the refresh state."""
    counts = news_service.get_counts(db, hours=hours)
    return {
        "window_hours": hours,
        **counts,
        "top_stories": news_service.get_top_stories(db, hours=hours),
        "sentiment": news_service.get_sentiment(db, hours=hours),
        "refreshed_at": news_service.last_refreshed_at(db),
        "stale": news_service.is_stale(db),
        "generated_at": int(time.time()),
    }


@router.get("/trending", response_model=NewsTrendingOut)
def news_trending(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_db),
):
    """Most-mentioned tickers, with a mention trend against the prior window."""
    return news_service.get_trending(db, hours=hours, limit=limit)


@router.get("/sentiment", response_model=NewsSentimentOut)
def news_sentiment(
    hours: int = Query(48, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
):
    """Aggregate sentiment, kept separate for official and community sources."""
    return news_service.get_sentiment(db, hours=hours)


@router.get("/sources")
def news_sources():
    """Source registry, credibility scale and the credentials still needed."""
    return news_service.get_sources_status()


@router.get("/sources/{key}")
def news_source(key: str):
    """One source's registry entry and credibility explanation."""
    status = news_service.get_sources_status()
    for source in status["sources"]:
        if source["key"].lower() == key.lower():
            return source
    raise HTTPException(status_code=404, detail=f"Unknown source '{key}'")


@router.post("/refresh", response_model=NewsRefreshOut)
async def refresh_news(
    force: bool = Query(True, description="Skip the freshness check"),
    providers: Optional[str] = Query(
        None,
        description="Comma-separated provider subset: google_news,direct_rss,reddit,marketaux,finnhub,alpha_vantage",
    ),
    db: Session = Depends(get_db),
):
    """Run one ingestion pass over every enabled provider."""
    selected: Optional[list[str]] = None
    if providers:
        selected = [part.strip() for part in providers.split(",") if part.strip()]
        allowed = {
            "google_news",
            "direct_rss",
            "reddit",
            "marketaux",
            "finnhub",
            "alpha_vantage",
        }
        unknown = [name for name in selected if name not in allowed]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider(s): {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}",
            )
    return await news_service.refresh_news(db, force=force, providers=selected)

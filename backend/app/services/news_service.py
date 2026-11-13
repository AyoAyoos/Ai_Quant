"""Market News Hub ingestion, classification and query service.

The pipeline is deliberately boring and auditable:

    keyless feeds (Google News RSS, official RSS, Reddit public JSON)
    + optional keyed APIs (Marketaux, Finnhub, Alpha Vantage)
        -> normalise (headline, short snippet, source URL, timestamp)
        -> classify (region, category, tickers, sentiment, impact)
        -> deduplicate (exact URL + near-identical title, same source type)
        -> Postgres (news_articles)
        -> API (feed / overview / trending / sentiment / sources)

Rules enforced here:

* Only headlines, short source snippets and links are stored.  Full article
  text and publisher images are never copied.
* Credibility always comes from :mod:`news_taxonomy`, never from a provider.
* ``is_verified`` is true only for an official/primary source.  A publisher
  reporting on a filing is not silently promoted to a verified fact.
* Sentiment is a deterministic lexicon unless a keyed provider explicitly
  supplies its own score; the method is stored on every article.
"""

from __future__ import annotations

import asyncio
import hashlib
import html as html_lib
import logging
import math
import re
import time
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import case, desc, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import NewsArticle
from app.services import news_taxonomy as tax

logger = logging.getLogger(__name__)

GOOGLE_NEWS_URL = "https://news.google.com/rss/search"
REDDIT_BASE = "https://www.reddit.com"
MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"
FINNHUB_URL = "https://finnhub.io/api/v1/news"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

MAX_ARTICLES_PER_REFRESH = 600
_MAX_SUMMARY = 420
_MAX_HEADLINE = 500
_REDDIT_MIN_SCORE = 5
_MAX_TITLE_MATCHES = 400

_REFRESH_LOCK = asyncio.Lock()

_PROVIDER_PRIORITY = {
    "direct_rss": 4,
    "google_news_rss": 3,
    "marketaux": 2,
    "finnhub": 2,
    "alpha_vantage": 2,
    "reddit": 1,
}

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "utm_brand", "fbclid", "gclid",
    "mc_cid", "mc_eid", "ref", "referrer", "source", "cmp", "soc_src",
    "soc_trk", "oc", "hl", "gl", "ceid", "output", "smid", "partner",
}

_RELEVANCE_TERMS = (
    "market", "stock", "share", "equity", "bond", "yield", "rupee", "dollar",
    "euro", "yen", "gold", "oil", "crude", "bitcoin", "crypto", "inflation",
    "gdp", "rate", "fed", "fomc", "rbi", "sebi", "earnings", "profit",
    "revenue", "ipo", "merger", "acquisition", "invest", "trading",
    "economy", "economic", "bank", "finance", "financial", "commodit",
    "forex", "currency", "tariff", "sanction", "budget", "policy",
    "stimulus", "recession", "growth", "fund", "index", "nifty", "sensex",
    "nasdaq", "s&p", "dow", "nikkei", "shanghai", "ecb", "pboc",
)

_ALPHA_LABELS = {
    "bullish": "bullish",
    "somewhat-bullish": "bullish",
    "neutral": "neutral",
    "somewhat-bearish": "bearish",
    "bearish": "bearish",
}


# ---------------------------------------------------------------------------
# Small normalisation helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Naive UTC, matching the rest of the database models."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_epoch(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return int(aware.timestamp())


def _from_epoch(value: int | float) -> datetime:
    number = float(value)
    if number > 1e12:  # milliseconds
        number /= 1000.0
    return datetime.fromtimestamp(number, tz=timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    parsed: Optional[datetime] = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        if value > 0:
            parsed = _from_epoch(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if re.fullmatch(r"\d{10,13}", text):
            parsed = _from_epoch(int(text))
        else:
            for fmt in ("%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                try:
                    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        parsed = parsedate_to_datetime(text)
                    except (TypeError, ValueError):
                        parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_lib.unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _clean_summary(value: str, headline: str = "", source_name: str = "") -> str:
    text = _strip_html(value)
    if not text:
        return ""
    for phrase in ("Read more", "Continue reading", "Click here", "Read the full story"):
        if text.lower().endswith(phrase.lower()):
            text = text[: -len(phrase)].strip(" -–—|")
    for suffix in (source_name, "Google News"):
        if suffix and text.lower().endswith(suffix.lower()):
            text = text[: -len(suffix)].strip(" -–—|")
    if source_name and text.lower().endswith(f"- {source_name}".lower()):
        text = text[: -(len(source_name) + 2)].strip()

    title_key = _normalize_title(headline)
    summary_key = _normalize_title(text)
    if title_key and summary_key and (
        summary_key == title_key
        or (summary_key.startswith(title_key) and len(summary_key) <= len(title_key) + 30)
    ):
        return ""
    if len(text) <= _MAX_SUMMARY:
        return text
    return text[: _MAX_SUMMARY - 1].rstrip() + "…"


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _canonical_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw or not re.match(r"^https?://", raw, re.I):
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    for prefix in ("www.", "m.", "amp."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    if not host:
        return ""
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    path = re.sub(r"/+$", "", parts.path) or "/"
    query_pairs = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    query = urlencode(query_pairs)
    return urlunsplit((scheme, host + port, path, query, ""))


def _external_id(source_url: str, headline: str, source_name: str = "") -> str:
    canonical = _canonical_url(source_url)
    if not canonical:
        canonical = f"{_normalize_title(headline)}|{_normalize_title(source_name)}"
    return hashlib.sha256(canonical.encode("utf-8", "ignore")).hexdigest()[:40]


def _is_near_duplicate(first: str, second: str) -> bool:
    if not first or not second:
        return False
    if first == second:
        return True
    if len(first) < 30 or len(second) < 30:
        return False
    ratio = SequenceMatcher(None, first, second).ratio()
    if ratio >= 0.82:
        return True
    if ratio < 0.65:
        return False
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    if not first_tokens or not second_tokens:
        return False
    jaccard = len(first_tokens & second_tokens) / len(first_tokens | second_tokens)
    return jaccard >= 0.72


def _looks_relevant(text: str) -> bool:
    lowered = (text or "").lower()
    if any(term in lowered for term in _RELEVANCE_TERMS):
        return True
    return bool(tax.extract_tickers(text))


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return str(value)[:120]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {
            str(key)[:48]: _json_safe(item, depth + 1)
            for key, item in list(value.items())[:24]
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth + 1) for item in list(value)[:24]]
    return str(value)[:120]


def _safe_error(exc: BaseException) -> str:
    """Error text that never leaks an API token from a request URL."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
        return "timeout"
    text = re.sub(
        r"(api_token|apikey|api_key|token|access_key)=[^&\s]+",
        r"\1=***",
        str(exc),
        flags=re.I,
    )
    return f"{type(exc).__name__}: {text[:180]}"


# ---------------------------------------------------------------------------
# RSS / Atom parsing
# ---------------------------------------------------------------------------

def _local_name(tag: str) -> str:
    return (tag or "").rsplit("}", 1)[-1].lower()


def _node_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if _local_name(child.tag) in names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _node_link(node: ET.Element) -> str:
    for child in list(node):
        if _local_name(child.tag) == "link":
            href = (child.attrib.get("href") or "").strip()
            if href:
                return href
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def _node_source(node: ET.Element) -> tuple[str, str]:
    for child in list(node):
        if _local_name(child.tag) == "source":
            return (child.text or "").strip(), (child.attrib.get("url") or "").strip()
    return "", ""


def _parse_feed_items(xml_text: str) -> list[dict]:
    """Parse RSS ``item`` or Atom ``entry`` nodes into a common shape."""
    root = ET.fromstring(xml_text)
    items = [node for node in root.iter() if _local_name(node.tag) == "item"]
    if not items:
        items = [node for node in root.iter() if _local_name(node.tag) == "entry"]

    parsed: list[dict] = []
    for node in items:
        title = _node_text(node, {"title"})
        link = _node_link(node)
        summary = _node_text(node, {"description", "summary", "content", "encoded"})
        published_text = ""
        for name in ("pubdate", "published", "updated", "date", "created"):
            published_text = _node_text(node, {name})
            if published_text:
                break
        source_name, source_url = _node_source(node)
        parsed.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published": _parse_datetime(published_text),
                "source_name": source_name,
                "source_url": source_url,
            }
        )
    return parsed


def parse_google_news_rss(xml_text: str, feed: tax.GoogleNewsFeed) -> list[dict]:
    """Turn one Google News RSS response into raw article dictionaries."""
    articles: list[dict] = []
    seen: set[str] = set()
    for item in _parse_feed_items(xml_text):
        title = (item.get("title") or "").strip()
        link = (item.get("link") or "").strip()
        if not title or not link:
            continue
        source_name = (item.get("source_name") or "Google News").strip()
        if source_name and title.endswith(f" - {source_name}"):
            title = title[: -(len(source_name) + 3)].strip()
        if not title:
            continue
        key = _normalize_title(title)
        if key in seen:
            continue
        seen.add(key)

        summary = _clean_summary(item.get("summary") or "", title, source_name)
        if feed.relevant_only and not _looks_relevant(f"{title} {summary}"):
            continue

        articles.append(
            {
                "headline": title,
                "summary": summary,
                "source_name": source_name,
                "source_url": link,
                "published_at": item.get("published"),
                "provider": "google_news_rss",
                "region_hint": feed.region,
                "raw_metadata": {"feed": feed.key},
            }
        )
        if len(articles) >= feed.max_items:
            break
    return articles


def parse_direct_feed(xml_text: str, feed: tax.DirectFeed) -> list[dict]:
    """Turn one official RSS/Atom response into raw article dictionaries."""
    articles: list[dict] = []
    for item in _parse_feed_items(xml_text):
        title = (item.get("title") or "").strip()
        link = (item.get("link") or "").strip()
        if not title or not link:
            continue
        summary = _clean_summary(item.get("summary") or "", title, feed.name)
        articles.append(
            {
                "headline": title,
                "summary": summary,
                "source_name": feed.name,
                "source_url": link,
                "published_at": item.get("published"),
                "provider": "direct_rss",
                "region_hint": feed.region,
                "source_type_hint": feed.source_type,
                "raw_metadata": {"feed": feed.key, "domain": feed.domain},
            }
        )
        if len(articles) >= feed.max_items:
            break
    return articles


def parse_reddit_listing(payload: dict, sub: tax.SubredditSpec) -> list[dict]:
    """Parse a Reddit ``/hot.json`` listing into community posts."""
    children = (((payload or {}).get("data") or {}).get("children")) or []
    articles: list[dict] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        data = child.get("data") or {}
        if data.get("stickied") or data.get("over_18"):
            continue
        try:
            score = int(data.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        if score < _REDDIT_MIN_SCORE:
            continue
        title = (data.get("title") or "").strip()
        if len(title) < 15:
            continue
        permalink = (data.get("permalink") or "").strip()
        if not permalink:
            continue
        if not permalink.startswith("/"):
            permalink = "/" + permalink
        selftext = (data.get("selftext") or "").strip()
        if selftext.lower() in {"[removed]", "[deleted]"}:
            selftext = ""
        articles.append(
            {
                "headline": title,
                "summary": _clean_summary(selftext, title, f"r/{sub.name}")[:_MAX_SUMMARY],
                "source_name": f"r/{sub.name}",
                "source_url": f"{REDDIT_BASE}{permalink}",
                "published_at": _parse_datetime(data.get("created_utc")),
                "provider": "reddit",
                "region_hint": sub.region,
                "source_type_hint": "community",
                "raw_metadata": {
                    "subreddit": sub.name,
                    "score": score,
                    "comments": int(data.get("num_comments") or 0),
                    "upvote_ratio": data.get("upvote_ratio"),
                    "flair": data.get("link_flair_text"),
                },
            }
        )
        if len(articles) >= sub.limit:
            break
    return articles


# ---------------------------------------------------------------------------
# Keyed provider parsing
# ---------------------------------------------------------------------------

def parse_marketaux(payload: dict) -> list[dict]:
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(str(payload.get("error"))[:200])
    articles: list[dict] = []
    for item in (payload or {}).get("data") or []:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue
        entities = item.get("entities") if isinstance(item.get("entities"), list) else []
        tickers: list[str] = []
        entity_scores: list[float] = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            symbol = entity.get("symbol")
            if symbol:
                tickers.append(symbol)
            score = entity.get("sentiment_score")
            if isinstance(score, (int, float)) and math.isfinite(float(score)):
                entity_scores.append(float(score))
        provider_score = (
            sum(entity_scores) / len(entity_scores) if entity_scores else None
        )
        summary = _clean_summary(
            item.get("snippet") or item.get("description") or "", title,
            str(item.get("source") or ""),
        )
        articles.append(
            {
                "headline": title,
                "summary": summary,
                "source_name": str(item.get("source") or ""),
                "source_url": url,
                "published_at": _parse_datetime(item.get("published_at")),
                "provider": "marketaux",
                "tickers": tickers,
                "sentiment_score": provider_score,
                "sentiment_method": "provider" if provider_score is not None else "lexicon",
                "raw_metadata": {"entities": len(entities)},
            }
        )
    return articles


def parse_finnhub(payload: Any) -> list[dict]:
    if not isinstance(payload, list):
        return []
    articles: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = (item.get("headline") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue
        related = item.get("related") or ""
        tickers = [part.strip() for part in str(related).split(",") if part.strip()]
        articles.append(
            {
                "headline": title,
                "summary": _clean_summary(
                    item.get("summary") or "", title, str(item.get("source") or "")
                ),
                "source_name": str(item.get("source") or ""),
                "source_url": url,
                "published_at": _parse_datetime(item.get("datetime")),
                "provider": "finnhub",
                "tickers": tickers,
                "raw_metadata": {"category": item.get("category")},
            }
        )
    return articles


def parse_alpha_vantage(payload: dict) -> list[dict]:
    if isinstance(payload, dict) and not payload.get("feed"):
        note = payload.get("Note") or payload.get("Information") or payload.get("Error Message")
        if note:
            raise RuntimeError(f"Alpha Vantage: {str(note)[:180]}")
    articles: list[dict] = []
    for item in (payload or {}).get("feed") or []:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue
        tickers: list[str] = []
        for entry in item.get("ticker_sentiment") or []:
            if not isinstance(entry, dict):
                continue
            try:
                relevance = float(entry.get("relevance_score") or 0)
            except (TypeError, ValueError):
                relevance = 0.0
            if relevance >= 0.2 and entry.get("ticker"):
                tickers.append(entry["ticker"])
        label = _ALPHA_LABELS.get(
            str(item.get("overall_sentiment_label") or "").strip().lower(), "neutral"
        )
        try:
            score = float(item.get("overall_sentiment_score"))
        except (TypeError, ValueError):
            score = None
        articles.append(
            {
                "headline": title,
                "summary": _clean_summary(
                    item.get("summary") or "", title, str(item.get("source") or "")
                ),
                "source_name": str(item.get("source") or ""),
                "source_url": url,
                "published_at": _parse_datetime(item.get("time_published")),
                "provider": "alpha_vantage",
                "tickers": tickers,
                "sentiment": label,
                "sentiment_score": score,
                "sentiment_method": "provider" if score is not None else "lexicon",
                "raw_metadata": {"topics": item.get("topics")},
            }
        )
    return articles


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _raw_to_article(raw: dict, fetched_at: datetime) -> Optional[dict]:
    headline = re.sub(r"\s+", " ", (raw.get("headline") or "")).strip()[:_MAX_HEADLINE]
    source_url = (raw.get("source_url") or "").strip()
    if not headline or not source_url:
        return None
    if not re.match(r"^https?://", source_url, re.I):
        return None

    published_at = _parse_datetime(raw.get("published_at")) or fetched_at
    if published_at > fetched_at + timedelta(hours=6):
        published_at = fetched_at
    if published_at < fetched_at - timedelta(days=max(2, settings.news_retention_days)):
        return None

    summary = _clean_summary(
        raw.get("summary") or "", headline, str(raw.get("source_name") or "")
    )

    classified = tax.classify_article(
        headline=headline,
        summary=summary,
        source_name=str(raw.get("source_name") or ""),
        source_url=source_url,
        region_hint=raw.get("region_hint"),
        source_type_hint=raw.get("source_type_hint"),
        tickers=raw.get("tickers"),
        sentiment=raw.get("sentiment"),
        sentiment_score=raw.get("sentiment_score"),
        sentiment_method=raw.get("sentiment_method") or "lexicon",
    )

    tickers = classified.get("tickers") or []
    return {
        "id": str(uuid.uuid4()),
        **classified,
        "provider": str(raw.get("provider") or "unknown"),
        "published_at": published_at,
        "fetched_at": fetched_at,
        "external_id": _external_id(
            classified["source_url"], headline, classified["source_name"]
        ),
        "tickers_text": f"|{'|'.join(tickers)}|" if tickers else "",
        "raw_metadata": _json_safe(raw.get("raw_metadata") or {}),
    }


def _dedupe_batch(articles: list[dict]) -> list[dict]:
    """Remove exact duplicates and same-type near-duplicates.

    Different source types are intentionally kept: an official filing and a
    publisher article about that filing are both useful and carry different
    credibility.  Within one source type the higher-priority feed wins.
    """
    articles.sort(
        key=lambda item: (
            _PROVIDER_PRIORITY.get(item.get("provider", ""), 0),
            item.get("credibility_level") or 0,
            item.get("published_at") or datetime.min,
        ),
        reverse=True,
    )

    kept: list[dict] = []
    seen_ids: set[str] = set()
    titles_by_type: dict[str, list[str]] = defaultdict(list)

    for article in articles:
        external_id = article.get("external_id") or ""
        if external_id in seen_ids:
            continue
        title_key = _normalize_title(article.get("headline") or "")
        source_type = article.get("source_type") or "publisher"
        if title_key and any(
            _is_near_duplicate(title_key, existing)
            for existing in titles_by_type[source_type]
        ):
            continue
        seen_ids.add(external_id)
        if title_key:
            titles_by_type[source_type].append(title_key)
        kept.append(article)
        if len(kept) >= MAX_ARTICLES_PER_REFRESH:
            break
    return kept


def _dedupe_against_db(
    db: Session, articles: list[dict], fetched_at: datetime
) -> list[dict]:
    cutoff = fetched_at - timedelta(days=14)
    rows = (
        db.query(NewsArticle.external_id, NewsArticle.headline, NewsArticle.source_type)
        .filter(NewsArticle.fetched_at >= cutoff)
        .limit(2000)
        .all()
    )
    existing_ids = {row[0] for row in rows}
    titles_by_type: dict[str, list[str]] = defaultdict(list)
    for _, headline, source_type in rows:
        key = _normalize_title(headline or "")
        if key and len(titles_by_type[source_type]) < _MAX_TITLE_MATCHES:
            titles_by_type[source_type].append(key)

    kept: list[dict] = []
    for article in articles:
        if article.get("external_id") in existing_ids:
            continue
        source_type = article.get("source_type") or "publisher"
        title_key = _normalize_title(article.get("headline") or "")
        # Community posts are linked by their permalink; a crosspost with a
        # different URL is still a distinct post.  News articles are deduped
        # within their own source type only.
        if title_key and any(
            _is_near_duplicate(title_key, existing)
            for existing in titles_by_type[source_type]
        ):
            continue
        existing_ids.add(article.get("external_id"))
        if title_key:
            titles_by_type[source_type].append(title_key)
        kept.append(article)
    return kept


def _insert_articles(db: Session, articles: list[dict]) -> int:
    if not articles:
        return 0
    dialect = ""
    try:
        dialect = db.get_bind().dialect.name
    except Exception:
        dialect = ""

    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        inserted = 0
        for start in range(0, len(articles), 100):
            chunk = articles[start:start + 100]
            statement = (
                pg_insert(NewsArticle)
                .values(chunk)
                .on_conflict_do_nothing(index_elements=["external_id"])
            )
            result = db.execute(statement)
            inserted += result.rowcount or 0
        db.commit()
        return inserted

    inserted = 0
    try:
        for article in articles:
            db.add(NewsArticle(**article))
        db.commit()
        return len(articles)
    except IntegrityError:
        db.rollback()
        for article in articles:
            try:
                with db.begin_nested():
                    db.add(NewsArticle(**article))
                inserted += 1
            except IntegrityError:
                continue
        db.commit()
        return inserted


def _cleanup(db: Session, fetched_at: datetime) -> int:
    deleted = 0
    cutoff = fetched_at - timedelta(days=max(2, settings.news_retention_days))
    deleted += (
        db.query(NewsArticle)
        .filter(NewsArticle.published_at < cutoff)
        .delete(synchronize_session=False)
    )

    maximum = max(100, settings.news_max_articles)
    count = db.query(func.count(NewsArticle.id)).scalar() or 0
    if count > maximum:
        excess = count - maximum
        rows = (
            db.query(NewsArticle.id)
            .order_by(NewsArticle.published_at.asc())
            .limit(excess)
            .all()
        )
        ids = [row[0] for row in rows]
        if ids:
            deleted += (
                db.query(NewsArticle)
                .filter(NewsArticle.id.in_(ids))
                .delete(synchronize_session=False)
            )
    db.commit()
    return deleted


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

@dataclass
class FetchOutcome:
    provider: str
    items: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0


def _new_client() -> httpx.AsyncClient:
    headers = {
        "User-Agent": settings.news_user_agent,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, application/json;q=0.9, */*;q=0.5",
    }
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.news_rss_timeout_seconds),
        follow_redirects=True,
        headers=headers,
    )


async def _get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> httpx.Response:
    last_error: Optional[BaseException] = None
    for attempt in range(2):
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                await asyncio.sleep(1.5)
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == 0:
                await asyncio.sleep(1.0)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("request failed")


async def _fetch_google_news_group(client: httpx.AsyncClient) -> tuple[list[dict], list[str]]:
    if not settings.news_enable_google_news:
        return [], ["disabled"]
    semaphore = asyncio.Semaphore(3)

    async def fetch_one(feed: tax.GoogleNewsFeed):
        async with semaphore:
            response = await _get(
                client,
                GOOGLE_NEWS_URL,
                params={
                    "q": feed.query,
                    "hl": feed.hl,
                    "gl": feed.gl,
                    "ceid": feed.ceid,
                },
            )
            return parse_google_news_rss(response.text, feed)

    results = await asyncio.gather(
        *(fetch_one(feed) for feed in tax.GOOGLE_NEWS_FEEDS),
        return_exceptions=True,
    )
    items: list[dict] = []
    errors: list[str] = []
    for feed, result in zip(tax.GOOGLE_NEWS_FEEDS, results):
        if isinstance(result, BaseException):
            errors.append(f"{feed.key}: {_safe_error(result)}")
        else:
            items.extend(result)
    return items, errors


async def _fetch_direct_group(client: httpx.AsyncClient) -> tuple[list[dict], list[str]]:
    semaphore = asyncio.Semaphore(3)

    async def fetch_one(feed: tax.DirectFeed):
        async with semaphore:
            response = await _get(client, feed.url)
            return parse_direct_feed(response.text, feed)

    results = await asyncio.gather(
        *(fetch_one(feed) for feed in tax.DIRECT_RSS_FEEDS),
        return_exceptions=True,
    )
    items: list[dict] = []
    errors: list[str] = []
    for feed, result in zip(tax.DIRECT_RSS_FEEDS, results):
        if isinstance(result, BaseException):
            errors.append(f"{feed.key}: {_safe_error(result)}")
        else:
            items.extend(result)
    return items, errors


async def _fetch_reddit_group(client: httpx.AsyncClient) -> tuple[list[dict], list[str]]:
    if not settings.news_enable_reddit:
        return [], ["disabled"]
    semaphore = asyncio.Semaphore(2)
    user_agent = settings.reddit_user_agent or settings.news_user_agent

    async def fetch_one(sub: tax.SubredditSpec):
        async with semaphore:
            response = await _get(
                client,
                f"{REDDIT_BASE}/r/{sub.name}/hot.json",
                params={"limit": min(25, sub.limit), "raw_json": 1},
                headers={"User-Agent": user_agent},
            )
            return parse_reddit_listing(response.json(), sub)

    results = await asyncio.gather(
        *(fetch_one(sub) for sub in tax.REDDIT_SUBREDDITS),
        return_exceptions=True,
    )
    items: list[dict] = []
    errors: list[str] = []
    for sub, result in zip(tax.REDDIT_SUBREDDITS, results):
        if isinstance(result, BaseException):
            errors.append(f"r/{sub.name}: {_safe_error(result)}")
        else:
            items.extend(result)
    return items, errors


async def _fetch_marketaux_group(client: httpx.AsyncClient) -> list[dict]:
    if not settings.marketaux_api_key:
        return []
    response = await _get(
        client,
        MARKETAUX_URL,
        params={
            "api_token": settings.marketaux_api_key,
            "language": "en",
            "filter_entities": "true",
            "limit": 50,
        },
    )
    return parse_marketaux(response.json())


async def _fetch_finnhub_group(client: httpx.AsyncClient) -> list[dict]:
    if not settings.finnhub_api_key:
        return []
    response = await _get(
        client,
        FINNHUB_URL,
        params={"category": "general", "token": settings.finnhub_api_key},
    )
    return parse_finnhub(response.json())


async def _fetch_alpha_vantage_group(client: httpx.AsyncClient) -> list[dict]:
    if not settings.alpha_vantage_api_key:
        return []
    response = await _get(
        client,
        ALPHA_VANTAGE_URL,
        params={
            "function": "NEWS_SENTIMENT",
            "topics": "financial_markets,economy_macro,earnings",
            "limit": 50,
            "apikey": settings.alpha_vantage_api_key,
        },
    )
    return parse_alpha_vantage(response.json())


async def _collect_outcomes(
    client: httpx.AsyncClient, providers: Optional[Iterable[str]] = None
) -> list[FetchOutcome]:
    selected = set(providers or ())
    available = {
        "google_news",
        "direct_rss",
        "reddit",
        "marketaux",
        "finnhub",
        "alpha_vantage",
    }
    if selected:
        available &= selected

    async def run(provider: str, factory):
        started = time.perf_counter()
        try:
            result = await factory()
            if isinstance(result, tuple):
                items, errors = result
            else:
                items, errors = result, []
            return FetchOutcome(
                provider=provider,
                items=items,
                errors=errors,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except BaseException as exc:  # provider failures must not abort others
            return FetchOutcome(
                provider=provider,
                items=[],
                errors=[_safe_error(exc)],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    jobs = []
    if "google_news" in available:
        jobs.append(run("google_news", lambda: _fetch_google_news_group(client)))
    if "direct_rss" in available:
        jobs.append(run("direct_rss", lambda: _fetch_direct_group(client)))
    if "reddit" in available:
        jobs.append(run("reddit", lambda: _fetch_reddit_group(client)))
    if "marketaux" in available:
        jobs.append(run("marketaux", lambda: _fetch_marketaux_group(client)))
    if "finnhub" in available:
        jobs.append(run("finnhub", lambda: _fetch_finnhub_group(client)))
    if "alpha_vantage" in available:
        jobs.append(run("alpha_vantage", lambda: _fetch_alpha_vantage_group(client)))
    return await asyncio.gather(*jobs)


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def last_refreshed_at(db: Session) -> Optional[int]:
    value = db.query(func.max(NewsArticle.fetched_at)).scalar()
    return _to_epoch(value) if value else None


def is_stale(db: Session) -> bool:
    latest = db.query(func.max(NewsArticle.fetched_at)).scalar()
    if latest is None:
        return True
    age = _utcnow() - latest
    return age > timedelta(minutes=max(5, settings.news_refresh_minutes))


async def refresh_news(
    db: Session,
    *,
    force: bool = False,
    providers: Optional[Iterable[str]] = None,
) -> dict:
    """Fetch every enabled provider, classify, dedupe and persist.

    ``force=False`` lets the background worker skip a refresh that is still
    fresh.  The manual endpoint passes ``force=True``.
    """
    async with _REFRESH_LOCK:
        started = time.perf_counter()
        now = _utcnow()
        latest = last_refreshed_at(db)
        interval_seconds = max(5, settings.news_refresh_minutes) * 60
        if not force and latest is not None and int(time.time()) - latest < interval_seconds:
            return {
                "status": "fresh",
                "fetched": 0,
                "normalized": 0,
                "inserted": 0,
                "duplicates": 0,
                "invalid": 0,
                "deleted": 0,
                "providers": [],
                "errors": [],
                "refreshed_at": latest,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }

        fetched_at = _utcnow()
        async with _new_client() as client:
            outcomes = await _collect_outcomes(client, providers)

        raw_items = [item for outcome in outcomes for item in outcome.items]
        normalized: list[dict] = []
        for raw in raw_items:
            article = _raw_to_article(raw, fetched_at)
            if article is not None:
                normalized.append(article)

        batch = _dedupe_batch(normalized)
        candidates = _dedupe_against_db(db, batch, fetched_at)
        inserted = _insert_articles(db, candidates)
        deleted = _cleanup(db, fetched_at)

        errors = [
            {"provider": outcome.provider, "error": error}
            for outcome in outcomes
            for error in outcome.errors
        ]
        providers_payload = [
            {
                "provider": outcome.provider,
                "fetched": len(outcome.items),
                "errors": len(outcome.errors),
                "duration_ms": outcome.duration_ms,
            }
            for outcome in outcomes
        ]

        if not outcomes:
            status = "disabled"
        elif errors and not raw_items:
            status = "error"
        elif errors:
            status = "partial"
        else:
            status = "ok"

        result = {
            "status": status,
            "fetched": len(raw_items),
            "normalized": len(normalized),
            "inserted": inserted,
            "duplicates": max(0, len(normalized) - inserted),
            "invalid": max(0, len(raw_items) - len(normalized)),
            "deleted": deleted,
            "providers": providers_payload,
            "errors": errors,
            "refreshed_at": last_refreshed_at(db) or _to_epoch(fetched_at),
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        logger.info(
            "News refresh: status=%s fetched=%d inserted=%d errors=%d in %dms",
            status, result["fetched"], inserted, len(errors), result["duration_ms"],
        )
        return result


async def auto_refresh_loop() -> None:
    """Background worker used by the FastAPI lifespan.

    It waits a short initial delay (so app startup never blocks on the
    network), then refreshes only when the database is stale.
    """
    initial = max(5, settings.news_auto_refresh_initial_delay_seconds)
    await asyncio.sleep(initial)
    while True:
        session = SessionLocal()
        try:
            if is_stale(session):
                await refresh_news(session, force=False)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Background news refresh failed")
        finally:
            session.close()
        await asyncio.sleep(max(60, settings.news_refresh_minutes * 60))


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def serialize_article(article: NewsArticle) -> dict:
    now = _to_epoch(_utcnow()) or 0
    published = _to_epoch(article.published_at)
    age_minutes = max(0, int((now - published) / 60)) if published else None
    tickers = article.tickers if isinstance(article.tickers, list) else []
    return {
        "id": article.id,
        "headline": article.headline,
        "summary": article.summary or "",
        "summary_kind": "source_snippet" if article.summary else "none",
        "source_name": article.source_name,
        "source_domain": article.source_domain or "",
        "source_url": article.source_url,
        "published_at": published,
        "fetched_at": _to_epoch(article.fetched_at),
        "age_minutes": age_minutes,
        "region": article.region,
        "region_label": tax.REGION_LABELS.get(article.region, article.region),
        "category": article.category,
        "category_label": tax.CATEGORY_LABELS.get(article.category, article.category),
        "tickers": tickers,
        "sentiment": article.sentiment,
        "sentiment_score": article.sentiment_score,
        "sentiment_method": article.sentiment_method or "lexicon",
        "source_type": article.source_type,
        "source_type_label": tax.SOURCE_TYPE_LABELS.get(
            article.source_type, article.source_type
        ),
        "content_type": article.content_type,
        "content_type_label": tax.CONTENT_TYPE_LABELS.get(
            article.content_type, article.content_type
        ),
        "credibility_level": article.credibility_level,
        "credibility_label": tax.CREDIBILITY_LABELS.get(
            article.credibility_level, "Unknown"
        ),
        "impact_level": article.impact_level,
        "is_verified": bool(article.is_verified),
        "provider": article.provider or "",
    }


def query_articles(
    db: Session,
    *,
    region: Optional[str] = None,
    category: Optional[str] = None,
    source_type: Optional[str] = None,
    content_type: Optional[str] = None,
    sentiment: Optional[str] = None,
    ticker: Optional[str] = None,
    q: Optional[str] = None,
    min_credibility: Optional[int] = None,
    hours: Optional[int] = 168,
    sort: str = "recent",
    limit: int = 40,
    offset: int = 0,
) -> tuple[list[NewsArticle], int]:
    query = db.query(NewsArticle)
    now = _utcnow()
    if hours:
        query = query.filter(
            NewsArticle.published_at >= now - timedelta(hours=max(1, int(hours)))
        )
    if region:
        query = query.filter(NewsArticle.region == region)
    if category:
        query = query.filter(NewsArticle.category == category)
    if source_type:
        query = query.filter(NewsArticle.source_type == source_type)
    if content_type:
        query = query.filter(NewsArticle.content_type == content_type)
    if sentiment:
        query = query.filter(NewsArticle.sentiment == sentiment)
    if ticker:
        cleaned = re.sub(r"[^A-Za-z0-9&.\-]", "", ticker).upper()[:12]
        if cleaned:
            query = query.filter(NewsArticle.tickers_text.like(f"%|{cleaned}|%"))
    if q:
        pattern = f"%{q.strip()[:120]}%"
        query = query.filter(
            or_(
                NewsArticle.headline.ilike(pattern),
                NewsArticle.summary.ilike(pattern),
                NewsArticle.source_name.ilike(pattern),
            )
        )
    if min_credibility is not None:
        query = query.filter(NewsArticle.credibility_level >= min_credibility)

    total = query.count()
    if sort == "impact":
        impact_rank = case(
            (NewsArticle.impact_level == "high", 3),
            (NewsArticle.impact_level == "medium", 2),
            else_=1,
        )
        query = query.order_by(
            impact_rank.desc(),
            NewsArticle.credibility_level.desc(),
            NewsArticle.published_at.desc(),
        )
    elif sort == "credibility":
        query = query.order_by(
            NewsArticle.credibility_level.desc(),
            NewsArticle.published_at.desc(),
        )
    else:
        query = query.order_by(
            NewsArticle.published_at.desc(),
            NewsArticle.fetched_at.desc(),
        )

    rows = query.offset(max(0, offset)).limit(max(1, min(200, limit))).all()
    return rows, total


def get_counts(db: Session, hours: int = 48) -> dict:
    cutoff = _utcnow() - timedelta(hours=max(1, hours))
    base = db.query(NewsArticle).filter(NewsArticle.published_at >= cutoff)

    def grouped(column) -> list[dict]:
        rows = (
            db.query(column, func.count(NewsArticle.id))
            .filter(NewsArticle.published_at >= cutoff)
            .group_by(column)
            .order_by(desc(func.count(NewsArticle.id)))
            .all()
        )
        return [{"key": row[0], "count": row[1]} for row in rows]

    total = base.count()
    high_impact = base.filter(NewsArticle.impact_level == "high").count()
    official = base.filter(NewsArticle.source_type == "official").count()
    community = base.filter(NewsArticle.source_type == "community").count()

    return {
        "total": total,
        "high_impact": high_impact,
        "official": official,
        "community": community,
        "regions": grouped(NewsArticle.region),
        "categories": grouped(NewsArticle.category),
        "source_types": grouped(NewsArticle.source_type),
    }


def get_top_stories(db: Session, hours: int = 48, limit: int = 5) -> list[dict]:
    cutoff = _utcnow() - timedelta(hours=max(1, hours))
    impact_rank = case(
        (NewsArticle.impact_level == "high", 3),
        (NewsArticle.impact_level == "medium", 2),
        else_=1,
    )
    rows = (
        db.query(NewsArticle)
        .filter(NewsArticle.published_at >= cutoff)
        .filter(NewsArticle.source_type != "community")
        .order_by(
            impact_rank.desc(),
            NewsArticle.credibility_level.desc(),
            NewsArticle.published_at.desc(),
        )
        .limit(max(1, min(10, limit)))
        .all()
    )
    return [serialize_article(row) for row in rows]


def _sentiment_bucket(rows: Iterable[Any]) -> dict:
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    score_total = 0.0
    score_count = 0
    methods: set[str] = set()
    for row in rows:
        sentiment = row.sentiment if hasattr(row, "sentiment") else row[0]
        score = row.sentiment_score if hasattr(row, "sentiment_score") else row[1]
        method = (
            row.sentiment_method if hasattr(row, "sentiment_method") else row[2]
        )
        counts[sentiment] = counts.get(sentiment, 0) + 1
        if isinstance(score, (int, float)) and math.isfinite(float(score)):
            score_total += float(score)
            score_count += 1
        if method:
            methods.add(method)
    total = sum(counts.values())
    if total == 0:
        return {
            "bullish_pct": 0.0,
            "bearish_pct": 0.0,
            "neutral_pct": 0.0,
            "average_score": 0.0,
            "sample_size": 0,
            "method": "lexicon",
        }
    method = "lexicon" if methods <= {"lexicon"} else ("provider" if methods <= {"provider"} else "mixed")
    return {
        "bullish_pct": round(counts["bullish"] * 100 / total, 1),
        "bearish_pct": round(counts["bearish"] * 100 / total, 1),
        "neutral_pct": round(counts["neutral"] * 100 / total, 1),
        "average_score": round(score_total / score_count, 3) if score_count else 0.0,
        "sample_size": total,
        "method": method,
    }


def get_sentiment(db: Session, hours: int = 48) -> dict:
    cutoff = _utcnow() - timedelta(hours=max(1, hours))
    rows = (
        db.query(
            NewsArticle.sentiment,
            NewsArticle.sentiment_score,
            NewsArticle.sentiment_method,
            NewsArticle.region,
            NewsArticle.source_type,
        )
        .filter(NewsArticle.published_at >= cutoff)
        .all()
    )

    by_region: dict[str, list] = defaultdict(list)
    by_source_type: dict[str, list] = defaultdict(list)
    community_rows = []
    official_rows = []
    for row in rows:
        sentiment, score, method, region, source_type = row
        item = (sentiment, score, method)
        by_region[region].append(item)
        by_source_type[source_type].append(item)
        if source_type == "community":
            community_rows.append(item)
        if source_type == "official":
            official_rows.append(item)

    return {
        "window_hours": hours,
        "overall": _sentiment_bucket(rows),
        "by_region": [
            {"region": region, **_sentiment_bucket(items)}
            for region, items in sorted(
                by_region.items(), key=lambda pair: len(pair[1]), reverse=True
            )
        ],
        "by_source_type": {
            source_type: _sentiment_bucket(items)
            for source_type, items in by_source_type.items()
        },
        "community": _sentiment_bucket(community_rows),
        "official": _sentiment_bucket(official_rows),
        "generated_at": int(time.time()),
    }


def get_trending(db: Session, hours: int = 24, limit: int = 10) -> dict:
    hours = max(1, min(168, hours))
    now = _utcnow()
    current_cutoff = now - timedelta(hours=hours)
    previous_cutoff = now - timedelta(hours=hours * 2)
    rows = (
        db.query(
            NewsArticle.tickers,
            NewsArticle.sentiment,
            NewsArticle.sentiment_score,
            NewsArticle.source_type,
            NewsArticle.impact_level,
            NewsArticle.published_at,
            NewsArticle.headline,
            NewsArticle.source_name,
        )
        .filter(NewsArticle.published_at >= previous_cutoff)
        .all()
    )

    buckets: dict[str, dict] = {}
    for row in rows:
        tickers = row[0] if isinstance(row[0], list) else []
        if not tickers:
            continue
        is_current = row[5] >= current_cutoff
        for ticker in tickers:
            bucket = buckets.setdefault(
                ticker,
                {
                    "mentions": 0,
                    "previous_mentions": 0,
                    "community": 0,
                    "official": 0,
                    "bullish": 0,
                    "bearish": 0,
                    "neutral": 0,
                    "score_total": 0.0,
                    "score_count": 0,
                    "headlines": [],
                    "sources": set(),
                },
            )
            if not is_current:
                bucket["previous_mentions"] += 1
                continue
            bucket["mentions"] += 1
            bucket["sources"].add(row[7] or "")
            if row[3] == "community":
                bucket["community"] += 1
            if row[3] == "official":
                bucket["official"] += 1
            bucket[row[1]] = bucket.get(row[1], 0) + 1
            if isinstance(row[2], (int, float)) and math.isfinite(float(row[2])):
                bucket["score_total"] += float(row[2])
                bucket["score_count"] += 1
            if (
                len(bucket["headlines"]) < 2
                and row[4] in {"high", "medium"}
                and row[6]
            ):
                bucket["headlines"].append(row[6])

    total_mentions = sum(bucket["mentions"] for bucket in buckets.values()) or 1
    tickers_payload = []
    for ticker, bucket in buckets.items():
        mentions = bucket["mentions"]
        if mentions == 0:
            continue
        previous = bucket["previous_mentions"]
        delta = (
            round((mentions - previous) * 100 / previous, 1) if previous else None
        )
        if previous == 0:
            velocity = "new"
        elif (delta or 0) >= 20:
            velocity = "rising"
        elif (delta or 0) <= -20:
            velocity = "cooling"
        else:
            velocity = "steady"
        counts = {
            "bullish": bucket["bullish"],
            "bearish": bucket["bearish"],
            "neutral": bucket["neutral"],
        }
        dominant = max(counts, key=counts.get) if mentions else "neutral"
        tickers_payload.append(
            {
                "ticker": ticker,
                "mentions": mentions,
                "previous_mentions": previous,
                "delta_pct": delta,
                "velocity": velocity,
                "mention_share": round(mentions * 100 / total_mentions, 1),
                "sentiment": dominant,
                "sentiment_score": round(
                    bucket["score_total"] / bucket["score_count"], 3
                ) if bucket["score_count"] else 0.0,
                "bullish_pct": round(counts["bullish"] * 100 / mentions, 1),
                "bearish_pct": round(counts["bearish"] * 100 / mentions, 1),
                "neutral_pct": round(counts["neutral"] * 100 / mentions, 1),
                "community_mentions": bucket["community"],
                "official_mentions": bucket["official"],
                "sources": sorted(source for source in bucket["sources"] if source)[:4],
                "headlines": bucket["headlines"],
            }
        )

    tickers_payload.sort(
        key=lambda item: (item["mentions"], item["delta_pct"] or 0), reverse=True
    )
    return {
        "window_hours": hours,
        "tickers": tickers_payload[: max(1, min(25, limit))],
        "generated_at": int(time.time()),
    }


# ---------------------------------------------------------------------------
# Source / provider status
# ---------------------------------------------------------------------------

def _provider_status() -> list[dict]:
    return [
        {
            "provider": "google_news_rss",
            "label": "Google News RSS",
            "kind": "keyless",
            "enabled": settings.news_enable_google_news,
            "configured": True,
            "feeds": len(tax.GOOGLE_NEWS_FEEDS),
            "notes": "Index over publisher and official sites; the publisher is always named.",
        },
        {
            "provider": "direct_rss",
            "label": "Official RSS / Atom feeds",
            "kind": "keyless",
            "enabled": True,
            "configured": True,
            "feeds": len(tax.DIRECT_RSS_FEEDS),
            "notes": "RBI, PIB, Federal Reserve, SEC, BLS and ECB primary feeds.",
        },
        {
            "provider": "reddit",
            "label": "Reddit public JSON",
            "kind": "keyless",
            "enabled": settings.news_enable_reddit,
            "configured": True,
            "feeds": len(tax.REDDIT_SUBREDDITS),
            "notes": "Sentiment only. Check Reddit's commercial display terms before launching ads alongside it.",
        },
        {
            "provider": "marketaux",
            "label": "Marketaux",
            "kind": "free API key",
            "enabled": True,
            "configured": bool(settings.marketaux_api_key),
            "env_var": "MARKETAUX_API_KEY",
            "free_tier": "Free tier: 100 requests/day (check current terms).",
            "signup": "https://www.marketaux.com",
            "notes": "Global news with entity-level sentiment and ticker mapping.",
        },
        {
            "provider": "finnhub",
            "label": "Finnhub",
            "kind": "free API key",
            "enabled": True,
            "configured": bool(settings.finnhub_api_key),
            "env_var": "FINNHUB_API_KEY",
            "free_tier": "Free tier: 60 API calls/minute (check current terms).",
            "signup": "https://finnhub.io",
            "notes": "General market news, company news and earnings.",
        },
        {
            "provider": "alpha_vantage",
            "label": "Alpha Vantage",
            "kind": "free API key",
            "enabled": True,
            "configured": bool(settings.alpha_vantage_api_key),
            "env_var": "ALPHA_VANTAGE_API_KEY",
            "free_tier": "Free tier: 25 requests/day (check current terms).",
            "signup": "https://www.alphavantage.co/support/#api-key",
            "notes": "NEWS_SENTIMENT endpoint supplies provider sentiment and tickers.",
        },
    ]


def get_sources_status() -> dict:
    direct_domains = {feed.domain for feed in tax.DIRECT_RSS_FEEDS}
    sources = []
    for spec in tax.all_sources():
        integrations = []
        if spec.source_type == "community":
            integrations.append("reddit")
        else:
            integrations.append("google_news_rss")
        if spec.domain in direct_domains:
            integrations.append("direct_rss")
        sources.append(
            {
                "key": spec.key,
                "name": spec.name,
                "domain": spec.domain,
                "homepage": spec.homepage,
                "region": spec.region,
                "region_label": tax.REGION_LABELS.get(spec.region, spec.region),
                "source_type": spec.source_type,
                "source_type_label": tax.SOURCE_TYPE_LABELS.get(
                    spec.source_type, spec.source_type
                ),
                "content_type": spec.content_type,
                "content_type_label": tax.CONTENT_TYPE_LABELS.get(
                    spec.content_type, spec.content_type
                ),
                "credibility_level": spec.credibility_level,
                "credibility_label": spec.credibility_label,
                "integrations": integrations,
                "notes": spec.notes,
            }
        )
    sources.sort(key=lambda item: (-item["credibility_level"], item["name"].lower()))

    providers = _provider_status()
    credentials_needed = [
        {
            "provider": provider["provider"],
            "label": provider["label"],
            "env_var": provider["env_var"],
            "free_tier": provider["free_tier"],
            "signup": provider["signup"],
            "notes": provider["notes"],
        }
        for provider in providers
        if provider["kind"] == "free API key" and not provider["configured"]
    ]

    return {
        "sources": sources,
        "providers": providers,
        "credentials_needed": credentials_needed,
        "credibility_scale": tax.credibility_scale(),
        "source_type_labels": tax.SOURCE_TYPE_LABELS,
        "content_type_labels": tax.CONTENT_TYPE_LABELS,
        "notes": [
            "Only headlines, short source snippets and links are stored.",
            "Official/primary sources are the only articles marked verified.",
            "Community posts are sentiment signals, never verified news.",
            "Check each provider's redistribution terms before commercial display.",
        ],
    }

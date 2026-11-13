"""Static taxonomy for the Market News Hub.

This module owns the *rules*, not the fetching.  Every source is mapped to a
region, a source type and a credibility tier, and every headline is classified
into a category, a sentiment bucket and an impact level by an explicit,
reviewable keyword model.  Keeping it separate from the ingestion service
means the API, the tests and the documentation all describe one set of rules.

Nothing here invents news.  A missing field degrades to a conservative
``aggregator`` / ``global`` / ``markets`` classification instead of guessing.

Credibility scale
-----------------
5  Official / primary      exchange filings, regulators, central banks
4  Newswire                Reuters, Bloomberg, AP
3  Established publisher   Moneycontrol, ET, CNBC, WSJ, FT
2  Aggregator / secondary  Google News, Yahoo Finance, Investing.com, blogs
1  Community / unverified  Reddit
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlsplit

from app.services.market_data_extended import INSTRUMENT_UNIVERSE

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

REGIONS = ("india", "usa", "china", "europe", "japan", "global")

REGION_LABELS = {
    "india": "India",
    "usa": "United States",
    "china": "China",
    "europe": "Europe",
    "japan": "Japan & Asia-Pacific",
    "global": "Global",
}

CATEGORIES = (
    "markets",
    "stocks",
    "economy",
    "policy",
    "earnings",
    "forex",
    "commodities",
    "crypto",
    "geopolitics",
)

CATEGORY_LABELS = {
    "markets": "Markets",
    "stocks": "Stocks",
    "economy": "Economy",
    "policy": "Policy & central banks",
    "earnings": "Earnings",
    "forex": "Forex",
    "commodities": "Commodities",
    "crypto": "Crypto",
    "geopolitics": "Geopolitics",
}

SOURCE_TYPES = ("official", "newswire", "publisher", "aggregator", "community")

SOURCE_TYPE_LABELS = {
    "official": "Official / primary",
    "newswire": "Newswire",
    "publisher": "Publisher",
    "aggregator": "Aggregator",
    "community": "Community",
}

CONTENT_TYPES = ("report", "analysis", "opinion", "community")

CONTENT_TYPE_LABELS = {
    "report": "Report",
    "analysis": "Analysis",
    "opinion": "Opinion",
    "community": "Community post",
}

SENTIMENTS = ("bullish", "bearish", "neutral")

IMPACT_LEVELS = ("high", "medium", "low")

CREDIBILITY_LABELS = {
    5: "Official / primary",
    4: "Newswire",
    3: "Established publisher",
    2: "Aggregator / secondary",
    1: "Community / unverified",
}

CREDIBILITY_MEANINGS = {
    5: "Primary document from an exchange, regulator or central bank. Treated as a verified fact.",
    4: "Established newswire reporting. Reported, not independently verified by this app.",
    3: "Established financial publisher. Reported, not independently verified by this app.",
    2: "Aggregator, secondary summary or analyst/opinion platform.",
    1: "Community discussion. Speculation only — never presented as verified news.",
}


@dataclass(frozen=True)
class SourceSpec:
    """One known publisher, exchange, regulator or community."""

    key: str
    name: str
    domain: str
    region: str
    source_type: str
    credibility_level: int
    content_type: str = "report"
    aliases: tuple[str, ...] = ()
    homepage: str = ""
    notes: str = ""

    @property
    def credibility_label(self) -> str:
        return CREDIBILITY_LABELS.get(self.credibility_level, "Unknown")


@dataclass(frozen=True)
class GoogleNewsFeed:
    """A Google News RSS query group.

    Google News is used as a keyless *index* over the publishers' own sites:
    every item keeps its publisher name and original source link, and the
    source registry decides its credibility tier.  The query never turns a
    publisher article into an official document.
    """

    key: str
    region: str
    query: str
    when: str = "2d"
    hl: str = "en-IN"
    gl: str = "IN"
    ceid: str = "IN:en"
    max_items: int = 25
    relevant_only: bool = False


@dataclass(frozen=True)
class DirectFeed:
    """A publisher/regulator RSS or Atom feed fetched without an API key."""

    key: str
    name: str
    url: str
    domain: str
    region: str
    source_type: str
    credibility_level: int
    content_type: str = "report"
    max_items: int = 20


@dataclass(frozen=True)
class SubredditSpec:
    name: str
    region: str
    focus: str
    limit: int = 20


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

_SOURCES: tuple[SourceSpec, ...] = (
    # ---------------------------------------------------------- India: press
    SourceSpec(
        "moneycontrol", "Moneycontrol", "moneycontrol.com", "india", "publisher", 3,
        aliases=("Money Control",),
        homepage="https://www.moneycontrol.com",
    ),
    SourceSpec(
        "economic_times", "The Economic Times", "economictimes.indiatimes.com", "india",
        "publisher", 3, aliases=("Economic Times", "ET Markets", "ET"),
        homepage="https://economictimes.indiatimes.com",
    ),
    SourceSpec(
        "mint", "Mint", "livemint.com", "india", "publisher", 3,
        aliases=("LiveMint", "Mint News"), homepage="https://www.livemint.com",
    ),
    SourceSpec(
        "cnbc_tv18", "CNBC-TV18", "cnbctv18.com", "india", "publisher", 3,
        aliases=("CNBC TV18", "CNBC-TV 18", "CNBC Awaaz"),
        homepage="https://www.cnbctv18.com",
    ),
    SourceSpec(
        "business_standard", "Business Standard", "business-standard.com", "india",
        "publisher", 3, homepage="https://www.business-standard.com",
    ),
    SourceSpec(
        "financial_express", "The Financial Express", "financialexpress.com", "india",
        "publisher", 3, aliases=("Financial Express",),
        homepage="https://www.financialexpress.com",
    ),
    SourceSpec(
        "businessline", "The Hindu BusinessLine", "thehindubusinessline.com", "india",
        "publisher", 3, aliases=("BusinessLine", "Hindu BusinessLine", "The Hindu Business Line"),
        homepage="https://www.thehindubusinessline.com",
    ),
    SourceSpec(
        "ndtv_profit", "NDTV Profit", "ndtvprofit.com", "india", "publisher", 3,
        aliases=("NDTV Profit",), homepage="https://www.ndtvprofit.com",
    ),
    SourceSpec(
        "et_now", "ET Now", "etnownews.com", "india", "publisher", 3,
        aliases=("ET Now",), homepage="https://www.etnownews.com",
    ),
    SourceSpec(
        "zee_business", "Zee Business", "zeebiz.com", "india", "publisher", 3,
        homepage="https://www.zeebiz.com",
    ),
    SourceSpec(
        "bq_prime", "BQ Prime", "bqprime.com", "india", "publisher", 3,
        aliases=("BQPrime", "NDTV Profit BQ Prime"), homepage="https://www.bqprime.com",
    ),
    SourceSpec(
        "business_today", "Business Today", "businesstoday.in", "india", "publisher", 3,
        homepage="https://www.businesstoday.in",
    ),
    SourceSpec(
        "zerodha_pulse", "Zerodha Pulse", "pulse.zerodha.com", "india", "aggregator", 2,
        homepage="https://pulse.zerodha.com",
        notes="Aggregates headlines from Indian publishers; secondary source.",
    ),
    # ------------------------------------------------------- India: official
    SourceSpec(
        "nse", "NSE India", "nseindia.com", "india", "official", 5,
        aliases=("National Stock Exchange of India", "NSE"),
        homepage="https://www.nseindia.com",
        notes="Exchange announcements, corporate actions, circulars.",
    ),
    SourceSpec(
        "bse", "BSE India", "bseindia.com", "india", "official", 5,
        aliases=("Bombay Stock Exchange", "BSE"),
        homepage="https://www.bseindia.com",
        notes="Company filings, announcements and results.",
    ),
    SourceSpec(
        "sebi", "SEBI", "sebi.gov.in", "india", "official", 5,
        aliases=("Securities and Exchange Board of India",),
        homepage="https://www.sebi.gov.in",
        notes="Regulations, investigations and investor alerts.",
    ),
    SourceSpec(
        "rbi", "Reserve Bank of India", "rbi.org.in", "india", "official", 5,
        aliases=("RBI", "Reserve Bank of India"),
        homepage="https://www.rbi.org.in",
        notes="Repo rate, monetary policy, banking and inflation.",
    ),
    SourceSpec(
        "ministry_of_finance", "Ministry of Finance", "finmin.nic.in", "india",
        "official", 5, aliases=("Finance Ministry",),
        homepage="https://www.finmin.nic.in",
    ),
    SourceSpec(
        "pib", "Press Information Bureau", "pib.gov.in", "india", "official", 5,
        aliases=("PIB",), homepage="https://pib.gov.in",
    ),
    SourceSpec(
        "niti_aayog", "NITI Aayog", "niti.gov.in", "india", "official", 5,
        homepage="https://www.niti.gov.in",
    ),
    SourceSpec(
        "amfi", "AMFI", "amfiindia.com", "india", "official", 5,
        aliases=("Association of Mutual Funds in India",),
        homepage="https://www.amfiindia.com",
    ),
    SourceSpec(
        "india_budget", "Union Budget", "indiabudget.gov.in", "india", "official", 5,
        homepage="https://www.indiabudget.gov.in",
    ),
    # ----------------------------------------------------- US / global press
    SourceSpec(
        "reuters", "Reuters", "reuters.com", "global", "newswire", 4,
        aliases=("Reuters Markets", "Reuters Business"),
        homepage="https://www.reuters.com/markets",
    ),
    SourceSpec(
        "bloomberg", "Bloomberg", "bloomberg.com", "global", "newswire", 4,
        aliases=("Bloomberg Markets", "Bloomberg News"),
        homepage="https://www.bloomberg.com/markets",
    ),
    SourceSpec(
        "ap", "Associated Press", "apnews.com", "global", "newswire", 4,
        aliases=("AP", "AP News"), homepage="https://apnews.com",
    ),
    SourceSpec(
        "cnbc", "CNBC", "cnbc.com", "usa", "publisher", 3,
        aliases=("CNBC Markets", "CNBC US"), homepage="https://www.cnbc.com/markets",
    ),
    SourceSpec(
        "wsj", "The Wall Street Journal", "wsj.com", "usa", "publisher", 3,
        aliases=("Wall Street Journal", "WSJ", "WSJ Markets"),
        homepage="https://www.wsj.com/finance",
    ),
    SourceSpec(
        "marketwatch", "MarketWatch", "marketwatch.com", "usa", "publisher", 3,
        homepage="https://www.marketwatch.com",
    ),
    SourceSpec(
        "barrons", "Barron's", "barrons.com", "usa", "publisher", 3,
        homepage="https://www.barrons.com",
    ),
    SourceSpec(
        "ft", "Financial Times", "ft.com", "europe", "publisher", 3,
        aliases=("FT", "Financial Times Markets"),
        homepage="https://www.ft.com/markets",
    ),
    # ------------------------------------------------------- US: official
    SourceSpec(
        "federal_reserve", "Federal Reserve", "federalreserve.gov", "usa", "official", 5,
        aliases=("Fed", "Board of Governors of the Federal Reserve System", "FOMC"),
        homepage="https://www.federalreserve.gov",
        notes="Interest rates, FOMC decisions and monetary policy.",
    ),
    SourceSpec(
        "sec", "U.S. Securities and Exchange Commission", "sec.gov", "usa", "official", 5,
        aliases=("SEC", "US SEC", "EDGAR"), homepage="https://www.sec.gov",
        notes="Company filings, 10-K/10-Q and enforcement releases.",
    ),
    SourceSpec(
        "nasdaq", "Nasdaq", "nasdaq.com", "usa", "official", 5,
        aliases=("NASDAQ", "Nasdaq Exchange"), homepage="https://www.nasdaq.com",
    ),
    SourceSpec(
        "nyse", "New York Stock Exchange", "nyse.com", "usa", "official", 5,
        aliases=("NYSE",), homepage="https://www.nyse.com",
    ),
    SourceSpec(
        "us_treasury", "U.S. Department of the Treasury", "treasury.gov", "usa",
        "official", 5, aliases=("US Treasury", "Treasury Department"),
        homepage="https://home.treasury.gov",
    ),
    SourceSpec(
        "bls", "Bureau of Labor Statistics", "bls.gov", "usa", "official", 5,
        aliases=("BLS",), homepage="https://www.bls.gov",
        notes="CPI, employment and inflation releases.",
    ),
    SourceSpec(
        "bea", "Bureau of Economic Analysis", "bea.gov", "usa", "official", 5,
        aliases=("BEA",), homepage="https://www.bea.gov",
    ),
    # -------------------------------------------------------------- China
    SourceSpec(
        "xinhua", "Xinhua", "news.cn", "china", "publisher", 3,
        aliases=("Xinhua News Agency", "English News"), homepage="https://english.news.cn",
    ),
    SourceSpec(
        "china_daily", "China Daily", "chinadaily.com.cn", "china", "publisher", 3,
        homepage="https://www.chinadaily.com.cn",
    ),
    SourceSpec(
        "pboc", "People's Bank of China", "pbc.gov.cn", "china", "official", 5,
        aliases=("PBOC", "PBoC"), homepage="http://www.pbc.gov.cn",
    ),
    SourceSpec(
        "sse", "Shanghai Stock Exchange", "sse.com.cn", "china", "official", 5,
        aliases=("SSE",), homepage="http://www.sse.com.cn",
    ),
    SourceSpec(
        "szse", "Shenzhen Stock Exchange", "szse.cn", "china", "official", 5,
        aliases=("SZSE",), homepage="http://www.szse.cn",
    ),
    # ------------------------------------------------------------- Europe
    SourceSpec(
        "ecb", "European Central Bank", "ecb.europa.eu", "europe", "official", 5,
        aliases=("ECB",), homepage="https://www.ecb.europa.eu",
        notes="Rate decisions, monetary policy and banking supervision.",
    ),
    SourceSpec(
        "euronext", "Euronext", "euronext.com", "europe", "official", 5,
        homepage="https://www.euronext.com",
    ),
    SourceSpec(
        "deutsche_boerse", "Deutsche Börse", "deutsche-boerse.com", "europe",
        "official", 5, aliases=("Deutsche Boerse", "Deutsche Borse"),
        homepage="https://www.deutsche-boerse.com",
    ),
    SourceSpec(
        "bank_of_england", "Bank of England", "bankofengland.co.uk", "europe",
        "official", 5, aliases=("BoE", "BOE"), homepage="https://www.bankofengland.co.uk",
    ),
    SourceSpec(
        "european_commission", "European Commission", "ec.europa.eu", "europe",
        "official", 5, homepage="https://ec.europa.eu",
    ),
    SourceSpec(
        "lse", "London Stock Exchange", "londonstockexchange.com", "europe",
        "official", 5, aliases=("LSE",), homepage="https://www.londonstockexchange.com",
    ),
    # ------------------------------------------------------- Japan / APAC
    SourceSpec(
        "nikkei_asia", "Nikkei Asia", "asia.nikkei.com", "japan", "publisher", 3,
        homepage="https://asia.nikkei.com",
    ),
    SourceSpec(
        "nikkei", "Nikkei", "nikkei.com", "japan", "publisher", 3,
        homepage="https://www.nikkei.com",
    ),
    SourceSpec(
        "jpx", "Japan Exchange Group", "jpx.co.jp", "japan", "official", 5,
        aliases=("JPX", "Tokyo Stock Exchange"), homepage="https://www.jpx.co.jp",
    ),
    SourceSpec(
        "mas", "Monetary Authority of Singapore", "mas.gov.sg", "japan", "official", 5,
        aliases=("MAS",), homepage="https://www.mas.gov.sg",
    ),
    SourceSpec(
        "asx", "Australian Securities Exchange", "asx.com.au", "japan", "official", 5,
        aliases=("ASX",), homepage="https://www2.asx.com.au",
    ),
    SourceSpec(
        "hkex", "Hong Kong Exchanges and Clearing", "hkex.com.hk", "japan", "official", 5,
        aliases=("HKEX",), homepage="https://www.hkex.com.hk",
    ),
    # ------------------------------------------------- Other intelligence
    SourceSpec(
        "coindesk", "CoinDesk", "coindesk.com", "global", "publisher", 3,
        homepage="https://www.coindesk.com",
    ),
    SourceSpec(
        "cointelegraph", "Cointelegraph", "cointelegraph.com", "global", "publisher", 3,
        homepage="https://cointelegraph.com",
    ),
    SourceSpec(
        "decrypt", "Decrypt", "decrypt.co", "global", "publisher", 3,
        homepage="https://decrypt.co",
    ),
    SourceSpec(
        "investing", "Investing.com", "investing.com", "global", "aggregator", 2,
        homepage="https://www.investing.com",
    ),
    SourceSpec(
        "yahoo_finance", "Yahoo Finance", "finance.yahoo.com", "global", "aggregator", 2,
        homepage="https://finance.yahoo.com",
    ),
    SourceSpec(
        "seeking_alpha", "Seeking Alpha", "seekingalpha.com", "global", "aggregator", 2,
        content_type="analysis", homepage="https://seekingalpha.com",
    ),
    SourceSpec(
        "tradingview", "TradingView", "tradingview.com", "global", "aggregator", 2,
        content_type="opinion", homepage="https://www.tradingview.com",
    ),
    SourceSpec(
        "kobeissi", "The Kobeissi Letter", "thekobeissiletter.com", "global",
        "publisher", 2, content_type="analysis",
        homepage="https://thekobeissiletter.com",
    ),
    SourceSpec(
        "glassnode", "Glassnode", "glassnode.com", "global", "aggregator", 2,
        content_type="analysis", homepage="https://glassnode.com",
    ),
    SourceSpec(
        "kitco", "Kitco", "kitco.com", "global", "publisher", 3,
        homepage="https://www.kitco.com",
    ),
    SourceSpec(
        "oilprice", "OilPrice.com", "oilprice.com", "global", "publisher", 3,
        homepage="https://oilprice.com",
    ),
    # --------------------------------------------------------- Community
    SourceSpec(
        "reddit", "Reddit", "reddit.com", "global", "community", 1,
        content_type="community", aliases=("Reddit",),
        homepage="https://www.reddit.com",
        notes="Public JSON. Sentiment only; never presented as verified news.",
    ),
)


# ---------------------------------------------------------------------------
# Feed definitions
# ---------------------------------------------------------------------------

GOOGLE_NEWS_FEEDS: tuple[GoogleNewsFeed, ...] = (
    GoogleNewsFeed(
        "india_publishers",
        "india",
        "("
        "site:moneycontrol.com OR site:economictimes.indiatimes.com OR "
        "site:livemint.com OR site:cnbctv18.com OR site:business-standard.com OR "
        "site:financialexpress.com OR site:thehindubusinessline.com OR "
        "site:ndtvprofit.com OR site:etnownews.com OR site:zeebiz.com OR "
        "site:bqprime.com OR site:businesstoday.in"
        ") when:2d",
        max_items=30,
    ),
    GoogleNewsFeed(
        "india_official",
        "india",
        "("
        "site:nseindia.com OR site:bseindia.com OR site:sebi.gov.in OR "
        "site:rbi.org.in OR site:pib.gov.in OR site:finmin.nic.in OR "
        "site:niti.gov.in OR site:amfiindia.com OR site:indiabudget.gov.in"
        ") when:7d",
        max_items=30,
    ),
    GoogleNewsFeed(
        "us_publishers",
        "usa",
        "("
        "site:reuters.com OR site:bloomberg.com OR site:cnbc.com OR site:wsj.com OR "
        "site:ft.com OR site:marketwatch.com OR site:barrons.com OR site:apnews.com"
        ") when:2d",
        hl="en-US",
        gl="US",
        ceid="US:en",
        max_items=30,
    ),
    GoogleNewsFeed(
        "us_official",
        "usa",
        "("
        "site:federalreserve.gov OR site:sec.gov OR site:treasury.gov OR "
        "site:bls.gov OR site:bea.gov OR site:nasdaq.com OR site:nyse.com"
        ") when:7d",
        hl="en-US",
        gl="US",
        ceid="US:en",
        max_items=30,
    ),
    GoogleNewsFeed(
        "china",
        "china",
        "("
        "site:news.cn OR site:chinadaily.com.cn OR site:pbc.gov.cn OR "
        "site:sse.com.cn OR site:szse.cn"
        ") when:3d",
        hl="en-US",
        gl="US",
        ceid="US:en",
        max_items=25,
    ),
    GoogleNewsFeed(
        "europe",
        "europe",
        "("
        "site:ecb.europa.eu OR site:euronext.com OR site:deutsche-boerse.com OR "
        "site:bankofengland.co.uk OR site:ft.com OR site:europa.eu"
        ") when:2d",
        hl="en-GB",
        gl="GB",
        ceid="GB:en",
        max_items=25,
    ),
    GoogleNewsFeed(
        "japan_apac",
        "japan",
        "("
        "site:asia.nikkei.com OR site:nikkei.com OR site:jpx.co.jp OR "
        "site:mas.gov.sg OR site:asx.com.au OR site:hkex.com.hk"
        ") when:3d",
        hl="en-US",
        gl="US",
        ceid="US:en",
        max_items=25,
    ),
    GoogleNewsFeed(
        "global_macro",
        "global",
        '("gold price" OR "crude oil" OR "bond yields" OR "dollar index" OR '
        '"forex market" OR "central bank") when:1d',
        hl="en-US",
        gl="US",
        ceid="US:en",
        max_items=25,
        relevant_only=True,
    ),
    GoogleNewsFeed(
        "crypto",
        "global",
        "("
        "site:coindesk.com OR site:cointelegraph.com OR site:decrypt.co OR "
        "site:glassnode.com"
        ") when:2d",
        hl="en-US",
        gl="US",
        ceid="US:en",
        max_items=20,
    ),
    GoogleNewsFeed(
        "other_intelligence",
        "global",
        "("
        "site:investing.com OR site:seekingalpha.com OR site:tradingview.com OR "
        "site:finance.yahoo.com OR site:thekobeissiletter.com OR site:kitco.com OR "
        "site:oilprice.com"
        ") when:2d",
        hl="en-US",
        gl="US",
        ceid="US:en",
        max_items=25,
        relevant_only=True,
    ),
)


DIRECT_RSS_FEEDS: tuple[DirectFeed, ...] = (
    DirectFeed(
        "rbi_press", "Reserve Bank of India",
        "https://www.rbi.org.in/pressreleases_rss.xml", "rbi.org.in",
        "india", "official", 5,
    ),
    DirectFeed(
        "rbi_notifications", "Reserve Bank of India",
        "https://www.rbi.org.in/notifications_rss.xml", "rbi.org.in",
        "india", "official", 5,
    ),
    DirectFeed(
        "pib", "Press Information Bureau",
        "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "pib.gov.in",
        "india", "official", 5,
    ),
    DirectFeed(
        "federal_reserve", "Federal Reserve",
        "https://www.federalreserve.gov/feeds/press_all.xml", "federalreserve.gov",
        "usa", "official", 5,
    ),
    DirectFeed(
        "sec", "U.S. Securities and Exchange Commission",
        "https://www.sec.gov/news/pressreleases.rss", "sec.gov",
        "usa", "official", 5,
    ),
    DirectFeed(
        "bls", "Bureau of Labor Statistics",
        "https://www.bls.gov/feed/bls_latest.rss", "bls.gov",
        "usa", "official", 5,
    ),
    DirectFeed(
        "ecb", "European Central Bank",
        "https://www.ecb.europa.eu/rss/press.html", "ecb.europa.eu",
        "europe", "official", 5,
    ),
)


REDDIT_SUBREDDITS: tuple[SubredditSpec, ...] = (
    SubredditSpec("IndianStockMarket", "india", "Indian retail investors"),
    SubredditSpec("IndiaInvestments", "india", "Indian investing and personal finance"),
    SubredditSpec("IndianStreetBets", "india", "Indian trading discussions"),
    SubredditSpec("NSEbets", "india", "NSE stock trading"),
    SubredditSpec("WallStreetBets", "usa", "Retail trading and speculative stocks"),
    SubredditSpec("stocks", "usa", "US stock discussions"),
    SubredditSpec("investing", "global", "Long-term investing"),
    SubredditSpec("SecurityAnalysis", "global", "Fundamental analysis"),
    SubredditSpec("options", "usa", "Options trading"),
    SubredditSpec("StockMarket", "usa", "General market discussions"),
    SubredditSpec("Forex", "global", "Forex trading"),
    SubredditSpec("CryptoCurrency", "global", "Cryptocurrency"),
)


# ---------------------------------------------------------------------------
# Ticker dictionaries
# ---------------------------------------------------------------------------

GLOBAL_INSTRUMENTS: tuple[dict[str, str], ...] = (
    {"symbol": "AAPL", "name": "Apple"},
    {"symbol": "MSFT", "name": "Microsoft"},
    {"symbol": "NVDA", "name": "NVIDIA"},
    {"symbol": "TSLA", "name": "Tesla"},
    {"symbol": "AMZN", "name": "Amazon"},
    {"symbol": "GOOGL", "name": "Alphabet"},
    {"symbol": "GOOG", "name": "Google"},
    {"symbol": "META", "name": "Meta Platforms"},
    {"symbol": "AMD", "name": "Advanced Micro Devices"},
    {"symbol": "NFLX", "name": "Netflix"},
    {"symbol": "INTC", "name": "Intel"},
    {"symbol": "ORCL", "name": "Oracle"},
    {"symbol": "CRM", "name": "Salesforce"},
    {"symbol": "JPM", "name": "JPMorgan Chase"},
    {"symbol": "BAC", "name": "Bank of America"},
    {"symbol": "GS", "name": "Goldman Sachs"},
    {"symbol": "MS", "name": "Morgan Stanley"},
    {"symbol": "C", "name": "Citigroup"},
    {"symbol": "BRK.B", "name": "Berkshire Hathaway"},
    {"symbol": "V", "name": "Visa"},
    {"symbol": "MA", "name": "Mastercard"},
    {"symbol": "WMT", "name": "Walmart"},
    {"symbol": "DIS", "name": "Walt Disney"},
    {"symbol": "BA", "name": "Boeing"},
    {"symbol": "XOM", "name": "Exxon Mobil"},
    {"symbol": "CVX", "name": "Chevron"},
    {"symbol": "SPY", "name": "S&P 500 ETF"},
    {"symbol": "QQQ", "name": "Nasdaq 100 ETF"},
    {"symbol": "VIX", "name": "Volatility Index"},
    {"symbol": "BTC", "name": "Bitcoin"},
    {"symbol": "ETH", "name": "Ethereum"},
    {"symbol": "SOL", "name": "Solana"},
    {"symbol": "XAU", "name": "Gold"},
    {"symbol": "XAG", "name": "Silver"},
    {"symbol": "WTI", "name": "WTI Crude"},
    {"symbol": "BRENT", "name": "Brent Crude"},
)


# ---------------------------------------------------------------------------
# Indexes and helpers
# ---------------------------------------------------------------------------

_NSE_BY_SYMBOL = {item["symbol"]: item for item in INSTRUMENT_UNIVERSE}
_NSE_NAME_MATCHES = [
    (item["name"].lower(), item["symbol"])
    for item in INSTRUMENT_UNIVERSE
    if len(item["name"]) >= 4
]
_GLOBAL_BY_SYMBOL = {item["symbol"]: item for item in GLOBAL_INSTRUMENTS}
_GLOBAL_NAME_MATCHES = [
    (item["name"].lower(), item["symbol"])
    for item in GLOBAL_INSTRUMENTS
    if len(item["name"]) >= 4
]
_GLOBAL_SYMBOLS = set(_GLOBAL_BY_SYMBOL)


def _name_key(value: str) -> str:
    """Lowercase ASCII key so ``Deutsche Börse`` and ``Deutsche Boerse`` match."""
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


_DOMAIN_TO_SPEC = {spec.domain: spec for spec in _SOURCES}
_ALIAS_TO_SPEC: dict[str, SourceSpec] = {}
for _spec in _SOURCES:
    _ALIAS_TO_SPEC[_name_key(_spec.name)] = _spec
    for _alias in _spec.aliases:
        _ALIAS_TO_SPEC.setdefault(_name_key(_alias), _spec)

_GOV_SUFFIXES = (
    ".gov", ".gov.in", ".gov.cn", ".gov.uk", ".gov.au", ".gov.sg", ".gov.hk",
    ".nic.in", ".europa.eu", ".mil",
)


def domain_from_url(url: str) -> str:
    """Return a bare lowercase hostname, or ``""`` for a non-URL."""
    value = (url or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    try:
        host = urlsplit(value).hostname or ""
    except ValueError:
        return ""
    host = host.lower().strip(".")
    for prefix in ("www.", "m.", "amp.", "edition."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def _domain_matches(host: str, known: str) -> bool:
    return bool(host and known and (host == known or host.endswith("." + known)))


def _region_from_domain(host: str) -> str:
    if host.endswith(".in") or host.endswith(".nic.in"):
        return "india"
    if host.endswith(".cn"):
        return "china"
    if host.endswith(".uk"):
        return "europe"
    if host.endswith(".jp"):
        return "japan"
    if host.endswith((".au", ".sg", ".hk", ".nz")):
        return "japan"
    return "global"


def source_for(source_name: str = "", source_url: str = "") -> SourceSpec:
    """Resolve a publisher name/URL to its registry entry.

    Unknown sources are never promoted.  A recognised government domain gets
    the official tier; an unknown publisher gets the secondary tier; a bare
    name with no domain gets the aggregator tier.
    """
    host = domain_from_url(source_url)
    if host:
        for spec in _SOURCES:
            if _domain_matches(host, spec.domain):
                return spec

    key = _name_key(source_name)
    if key:
        exact = _ALIAS_TO_SPEC.get(key)
        if exact is not None:
            return exact
        for alias, spec in _ALIAS_TO_SPEC.items():
            # Short aliases ("FT", "AP") only match exactly.  Longer aliases
            # tolerate suffixes such as "Reuters - Markets".
            if len(alias) >= 6 and (alias in key or key in alias):
                return spec

    display = (source_name or "").strip() or host or "Unknown source"
    if host and any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in _GOV_SUFFIXES):
        return SourceSpec(
            key=f"official:{host}",
            name=display,
            domain=host,
            region=_region_from_domain(host),
            source_type="official",
            credibility_level=5,
        )

    if host and key:
        return SourceSpec(
            key=f"secondary:{host}",
            name=display,
            domain=host,
            region=_region_from_domain(host),
            source_type="aggregator",
            credibility_level=2,
        )

    return SourceSpec(
        key=f"secondary:{host or key or 'unknown'}",
        name=display,
        domain=host,
        region=_region_from_domain(host) if host else "global",
        source_type="aggregator",
        credibility_level=2,
    )


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

_REGION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "india": (
        "india", "indian", "nifty", "sensex", "bse", "nse", "rbi", "sebi",
        "rupee", "dalal street", "mumbai", "modi", "gst", "sebi", "nse",
        "bank nifty", "mutual fund", "fii", "dii",
    ),
    "usa": (
        "united states", "u.s.", "us ", "america", "american", "wall street",
        "federal reserve", "fed ", "fomc", "nasdaq", "s&p 500", "dow jones",
        "treasury", "sec ", "washington", "dollar", "silicon valley",
    ),
    "china": (
        "china", "chinese", "shanghai", "shenzhen", "pboc", "yuan", "renminbi",
        "beijing", "xi jinping", "hang seng", "hong kong",
    ),
    "europe": (
        "europe", "european", "eurozone", "ecb", "euro", "germany", "german",
        "dax", "cac 40", "ftse", "france", "french", "uk ", "britain", "british",
        "bank of england", "london", "brussels", "lagarde",
    ),
    "japan": (
        "japan", "japanese", "nikkei", "tokyo", "yen", "boj", "bank of japan",
        "korea", "kospi", "singapore", "australia", "asx", "asia-pacific",
        "asia pacific", "taiwan", "semiconductor",
    ),
}


def _keyword_score(text: str, keywords: Iterable[str]) -> int:
    lowered = text.lower()
    score = 0
    for keyword in keywords:
        if keyword in lowered:
            score += 1
    return score


def classify_region(headline: str, summary: str = "", default: str = "global") -> str:
    """Pick a region from explicit keywords; fall back to the feed's hint."""
    text = f"{headline} {summary}"
    scores = {region: _keyword_score(text, words) for region, words in _REGION_KEYWORDS.items()}
    best_score = max(scores.values(), default=0)
    if best_score <= 0:
        return default if default in REGIONS else "global"
    winners = [region for region, score in scores.items() if score == best_score]
    if len(winners) == 1:
        return winners[0]
    # A genuine tie is usually a cross-market story.  Prefer the feed hint
    # when it is one of the tied regions, otherwise report it as global.
    if default in winners:
        return default
    return "global"


_CATEGORY_KEYWORDS: dict[str, dict[str, float]] = {
    "crypto": {
        "bitcoin": 3, "ethereum": 3, "crypto": 3, "cryptocurrency": 3,
        "blockchain": 2, "stablecoin": 2, "defi": 2, "token": 1, "coinbase": 2,
        "binance": 2, "nft": 2, "digital asset": 2, "ether": 2, "solana": 2,
    },
    "commodities": {
        "gold": 2, "silver": 2, "crude": 3, "oil price": 3, "brent": 3,
        "wti": 3, "natural gas": 3, "copper": 2, "commodity": 2, "opec": 3,
        "wheat": 2, "corn": 1, "bullion": 2,
    },
    "forex": {
        "rupee": 2, "dollar": 2, "euro": 2, "yen": 2, "yuan": 2, "pound": 2,
        "currency": 2, "forex": 3, "exchange rate": 2, "dollar index": 3,
        "dxy": 3, "greenback": 2,
    },
    "policy": {
        "rbi": 3, "sebi": 3, "federal reserve": 3, "fed": 2, "fomc": 3,
        "ecb": 3, "bank of england": 3, "pboc": 3, "central bank": 3,
        "monetary policy": 3, "rate cut": 3, "rate hike": 3, "repo rate": 3,
        "interest rate": 2, "regulation": 2, "regulator": 2, "government": 1,
        "parliament": 1, "budget": 2, "tax": 1, "gst": 2, "subsidy": 2,
        "tariff": 2, "sanction": 2, "policy": 2, "stimulus": 2,
    },
    "earnings": {
        "earnings": 3, "results": 2, "quarterly": 2, "q1": 2, "q2": 2, "q3": 2,
        "q4": 2, "profit": 2, "revenue": 2, "net income": 2, "margin": 1,
        "guidance": 2, "dividend": 2, "buyback": 2, "eps": 2,
    },
    "stocks": {
        "ipo": 3, "listing": 2, "shares": 2, "stock": 1, "stake": 2,
        "merger": 2, "acquisition": 2, "takeover": 2, "demerger": 2,
        "block deal": 2, "upper circuit": 2, "lower circuit": 2,
        "bonus issue": 2, "stock split": 2, "delisting": 2, "equity": 1,
    },
    "economy": {
        "gdp": 3, "inflation": 3, "cpi": 3, "wpi": 3, "pmi": 2,
        "unemployment": 2, "jobs report": 2, "trade deficit": 3,
        "fiscal deficit": 3, "current account": 2, "industrial production": 2,
        "retail sales": 2, "recession": 3, "economic growth": 2, "economy": 1,
    },
    "geopolitics": {
        "war": 3, "conflict": 2, "sanctions": 2, "election": 2, "missile": 3,
        "ceasefire": 3, "trade war": 3, "nato": 2, "taiwan": 2, "ukraine": 2,
        "israel": 2, "gaza": 2, "red sea": 3, "geopolitical": 3, "border": 1,
    },
    "markets": {
        "stock market": 1, "equity market": 1, "index": 1, "rally": 1,
        "selloff": 1, "sell-off": 1, "wall street": 1, "sensex": 1,
        "nifty": 1, "nasdaq": 1, "s&p 500": 1, "dow jones": 1, "ftse": 1,
        "dax": 1, "cac 40": 1, "hang seng": 1, "nikkei": 1,
    },
}

_CATEGORY_TIE_ORDER = (
    "crypto", "commodities", "forex", "policy", "earnings", "economy",
    "geopolitics", "stocks", "markets",
)


def classify_category(headline: str, summary: str = "") -> str:
    """Score keyword groups and return the strongest category."""
    text = f"{headline} {summary}".lower()
    scores: dict[str, float] = {}
    for category, terms in _CATEGORY_KEYWORDS.items():
        scores[category] = sum(weight for term, weight in terms.items() if term in text)
    best = max(scores.values(), default=0)
    if best <= 0:
        return "markets"
    for category in _CATEGORY_TIE_ORDER:
        if scores.get(category, 0) == best:
            return category
    return "markets"


# ---------------------------------------------------------------------------
# Sentiment (deterministic lexicon)
# ---------------------------------------------------------------------------

_POSITIVE_TERMS: dict[str, float] = {
    "surge": 2.0, "soar": 2.0, "skyrocket": 2.0, "rally": 1.5, "jump": 1.5,
    "gain": 1.0, "gains": 1.0, "rise": 1.0, "rises": 1.0, "climb": 1.0,
    "record high": 2.0, "all-time high": 2.0, "outperform": 1.5,
    "upgrade": 1.5, "beat": 1.5, "beats": 1.5, "strong": 1.0,
    "growth": 1.0, "profit": 1.0, "profits": 1.0, "positive": 1.0,
    "bullish": 2.0, "optimism": 1.0, "optimistic": 1.0, "recovery": 1.0,
    "rebound": 1.5, "approval": 1.0, "approved": 1.0, "rate cut": 2.0,
    "rate cuts": 2.0, "repo rate cut": 2.5, "cuts repo rate": 2.5,
    "cuts rates": 2.5, "policy easing": 2.0, "easing cycle": 1.5,
    "stimulus": 1.5, "expansion": 1.0, "inflows": 1.0, "buyback": 1.0,
    "dividend": 1.0, "record profit": 2.0, "beat estimates": 2.0,
    "raised guidance": 2.0, "upgraded": 1.5, "breakout": 1.0,
}

_NEGATIVE_TERMS: dict[str, float] = {
    "fall": 1.0, "falls": 1.0, "drop": 1.0, "drops": 1.0, "slump": 1.5,
    "plunge": 2.0, "plunges": 2.0, "crash": 2.5, "tumble": 1.5,
    "decline": 1.0, "declines": 1.0, "loss": 1.0, "losses": 1.0,
    "downgrade": 1.5, "downgraded": 1.5, "miss": 1.5, "misses": 1.5,
    "weak": 1.0, "weakness": 1.0, "warning": 1.0, "warns": 1.0,
    "bearish": 2.0, "pessimism": 1.0, "recession": 2.0, "default": 2.5,
    "bankruptcy": 2.5, "fraud": 2.5, "probe": 1.5, "investigation": 1.5,
    "layoff": 1.5, "layoffs": 1.5, "rate hike": 2.0, "rate hikes": 2.0,
    "hikes rates": 2.5, "repo rate hike": 2.5, "inflation": 1.0,
    "sell-off": 2.0, "selloff": 2.0, "crash ": 2.5, "record low": 2.0,
    "profit warning": 2.5, "missed estimates": 2.0, "cut guidance": 2.0,
    "downgraded to": 2.0, "war": 2.0, "sanction": 1.5, "sanctions": 1.5,
    "tariff": 1.5, "tariffs": 1.5, "halt": 1.5, "ban": 1.5, "probe ": 1.5,
    "resign": 1.0, "resignation": 1.0, "shutdown": 1.5, "outage": 1.5,
}

_NEGATIONS = re.compile(r"\b(not|no|never|unlikely|denies|denied|without|fails to)\b", re.I)
_TERM_PATTERNS: dict[str, re.Pattern] = {}


def _term_pattern(term: str) -> re.Pattern:
    pattern = _TERM_PATTERNS.get(term)
    if pattern is None:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", re.I)
        _TERM_PATTERNS[term] = pattern
    return pattern


def _weighted_hits(text: str, terms: dict[str, float]) -> float:
    """Sum term weights, flipping a hit when it is negated nearby."""
    total = 0.0
    for term, weight in terms.items():
        for match in _term_pattern(term).finditer(text):
            before = text[max(0, match.start() - 32):match.start()]
            total += -weight if _NEGATIONS.search(before) else weight
    return total


def score_sentiment(headline: str, summary: str = "") -> tuple[str, float]:
    """Return ``(label, score)`` from a deterministic finance lexicon.

    Scores are normalised to roughly ``[-1, 1]``.  A neutral zone keeps the
    label honest when a headline only contains one weak directional word.
    """
    text = f"{headline} {summary}".strip()
    if not text:
        return "neutral", 0.0
    positive = _weighted_hits(text, _POSITIVE_TERMS)
    negative = _weighted_hits(text, _NEGATIVE_TERMS)
    raw = positive - negative
    denominator = positive + negative + 2.0
    score = max(-1.0, min(1.0, raw / denominator))
    if score >= 0.12:
        label = "bullish"
    elif score <= -0.12:
        label = "bearish"
    else:
        label = "neutral"
        score = 0.0 if abs(score) < 0.05 else score
    return label, round(score, 3)


def sentiment_from_score(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# Impact
# ---------------------------------------------------------------------------

_HIGH_IMPACT_TERMS = (
    "rate cut", "rate hike", "repo rate", "monetary policy", "fomc",
    "interest rate", "inflation", "cpi", "gdp", "budget", "stimulus",
    "sanction", "tariff", "war", "ceasefire", "default", "bankruptcy",
    "fraud", "probe", "merger", "acquisition", "takeover", "ipo",
    "earnings", "results", "dividend", "buyback", "crash", "plunge",
    "surge", "record high", "record low", "circuit", "halt", "ban",
    "resign", "resignation", "emergency", "delisting", "insolvency",
)


def _contains_high_impact(text: str) -> bool:
    lowered = text.lower()
    return any(
        _term_pattern(term).search(lowered) is not None
        for term in _HIGH_IMPACT_TERMS
    )


def classify_impact(
    source_type: str,
    credibility_level: int,
    category: str,
    headline: str,
    tickers: Optional[list[str]] = None,
) -> str:
    """Impact is a coarse market-moving flag, not a prediction."""
    if source_type == "community":
        return "low"
    text = headline or ""
    high_signal = _contains_high_impact(text)
    if credibility_level >= 5:
        if category in {"policy", "economy", "earnings", "stocks"} or high_signal:
            return "high"
        return "medium"
    if credibility_level == 4:
        return "high" if high_signal else "medium"
    if credibility_level == 3:
        if category in {"policy", "economy", "earnings", "stocks"} or high_signal:
            return "medium"
        return "low"
    if high_signal and (tickers or category in {"policy", "economy", "crypto"}):
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Tickers
# ---------------------------------------------------------------------------

_TICKER_TOKEN = re.compile(r"(?<![A-Za-z0-9&])([A-Z][A-Z0-9&.\-]{1,14})(?![A-Za-z0-9&])")
_CASHTAG = re.compile(r"\$([A-Za-z][A-Za-z0-9.\-]{0,11})")
_TICKER_SUFFIX_RE = re.compile(r"(\.(NS|BO|BSE|NSE|US|NASDAQ|NYSE|LSE|TO|HK|T))$")
_TICKER_PREFIX_RE = re.compile(r"^(NASDAQ|NYSE|NSE|BSE|AMEX|NYSEARCA)\s*:\s*")
_TICKER_ALIASES = {
    "BTC-USD": "BTC", "BTCUSD": "BTC", "XBT": "BTC",
    "ETH-USD": "ETH", "ETHUSD": "ETH",
    "SOL-USD": "SOL", "SOLUSD": "SOL",
    "XAUUSD": "XAU", "XAU-USD": "XAU",
    "XAGUSD": "XAG", "XAG-USD": "XAG",
    "CL=F": "WTI", "WTI-USD": "WTI", "BRENT-USD": "BRENT",
    "BRK-B": "BRK.B",
}


def normalize_ticker(value: object) -> Optional[str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    raw = _TICKER_PREFIX_RE.sub("", raw)
    raw = _TICKER_SUFFIX_RE.sub("", raw)
    raw = raw.strip(" .,:;|")
    if raw in _TICKER_ALIASES:
        return _TICKER_ALIASES[raw]
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9&.\-]{0,11}", raw):
        return None
    return raw


def _add_ticker(found: list[str], value: object) -> None:
    ticker = normalize_ticker(value)
    if not ticker:
        return
    # Keep only recognised instruments; provider payloads occasionally include
    # indexes, private companies or exchange codes that are not tradable.
    if ticker not in _NSE_BY_SYMBOL and ticker not in _GLOBAL_SYMBOLS:
        return
    if ticker not in found:
        found.append(ticker)


def extract_tickers(
    headline: str,
    summary: str = "",
    extra: Optional[Iterable[object]] = None,
    limit: int = 6,
) -> list[str]:
    """Extract tickers from text and provider payloads without inventing them.

    Matches company names and known NSE/global symbols only.  Cashtags
    (``$NVDA``) are accepted as explicit user intent.
    """
    text = f"{headline or ''} {summary or ''}".strip()
    found: list[str] = []

    if text:
        lowered = text.lower()
        for name, symbol in _NSE_NAME_MATCHES:
            if name in lowered:
                _add_ticker(found, symbol)
        for name, symbol in _GLOBAL_NAME_MATCHES:
            if name in lowered:
                _add_ticker(found, symbol)

        for match in _CASHTAG.finditer(text):
            _add_ticker(found, match.group(1))

        for match in _TICKER_TOKEN.finditer(text):
            token = match.group(1)
            if token in _NSE_BY_SYMBOL or token in _GLOBAL_SYMBOLS:
                _add_ticker(found, token)

    for value in extra or ():
        _add_ticker(found, value)

    return found[:limit]


# ---------------------------------------------------------------------------
# Article classification
# ---------------------------------------------------------------------------

def classify_content_type(source_type: str, spec: SourceSpec, headline: str) -> str:
    if source_type == "community":
        return "community"
    if source_type == "official":
        return "report"
    lowered = (headline or "").lower()
    if lowered.startswith("opinion") or "| opinion" in lowered:
        return "opinion"
    if lowered.startswith("analysis") or "| analysis" in lowered:
        return "analysis"
    return spec.content_type if spec.content_type in ("analysis", "opinion") else "report"


def classify_article(
    *,
    headline: str,
    summary: str = "",
    source_name: str = "",
    source_url: str = "",
    region_hint: Optional[str] = None,
    source_type_hint: Optional[str] = None,
    tickers: Optional[Iterable[object]] = None,
    sentiment: Optional[str] = None,
    sentiment_score: Optional[float] = None,
    sentiment_method: str = "lexicon",
) -> dict:
    """Classify one normalised article.

    ``source_type_hint`` is only used for feeds that are definitionally one
    type (Reddit).  Credibility is never supplied by a provider; it always
    comes from the local registry or the conservative fallback.
    """
    spec = source_for(source_name, source_url)
    source_type = source_type_hint if source_type_hint in SOURCE_TYPES else spec.source_type

    if source_type == "community":
        credibility = 1
    elif source_type == "official" and spec.credibility_level < 5:
        credibility = 5
    else:
        credibility = spec.credibility_level

    if spec.region != "global":
        region = spec.region
    elif source_type == "community" and region_hint in REGIONS:
        region = region_hint
    else:
        region = classify_region(headline, summary, default=region_hint or "global")

    category = classify_category(headline, summary)
    resolved_tickers = extract_tickers(headline, summary, extra=tickers)

    method = sentiment_method
    if sentiment in SENTIMENTS and sentiment_method == "provider":
        label = sentiment
        score = round(float(sentiment_score or 0.0), 3)
    elif sentiment_score is not None and sentiment_method == "provider":
        label = sentiment_from_score(float(sentiment_score))
        score = round(max(-1.0, min(1.0, float(sentiment_score))), 3)
    else:
        label, score = score_sentiment(headline, summary)
        method = "lexicon"

    impact = classify_impact(
        source_type, credibility, category, headline, resolved_tickers
    )
    content_type = classify_content_type(source_type, spec, headline)

    return {
        "headline": headline.strip(),
        "summary": summary.strip(),
        "source_name": source_name.strip() or spec.name,
        "source_domain": domain_from_url(source_url) or spec.domain,
        "source_key": spec.key,
        "source_url": source_url.strip(),
        "region": region,
        "category": category,
        "tickers": resolved_tickers,
        "sentiment": label,
        "sentiment_score": score,
        "sentiment_method": method,
        "source_type": source_type,
        "content_type": content_type,
        "credibility_level": credibility,
        "impact_level": impact,
        "is_verified": source_type == "official",
    }


# ---------------------------------------------------------------------------
# Public registry helpers
# ---------------------------------------------------------------------------

def all_sources() -> tuple[SourceSpec, ...]:
    return _SOURCES


def credibility_scale() -> list[dict]:
    return [
        {
            "level": level,
            "label": CREDIBILITY_LABELS[level],
            "meaning": CREDIBILITY_MEANINGS[level],
        }
        for level in sorted(CREDIBILITY_LABELS, reverse=True)
    ]

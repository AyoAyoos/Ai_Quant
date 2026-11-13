import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  Link,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'
import {
  AlertTriangle,
  ArrowUpRight,
  ExternalLink,
  Minus,
  Newspaper,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import {
  fetchNews,
  fetchNewsOverview,
  fetchNewsSources,
  fetchNewsTrending,
  refreshNews,
} from '../lib/api.js'
import {
  formatDateTime,
  formatNumber,
} from '../lib/format.js'
import Note from '../components/Note.jsx'

const ICON_SIZE = 14

const REGIONS = [
  { key: 'india', label: 'India' },
  { key: 'usa', label: 'United States' },
  { key: 'china', label: 'China' },
  { key: 'europe', label: 'Europe' },
  { key: 'japan', label: 'Japan & APAC' },
  { key: 'global', label: 'Global' },
]

const SOURCE_TYPES = [
  { key: 'official', label: 'Official' },
  { key: 'newswire', label: 'Newswire' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'aggregator', label: 'Aggregator' },
  { key: 'community', label: 'Community' },
]

const SENTIMENTS = [
  { key: 'bullish', label: 'Bullish', tone: 'positive' },
  { key: 'bearish', label: 'Bearish', tone: 'negative' },
  { key: 'neutral', label: 'Neutral', tone: 'neutral' },
]

const CREDIBILITY_STYLES = {
  5: { label: 'Official', tone: 'verified' },
  4: { label: 'Newswire', tone: 'reported' },
  3: { label: 'Publisher', tone: 'reported' },
  2: { label: 'Aggregator', tone: 'secondary' },
  1: { label: 'Community', tone: 'speculative' },
}

const SENTIMENT_STYLES = {
  bullish: { label: 'Bullish', tone: 'bullish' },
  bearish: { label: 'Bearish', tone: 'bearish' },
  neutral: { label: 'Neutral', tone: 'muted' },
}

function credibilityClass(level) {
  switch (level) {
    case 5: return 'cred--verified'
    case 4: return 'cred--newswire'
    case 3: return 'cred--publisher'
    case 2: return 'cred--aggregator'
    case 1: return 'cred--community'
    default: return 'cred--unknown'
  }
}

function formatAge(publishedAt) {
  if (!publishedAt) return ''
  const seconds = Math.max(0, Date.now() / 1000 - publishedAt)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.floor(hours / 24)} d ago`
}

function CredibilityBadge({ level }) {
  const style = CREDIBILITY_STYLES[level] ?? CREDIBILITY_STYLES[2]
  return (
    <span className={`status-badge ${credibilityClass(level)}`} title={style.label}>
      {style.label}
    </span>
  )
}

function SentimentPill({ sentiment, score, method }) {
  const style = SENTIMENT_STYLES[sentiment] ?? SENTIMENT_STYLES.neutral
  return (
    <span
      className={`status-badge sentiment--${sentiment}`}
      title={`${style.label} · score ${score?.toFixed(2) ?? '—'} · ${method}`}
    >
      {style.label}
    </span>
  )
}

export default function NewsHubPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [overview, setOverview] = useState(null)
  const [articles, setArticles] = useState([])
  const [total, setTotal] = useState(0)
  const [trending, setTrending] = useState([])
  const [stale, setStale] = useState(true)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [sourcesStatus, setSourcesStatus] = useState(null)
  const [activeTab, setActiveTab] = useState(params.get('tab') || 'feed')

  const region = params.get('region') || ''
  const category = params.get('category') || ''
  const sourceType = params.get('source_type') || ''
  const contentType = params.get('content_type') || ''
  const sentiment = params.get('sentiment') || ''
  const ticker = params.get('ticker') || ''
  const q = params.get('q') || ''
  const minCredibility = params.get('min_credibility') || ''
  const hours = params.get('hours') || '168'
  const sort = params.get('sort') || 'recent'
  const limit = Number(params.get('limit')) || 40
  const offset = Number(params.get('offset')) || 0

  const mountRef = useRef(true)

  const setFilter = useCallback((key, value) => {
    const next = new URLSearchParams(params)
    if (value === '' || value == null) next.delete(key)
    else next.set(key, String(value))
    next.set('offset', '0')
    navigate(`?${next.toString()}`, { replace: true })
  }, [params, navigate])

  const load = useCallback(async () => {
    if (!mountRef.current) return
    setLoading(true)
    setError(null)
    try {
      const [overviewResult, listResult, trendingResult, sourcesResult] =
        await Promise.all([
          fetchNewsOverview({ hours }),
          fetchNews({
            region: region || undefined,
            category: category || undefined,
            sourceType: sourceType || undefined,
            contentType: contentType || undefined,
            sentiment: sentiment || undefined,
            ticker: ticker || undefined,
            q: q || undefined,
            minCredibility: minCredibility || undefined,
            hours: Number(hours) || 168,
            sort,
            limit,
            offset,
          }),
          fetchNewsTrending({ hours: 24, limit: 8 }),
          fetchNewsSources(),
        ])
      setOverview(overviewResult)
      setArticles(listResult.articles ?? [])
      setTotal(listResult.total ?? 0)
      setTrending(trendingResult.tickers ?? [])
      setSourcesStatus(sourcesResult)
      setStale(listResult.stale ?? true)
    } catch (err) {
      setError(err.message || 'Could not load market news.')
    } finally {
      if (mountRef.current) setLoading(false)
    }
  }, [
    region, category, sourceType, contentType, sentiment, ticker, q,
    minCredibility, hours, sort, limit, offset,
  ])

  useEffect(() => {
    load()
    return () => { mountRef.current = false }
  }, [load])

  useEffect(() => {
    const timer = window.setInterval(load, 60000)
    return () => window.clearInterval(timer)
  }, [load])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      await refreshNews({ force: true })
      await load()
    } catch (err) {
      setError(err.message || 'Refresh failed.')
    } finally {
      setRefreshing(false)
    }
  }, [load])

  const pageCount = Math.max(1, Math.ceil(total / limit))
  const currentPage = Math.max(1, Math.floor(offset / limit) + 1)

  const counts = useMemo(() => {
    if (!overview) return null
    return {
      total: overview.total ?? 0,
      highImpact: overview.high_impact ?? 0,
      official: overview.official ?? 0,
      community: overview.community ?? 0,
    }
  }, [overview])

  const sentimentSnapshot = useMemo(() => {
    return overview?.sentiment?.overall ?? null
  }, [overview])

  const setTab = (tab) => {
    setActiveTab(tab)
    const next = new URLSearchParams(params)
    next.set('tab', tab)
    next.delete('offset')
    navigate(`?${next.toString()}`, { replace: true })
  }

  const allSources = useMemo(() => sourcesStatus?.sources ?? [], [sourcesStatus])
  const credentialsNeeded = useMemo(() => sourcesStatus?.credentials_needed ?? [], [sourcesStatus])

  if (activeTab === 'sources') {
    return (
      <div className="page">
        <div className="page-head">
          <div className="page-head__text">
            <h1 className="page-title">Market News Hub — Sources</h1>
            <p className="page-lede">
              Every publisher, exchange and regulator in the registry, with its
              credibility tier and how it is ingested.
            </p>
          </div>
        </div>

        <section className="panel" aria-labelledby="source-registry">
          <h2 className="section-title" id="source-registry">Source registry</h2>
          {loading && <p className="muted">Loading sources…</p>}
          {error && <Note tone="danger" title="Unable to load sources">{error}</Note>}
          {!loading && !error && (
            <div className="sources-grid">
              {allSources.map((source) => (
                <div key={source.key} className="source-card">
                  <div className="source-card__head">
                    <span className="source-card__name">{source.name}</span>
                    <CredibilityBadge level={source.credibility_level} />
                  </div>
                  <div className="source-card__meta">
                    <span>{source.region_label}</span>
                    <span>{source.source_type_label}</span>
                    <span>{source.content_type_label}</span>
                  </div>
                  <div className="source-card__integrations">
                    {source.integrations.map((integration) => (
                      <span key={integration} className="integration-chip">{integration}</span>
                    ))}
                  </div>
                  {source.notes && (
                    <p className="source-card__notes">{source.notes}</p>
                  )}
                  <a
                    className="source-card__link"
                    href={source.homepage || source.domain}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Visit {source.name} <ArrowUpRight size={ICON_SIZE} />
                  </a>
                </div>
              ))}
            </div>
          )}
        </section>

        {credentialsNeeded.length > 0 && (
          <section className="panel panel--accent" aria-labelledby="credentials">
            <h2 className="section-title" id="credentials">Free API keys you can add</h2>
            <p className="page-lede">
              The hub works without any key using Google News RSS, official
              RSS/Atom feeds and Reddit's public JSON. These providers are
              optional extras:
            </p>
            <ul className="credential-list">
              {credentialsNeeded.map((cred) => (
                <li key={cred.env_var} className="credential-list__item">
                  <span className="credential-list__provider">{cred.label}</span>
                  <span className="credential-list__env">env: <code>{cred.env_var}</code></span>
                  <span className="credential-list__tier">{cred.free_tier}</span>
                  <a
                    className="credential-list__signup"
                    href={cred.signup}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Sign up <ExternalLink size={ICON_SIZE} />
                  </a>
                </li>
              ))}
            </ul>
            <p className="page-lede">
              Add them to <code>backend/.env</code> and restart the backend. No
              code change is required.
            </p>
          </section>
        )}

        <section className="panel" aria-labelledby="credibility-scale">
          <h2 className="section-title" id="credibility-scale">Credibility scale</h2>
          <p className="page-lede">
            Credibility is assigned by the app's own taxonomy — never by a
            provider. Only official/primary sources are marked verified.
          </p>
          <div className="credibility-scale">
            {sourcesStatus?.credibility_scale?.map((tier) => (
              <div key={tier.level} className={`tier-row tier--${tier.level}`}>
                <span className="tier-level">{tier.level}</span>
                <span className="tier-label">{tier.label}</span>
                <span className="tier-meaning">{tier.meaning}</span>
              </div>
            ))}
          </div>
        </section>

        <Note title="Redistribution reminder">
          Only headlines, short source snippets and links are stored — never
          full article text or publisher images. Community (Reddit) posts are
          sentiment signals, never verified news. Check each provider's
          redistribution terms before commercial display.
        </Note>
      </div>
    )
  }

  if (activeTab === 'trending') {
    return (
      <div className="page">
        <div className="page-head">
          <div className="page-head__text">
            <h1 className="page-title">Trending tickers</h1>
            <p className="page-lede">
              Most-mentioned instruments in the last {overview?.window_hours ?? 24}
              hours, with mention momentum against the previous window.
            </p>
          </div>
          <button
            className="btn btn--primary btn--sm"
            onClick={() => setTab('feed')}
          >
            ← Back to feed
          </button>
        </div>

        <section className="panel" aria-labelledby="trending-list">
          <h2 className="section-title" id="trending-list">Trending by mention volume</h2>
          {loading && <p className="muted">Loading…</p>}
          {error && <Note tone="danger" title="Unable to load trending">{error}</Note>}
          {!loading && !error && trending.length === 0 && (
            <div className="empty-state">
              <span className="empty-state__icon">📉</span>
              <h3 className="empty-state__title">No trending tickers</h3>
              <p className="empty-state__text">
                Refresh the feed or broaden the time window to surface trending
                instruments.
              </p>
            </div>
          )}
          {!loading && !error && trending.length > 0 && (
            <div className="trending-table">
              <table>
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Mentions</th>
                    <th>Trend</th>
                    <th>Sentiment</th>
                    <th>Official</th>
                    <th>Community</th>
                    <th>Sources</th>
                    <th>Headlines</th>
                  </tr>
                </thead>
                <tbody>
                  {trending.map((item) => (
                    <tr key={item.ticker} className="trending-row">
                      <td className="trending-cell--ticker">
                        <Link
                          className="trending-ticker-link"
                          to={`/news?q=${encodeURIComponent(item.ticker)}`}
                        >
                          {item.ticker}
                        </Link>
                      </td>
                      <td className="tabular">{item.mentions}</td>
                      <td>
                        <span className={`trend-chip trend--${item.velocity}`}>
                          {item.velocity}
                          {item.delta_pct != null && ` (${item.delta_pct >= 0 ? '+' : ''}${item.delta_pct}%)`}
                        </span>
                      </td>
                      <td>
                        <SentimentPill
                          sentiment={item.sentiment}
                          score={item.sentiment_score}
                          method="lexicon"
                        />
                      </td>
                      <td className="tabular">{item.official_mentions}</td>
                      <td className="tabular">{item.community_mentions}</td>
                      <td className="tabular muted">{item.sources.join(', ') || '—'}</td>
                      <td>
                        <ul className="headline-list">
                          {item.headlines.map((headline, i) => (
                            <li key={i}>{truncate(headline, 90)}</li>
                          ))}
                          {item.headlines.length === 0 && <span className="muted">—</span>}
                        </ul>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    )
  }

  // Feed tab
  return (
    <div className="page news-hub-page">
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">
            <Newspaper size={20} /> Market News Hub
          </h1>
          <p className="page-lede">
            Aggregated market news from Indian publishers, official sources
            (NSE/BSE/SEBI/RBI), US/Wall Street, China, Europe, Japan, Reddit
            sentiment and other intelligence. Every article carries a
            credibility rating — official sources are verified; everything else
            is reported, not independently confirmed.
          </p>
        </div>
        <div className="page-head__actions">
          <button
            className="btn btn--primary"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? (
              <>
                <RefreshCw size={ICON_SIZE} className="spinning" /> Refreshing…
              </>
            ) : (
              <>
                <RefreshCw size={ICON_SIZE} /> Refresh
              </>
            )}
          </button>
          <span className="stale-indicator">
            {stale ? (
              <>
                <AlertTriangle size={ICON_SIZE} /> Stale — refresh to update
              </>
            ) : (
              <>
                <ShieldAlert size={ICON_SIZE} /> Fresh
              </>
            )}
          </span>
        </div>
      </div>

      {error && <Note tone="danger" title="Unable to load news">{error}</Note>}

      {/* Overview strip */}
      <section className="panel overview-strip" aria-labelledby="overview">
        <h2 className="section-title" id="overview">Overview</h2>
        <div className="overview-grid">
          <div className="overview-card">
            <span className="overview-card__label">Articles</span>
            <span className="overview-card__value">{counts?.total ?? '—'}</span>
            <span className="overview-card__delta">
              {overview?.refreshed_at ? `updated ${formatDateTime(overview.refreshed_at * 1000)}` : '—'}
            </span>
          </div>
          <div className="overview-card overview-card--impact">
            <span className="overview-card__label">High impact</span>
            <span className="overview-card__value">{counts?.highImpact ?? '—'}</span>
          </div>
          <div className="overview-card overview-card--official">
            <span className="overview-card__label">Official / verified</span>
            <span className="overview-card__value">{counts?.official ?? '—'}</span>
          </div>
          <div className="overview-card overview-card--community">
            <span className="overview-card__label">Community posts</span>
            <span className="overview-card__value">{counts?.community ?? '—'}</span>
          </div>
        </div>

        <div className="overview-sentiment">
          <h3 className="overview-sentiment__title">Market sentiment</h3>
          {sentimentSnapshot && (
            <>
              <div className="sentiment-breakdown">
                <div className="sentiment-item sentiment-item--bullish">
                  <span className="sentiment-item__label">Bullish</span>
                  <span className="sentiment-item__value">
                    {sentimentSnapshot.bullish_pct}%
                  </span>
                </div>
                <div className="sentiment-item sentiment-item--bearish">
                  <span className="sentiment-item__label">Bearish</span>
                  <span className="sentiment-item__value">
                    {sentimentSnapshot.bearish_pct}%
                  </span>
                </div>
                <div className="sentiment-item sentiment-item--neutral">
                  <span className="sentiment-item__label">Neutral</span>
                  <span className="sentiment-item__value">
                    {sentimentSnapshot.neutral_pct}%
                  </span>
                </div>
              </div>
              <p className="sentiment-note">
                Sample: {formatNumber(sentimentSnapshot.sample_size)} ·{' '}
                {sentimentSnapshot.method === 'provider' ? 'provider scores' : 'lexicon scores'}
              </p>
            </>
          )}
        </div>
      </section>

      {/* Trending strip */}
      {trending.length > 0 && (
        <section className="panel trending-strip" aria-labelledby="trending-header">
          <div className="panel__head">
            <h2 className="section-title" id="trending-header">Trending tickers</h2>
            <button className="btn btn--sm btn--outline" onClick={() => setTab('trending')}>
              See all <ArrowUpRight size={ICON_SIZE} />
            </button>
          </div>
          <div className="trending-list">
            {trending.slice(0, 6).map((item) => (
              <div key={item.ticker} className="trending-item">
                <Link
                  className="trending-item__ticker"
                  to={`/news?q=${encodeURIComponent(item.ticker)}`}
                >
                  {item.ticker}
                </Link>
                <span className={`trend-chip trend--${item.velocity}`}>
                  {item.mentions} mentions
                  {item.delta_pct != null && ` · ${item.delta_pct >= 0 ? '+' : ''}${item.delta_pct}%`}
                </span>
                <SentimentPill
                  sentiment={item.sentiment}
                  score={item.sentiment_score}
                  method="lexicon"
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Controls */}
      <section className="panel controls-panel" aria-labelledby="filters">
        <h2 className="section-title" id="filters">Filters</h2>
        <div className="filter-bar">
          <button
            className={`filter-chip ${!region && !category && !sourceType && !contentType && !sentiment && !ticker && !q && !minCredibility ? 'filter-chip--active' : ''}`}
            onClick={() => {
              setFilter('region', '')
              setFilter('category', '')
              setFilter('source_type', '')
              setFilter('content_type', '')
              setFilter('sentiment', '')
              setFilter('ticker', '')
              setFilter('q', '')
              setFilter('min_credibility', '')
            }}
          >
            Clear all
          </button>
          <div className="chip-group">
            <span className="chip-group__label">Region</span>
            {REGIONS.map((item) => (
              <button
                key={item.key}
                className={`filter-chip ${region === item.key ? 'filter-chip--active' : ''}`}
                onClick={() => setFilter('region', item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="chip-group">
            <span className="chip-group__label">Source type</span>
            {SOURCE_TYPES.map((item) => (
              <button
                key={item.key}
                className={`filter-chip ${sourceType === item.key ? 'filter-chip--active' : ''}`}
                onClick={() => setFilter('source_type', item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="chip-group">
            <span className="chip-group__label">Sentiment</span>
            {SENTIMENTS.map((item) => (
              <button
                key={item.key}
                className={`filter-chip ${sentiment === item.key ? 'filter-chip--active' : ''}`}
                onClick={() => setFilter('sentiment', item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="filter-bar filter-bar--search">
          <span className="chip-group__label">Search</span>
          <input
            className="input input--search"
            placeholder="Headline, source or ticker…"
            value={q}
            onChange={(e) => setFilter('q', e.target.value)}
          />
          <span className="chip-group__label">Ticker</span>
          <input
            className="input input--search"
            placeholder="RELIANCE, NVDA…"
            value={ticker}
            onChange={(e) => setFilter('ticker', e.target.value)}
          />
          <button className="btn btn--sm btn--outline" onClick={() => setFilter('sort', sort === 'recent' ? 'impact' : 'recent')}>
            Sort by {sort === 'recent' ? 'impact' : 'recent'}
          </button>
        </div>
      </section>

      {/* Articles */}
      <section className="panel articles-panel" aria-labelledby="articles">
        <h2 className="section-title" id="articles">
          Articles ({formatNumber(total)})
        </h2>
        {loading && articles.length === 0 && (
          <div className="empty-state">
            <span className="empty-state__icon">⏳</span>
            <h3 className="empty-state__title">Loading news…</h3>
            <p className="empty-state__text">Fetching the latest from all enabled sources.</p>
          </div>
        )}
        {!loading && articles.length === 0 && (
          <div className="empty-state">
            <span className="empty-state__icon">📭</span>
            <h3 className="empty-state__title">No articles match your filters</h3>
            <p className="empty-state__text">
              Try clearing filters, broadening the time window, or refreshing
              the feed.
            </p>
            <div className="empty-state__actions">
              <button className="btn btn--primary" onClick={handleRefresh}>
                <RefreshCw size={ICON_SIZE} /> Refresh feed
              </button>
            </div>
          </div>
        )}
        {!loading && articles.length > 0 && (
          <>
          <div className="article-grid">
            {articles.map((article) => (
              <article key={article.id} className="news-card news-card--article">
                <div className="news-card__head">
                  <div className="news-card__meta">
                    <span className={`region-chip region--${article.region}`}>
                      {article.region_label}
                    </span>
                    <CredibilityBadge level={article.credibility_level} />
                    {article.is_verified && (
                      <span className="verified-badge" title="Verified official source">Verified</span>
                    )}
                    {article.content_type === 'opinion' && (
                      <span className="opinion-badge" title="Opinion / analysis">Opinion</span>
                    )}
                    <span className="published-chip">{formatAge(article.published_at)}</span>
                  </div>
                  <h3 className="news-card__headline">
                    <Link
                      className="news-card__headline-link"
                      to={`/news?q=${encodeURIComponent(article.headline)}`}
                      title={article.headline}
                    >
                      {article.headline}
                    </Link>
                  </h3>
                  {article.summary && (
                    <p className="news-card__summary">{article.summary}</p>
                  )}
                </div>
                <div className="news-card__footer">
                  <div className="news-card__source">
                    {article.source_name}
                    {article.source_domain && (
                      <span className="news-card__domain">· {article.source_domain}</span>
                    )}
                  </div>
                  <div className="news-card__tags">
                    {article.tickers.slice(0, 4).map((ticker) => (
                      <span
                        key={ticker}
                        className="news-card__tag news-card__tag--ticker"
                        title={ticker}
                      >
                        {ticker}
                      </span>
                    ))}
                    <SentimentPill
                      sentiment={article.sentiment}
                      score={article.sentiment_score}
                      method={article.sentiment_method}
                    />
                  </div>
                  <div className="news-card__actions">
                    <a
                      className="news-card__link"
                      href={article.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`Open original article on ${article.source_name}`}
                    >
                      Read on {article.source_name} <ExternalLink size={ICON_SIZE} />
                    </a>
                  </div>
                </div>
              </article>
            ))}
          </div>

          <div className="pagination">
            <button
              className="btn btn--sm btn--outline"
              disabled={currentPage <= 1}
              onClick={() => setFilter('offset', Math.max(0, offset - limit))}
            >
              <Minus size={ICON_SIZE} /> Prev
            </button>
            <span className="pagination__info">
              Page {currentPage} of {pageCount} · {formatNumber(total)} articles
            </span>
            <button
              className="btn btn--sm btn--outline"
              disabled={currentPage >= pageCount}
              onClick={() => setFilter('offset', offset + limit)}
            >
              Next <ArrowUpRight size={ICON_SIZE} />
            </button>
          </div>
          </>
        )}
      </section>

      <Note tone="info" title="How to read credibility">
        <strong>Official / primary</strong> (exchange filings, regulators,
        central banks) are the only articles marked verified.{' '}
        <strong>Newswire</strong> and <strong>publisher</strong> articles are
        reported, not independently verified by this app.{' '}
        <strong>Community</strong> (Reddit) posts are speculation — never
        presented as verified news. AI summaries are never shown; every summary
        is the source's own snippet.
      </Note>
    </div>
  )
}

function truncate(text, max) {
  if (typeof text !== 'string') return ''
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, max - 1).trimEnd()}…`
}

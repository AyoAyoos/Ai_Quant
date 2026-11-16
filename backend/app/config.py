from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://quant_user:quant_pass@localhost:5432/quant_trading"

    # LLM provider config (Groq recommended: fast, free tier, Llama/Qwen models)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Market focus for MVP
    default_market: str = "NIFTY50"

    # How many days a cached OHLCV CSV stays fresh before we re-download.
    market_data_refresh_days: int = 1

    # Sandbox backstops for the backtest worker subprocess. The memory cap
    # applies on POSIX only (Windows has no rlimit equivalent); the wall-clock
    # timeout in run_backtest_sandboxed applies everywhere.
    #
    # This is an address-space (RLIMIT_AS) cap, and importing pandas + numpy +
    # backtrader alone needs ~1.5GB of it — below that the worker dies with
    # "ImportError: ... failed to map segment from shared object" before the
    # strategy code even runs. Keep comfortable headroom above the import cost.
    sandbox_memory_mb: int = 2048
    sandbox_cpu_seconds: int | None = None

    # Paper-trading approval gate: a backtest must show at least this many
    # closed trades and stay within this max-drawdown cap (percent).
    approval_min_trades: int = 10
    approval_max_drawdown_pct: float = 50.0

    # Comma-separated browser origins allowed by CORS, or "*" for any.
    # Read from the ALLOWED_ORIGINS env var (set on Render). Empty = dev defaults.
    allowed_origins: str = ""

    # ------------------------------------------------------------ News Hub
    # Optional free API keys. The hub is fully functional without them using
    # keyless RSS/Atom feeds and Reddit's public JSON. Marketaux and Alpha
    # Vantage can supply their own sentiment; Finnhub only supplies headlines.
    marketaux_api_key: str = ""
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""

    # Background refresh cadence and retention.
    news_refresh_minutes: int = 30
    news_retention_days: int = 7
    news_max_articles: int = 3000
    news_enable_reddit: bool = True
    news_enable_google_news: bool = True
    news_auto_refresh: bool = True
    news_auto_refresh_initial_delay_seconds: int = 20
    news_rss_timeout_seconds: float = 20.0
    news_user_agent: str = (
        "QuantNitiNewsHub/1.0 (+https://github.com/; educational market research)"
    )
    # Reddit asks for a descriptive UA with contact info; override in .env.
    reddit_user_agent: str = (
        "QuantNitiNewsHub/1.0 (educational market-news aggregator; contact: dev@local)"
    )

    # Single local user (auth removed): every request runs as dev@local.


settings = Settings()

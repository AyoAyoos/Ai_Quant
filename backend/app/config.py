from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    sandbox_memory_mb: int = 1024
    sandbox_cpu_seconds: int | None = None

    # Paper-trading approval gate: a backtest must show at least this many
    # closed trades and stay within this max-drawdown cap (percent).
    approval_min_trades: int = 1
    approval_max_drawdown_pct: float = 50.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

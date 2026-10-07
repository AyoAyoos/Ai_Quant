from pydantic import BaseModel, Field, field_validator
from typing import Optional


class ChatMessageIn(BaseModel):
    conversation_id: str | None = None
    content: str


class ChatMessageOut(BaseModel):
    conversation_id: str
    reply: str
    strategy_id: str | None = None
    strategy_name: str | None = None
    strategy_description: str | None = None


class StrategyDetailOut(BaseModel):
    strategy_id: str
    name: str
    description: str | None = None
    market: str
    status: str
    status_note: str | None = None
    generated_code: str | None = None
    strategy_spec: dict | None = None


class GateOut(BaseModel):
    strategy_id: str
    status: str
    status_note: str | None = None


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class StopIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class CapitalParams(BaseModel):
    """Money knobs shared by the backtest and deployment endpoints.

    ``commission_pct`` and ``sizer_percents`` are PERCENTAGES in the open
    interval (0, 100) — NOT decimal ratios. 0.2 means 0.2% and 20 means 20%;
    the worker divides by 100 before handing the rate to Backtrader
    (``strategy_runner.pct_to_fraction``). Sending a ratio such as 0.002 would
    silently be read as 0.002%, so the UI always posts the percentage.
    """

    cash: float = Field(default=100000.0, gt=0, description="Starting capital (> 0)")
    commission_pct: float = Field(
        default=0.1, gt=0, lt=100, description="Commission per order, percent in (0, 100)"
    )
    sizer_percents: float = Field(
        default=95.0, gt=0, lt=100, description="Percent of available cash per entry, in (0, 100)"
    )


class DeployIn(CapitalParams):
    pass


class DeploymentOut(BaseModel):
    id: str
    strategy_id: str
    status: str
    cash: float
    commission_pct: float
    sizer_percents: float
    deployed_at: str | None = None
    stopped_at: str | None = None
    stop_reason: str | None = None


class BacktestRequest(CapitalParams):
    data_path: str | None = None


class BacktestResultOut(BaseModel):
    strategy_id: str
    status: str = "backtested"
    total_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    win_rate_pct: float | None = None
    max_drawdown_pct: float | None = None
    num_trades: int | None = None
    sharpe: float | None = None
    sortino: float | None = None
    cagr_pct: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    trades: list[dict] = []
    trades_truncated: int = 0
    equity_curve: list[list] = []
    warnings: list[str] = []
    raw_metrics: dict | None = None


# ============================================================
# Paper Trading Schemas (simulated execution only — no broker)
# ============================================================

class PaperTickIn(BaseModel):
    """Optional explicit bar date for a paper tick (``YYYY-MM-DD``).

    Omitted (the normal UI path) advances the oldest unprocessed cached bar.
    When supplied, it must equal EXACTLY the next unprocessed bar — skips
    are rejected to preserve chronological execution.
    ``deployment_id`` optionally pins the tick to one deployment; omitted
    ticks the active deployment (stopped deployments never tick).
    """

    bar_date: str | None = None
    deployment_id: str | None = None


class PaperTickOut(BaseModel):
    deployment_id: str
    strategy_id: str
    bar_date: str
    signal: str  # BUY | SELL | HOLD — what the strategy replay said
    action: str  # BUY | SELL | HOLD — what the simulator executed
    price: float | None = None  # simulated fill price, or the bar close on HOLD
    quantity: int = 0
    order_id: str | None = None
    order_status: str | None = None  # filled | rejected | None (HOLD writes no order)
    trade_id: str | None = None
    pnl_net: float | None = None
    cash_balance: float | None = None
    equity: float | None = None
    realized_pnl: float | None = None
    note: str | None = None


class PaperAccountOut(BaseModel):
    """Authoritative virtual-account snapshot. The frontend displays it verbatim."""

    deployment_id: str
    strategy_id: str
    status: str
    starting_cash: float
    cash_balance: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float | None = None
    total_pnl: float
    return_pct: float | None = None
    open_positions: int
    completed_trades: int
    last_bar_date: str | None = None
    last_error: str | None = None
    deployed_at: str | None = None
    stopped_at: str | None = None
    is_active: bool


class PaperPositionOut(BaseModel):
    id: str
    deployment_id: str
    symbol: str
    quantity: int
    avg_price: float
    entry_date: str
    market_value: float | None = None
    unrealized_pnl: float | None = None


class PaperOrderOut(BaseModel):
    id: str
    deployment_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    bar_date: str
    status: str
    commission: float
    note: str | None = None
    created_at: str | None = None


class PaperTradeOut(BaseModel):
    id: str
    deployment_id: str
    symbol: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_date: str
    exit_date: str
    pnl: float
    pnl_net: float
    entry_order_id: str | None = None
    exit_order_id: str | None = None


class MarketBarOut(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketBarsOut(BaseModel):
    """Processed-period OHLC bars, oldest first. READ-ONLY — never trades."""

    strategy_id: str
    deployment_id: str | None = None
    market: str
    last_bar_date: str | None = None
    bars: list[MarketBarOut] = []
    truncated: bool = False


class PaperDeploymentSummaryOut(BaseModel):
    """One row for the Paper Trading hub: deployment + live snapshot numbers."""

    id: str
    strategy_id: str
    strategy_name: str | None = None
    market: str | None = None
    status: str
    starting_cash: float
    cash_balance: float | None = None
    equity: float | None = None
    realized_pnl: float | None = None
    total_pnl: float | None = None
    return_pct: float | None = None
    open_positions: int = 0
    completed_trades: int = 0
    last_bar_date: str | None = None
    deployed_at: str | None = None
    stopped_at: str | None = None
    stop_reason: str | None = None


# ============================================================
# Structured Strategy Builder Schemas
# ============================================================

SUPPORTED_MARKETS = ["NIFTY50", "BANKNIFTY", "SENSEX", "OTHER"]
SUPPORTED_TRADING_STYLES = ["scalping", "intraday", "swing", "positional"]
SUPPORTED_TIMEFRAMES = ["5m", "15m", "30m", "1h", "1d"]
SUPPORTED_INDICATORS = ["EMA", "SMA", "RSI", "MACD", "Bollinger Bands", "Volume"]


def _indicator_lookup_key(name: str) -> str:
    """Fold a name to a comparison key: lowercase, separators collapsed away.

    'BOLLINGER_BANDS', 'bollinger-bands', 'Bollinger  Bands' and
    'BOLLINGERBANDS' all fold to the same key as the canonical name.
    """
    return "".join(ch for ch in name.strip().lower() if ch.isalnum())


# canonical name keyed by every reasonable spelling of it
_INDICATOR_LOOKUP = {_indicator_lookup_key(name): name for name in SUPPORTED_INDICATORS}
_INDICATOR_LOOKUP.update({
    _indicator_lookup_key("bb"): "Bollinger Bands",
    _indicator_lookup_key("bollinger"): "Bollinger Bands",
    _indicator_lookup_key("volume indicator"): "Volume",
})


def canonical_indicator_name(value: str) -> str | None:
    """Return the canonical supported name for any common spelling, else None."""
    return _INDICATOR_LOOKUP.get(_indicator_lookup_key(value))

# Trading style to compatible timeframes mapping
STYLE_TIMEFRAME_COMPATIBILITY = {
    "scalping": ["5m", "15m"],
    "intraday": ["5m", "15m", "30m", "1h"],
    "swing": ["1h", "1d"],
    "positional": ["1d"],
}


class IndicatorSpec(BaseModel):
    name: str
    parameters: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_indicator_name(cls, v: str) -> str:
        # Normalize first: enum-style (BOLLINGER_BANDS), lower (rsi) and
        # compact (bollingerbands) spellings all collapse to the canonical
        # display name the rest of the pipeline expects.
        canonical = canonical_indicator_name(v)
        if canonical is None:
            raise ValueError(
                f"Unsupported indicator: {v}. Supported: {SUPPORTED_INDICATORS}"
            )
        return canonical

    @field_validator("parameters")
    @classmethod
    def validate_indicator_parameters(cls, v: dict, info) -> dict:
        # Parameters are validated per-indicator in the service layer
        return v


class RiskManagementSpec(BaseModel):
    stop_loss_percent: float = Field(gt=0, le=100, description="Stop loss percentage (0-100)")
    take_profit_percent: float = Field(gt=0, le=100, description="Take profit percentage (0-100)")
    trailing_stop_percent: float | None = Field(default=None, ge=0, le=100, description="Trailing stop percentage (0-100)")
    max_trades_per_day: int | None = Field(default=None, ge=1, le=100, description="Maximum trades per day (1-100)")


class StrategyBuilderRequest(BaseModel):
    market: str = Field(default="NIFTY50", description="Trading market")
    trading_style: str = Field(description="Trading style")
    timeframe: str = Field(description="Chart timeframe")
    indicators: list[IndicatorSpec] = Field(min_length=1, description="Technical indicators with parameters")
    entry_conditions: list[str] = Field(min_length=1, description="Entry condition descriptions")
    exit_conditions: list[str] = Field(min_length=1, description="Exit condition descriptions")
    risk_management: RiskManagementSpec

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        if v not in SUPPORTED_MARKETS:
            raise ValueError(f"Unsupported market: {v}. Supported: {SUPPORTED_MARKETS}")
        # For MVP, only NIFTY50 has market data
        if v != "NIFTY50":
            raise ValueError(f"Market {v} is not yet supported for backtesting (only NIFTY50 has data)")
        return v

    @field_validator("trading_style")
    @classmethod
    def validate_trading_style(cls, v: str) -> str:
        if v not in SUPPORTED_TRADING_STYLES:
            raise ValueError(f"Unsupported trading style: {v}. Supported: {SUPPORTED_TRADING_STYLES}")
        return v

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        if v not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {v}. Supported: {SUPPORTED_TIMEFRAMES}")
        return v

    @field_validator("timeframe")
    @classmethod
    def validate_style_timeframe_compatibility(cls, v: str, info) -> str:
        trading_style = info.data.get("trading_style")
        if trading_style and v not in STYLE_TIMEFRAME_COMPATIBILITY.get(trading_style, []):
            raise ValueError(
                f"Timeframe {v} is not compatible with trading style {trading_style}. "
                f"Compatible: {STYLE_TIMEFRAME_COMPATIBILITY.get(trading_style, [])}"
            )
        return v

    @field_validator("indicators")
    @classmethod
    def validate_indicators(cls, v: list[IndicatorSpec]) -> list[IndicatorSpec]:
        if not v:
            raise ValueError("At least one indicator is required")
        # Check for duplicate indicator names
        names = [ind.name for ind in v]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate indicator names are not allowed")
        return v

    @field_validator("entry_conditions")
    @classmethod
    def validate_entry_conditions(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one entry condition is required")
        for condition in v:
            if not condition.strip():
                raise ValueError("Entry conditions cannot be empty strings")
        return v

    @field_validator("exit_conditions")
    @classmethod
    def validate_exit_conditions(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one exit condition is required")
        for condition in v:
            if not condition.strip():
                raise ValueError("Exit conditions cannot be empty strings")
        return v


class StrategySpecOut(BaseModel):
    """Echo of the validated strategy specification for the response."""
    market: str
    trading_style: str
    timeframe: str
    indicators: list[IndicatorSpec]
    entry_conditions: list[str]
    exit_conditions: list[str]
    risk_management: RiskManagementSpec


class StrategyGenerateResponse(BaseModel):
    strategy_id: str
    name: str
    description: str
    market: str
    timeframe: str
    status: str
    generated_code: str
    strategy_specification: StrategySpecOut
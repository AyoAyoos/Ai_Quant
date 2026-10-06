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


class DeployIn(BaseModel):
    cash: float = Field(default=100000.0, gt=0)
    commission_pct: float = Field(default=0.1, gt=0, lt=100)
    sizer_percents: float = Field(default=95.0, gt=0, lt=100)


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


class BacktestRequest(BaseModel):
    data_path: str | None = None
    cash: float = Field(default=100000.0, gt=0)
    commission_pct: float = Field(default=0.1, gt=0, lt=100)
    sizer_percents: float = Field(default=95.0, gt=0, lt=100)


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
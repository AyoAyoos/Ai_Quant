"""
Engine-neutral normalized result model for dual-engine comparison.

Both Backtrader and Backtesting.py adapters produce this format.
"""

from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class NormalizedTrade(BaseModel):
    """A single completed trade, normalized across engines."""
    model_config = ConfigDict(extra="forbid")

    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    size: int
    pnl: float
    return_pct: float


class NormalizedMetrics(BaseModel):
    """Normalized backtest metrics."""
    model_config = ConfigDict(extra="forbid")

    initial_cash: float
    final_equity: float
    return_pct: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    max_drawdown_pct: float
    profit_factor: Optional[float] = None
    total_commission: float
    start_date: str
    end_date: str
    bars_processed: int


class NormalizedResult(BaseModel):
    """Complete normalized backtest result."""
    model_config = ConfigDict(extra="forbid")

    engine: Literal["backtrader", "backtesting.py", "shared_runtime"]
    spec_version: int
    metrics: NormalizedMetrics
    trades: list[NormalizedTrade]
    warnings: list[str]
    execution_model: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


def to_normalized_result(raw: dict) -> NormalizedResult:
    """Convert raw adapter output to validated NormalizedResult."""
    return NormalizedResult(
        engine=raw["engine"],
        spec_version=raw["spec_version"],
        metrics=NormalizedMetrics(**raw["metrics"]),
        trades=[NormalizedTrade(**t) for t in raw["trades"]],
        warnings=raw["warnings"],
        execution_model=raw["execution_model"],
    )
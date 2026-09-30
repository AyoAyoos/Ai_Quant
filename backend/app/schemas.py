from pydantic import BaseModel, Field


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
    # Per-trade breakdown and portfolio value path for the trade dashboard.
    # Each trade: entry/exit date+price, size, direction, bars_held, pnl,
    # pnl_net, won. Each equity point: [date, value].
    trades: list[dict] = []
    trades_truncated: int = 0
    equity_curve: list[list] = []
    warnings: list[str] = []
    raw_metrics: dict | None = None

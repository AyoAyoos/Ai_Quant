from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    conversation_id: str | None = None
    content: str


class ChatMessageOut(BaseModel):
    conversation_id: str
    reply: str
    strategy_id: str | None = None
    strategy_name: str | None = None


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
    warnings: list[str] = []
    raw_metrics: dict | None = None

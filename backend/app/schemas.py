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


class PaperPositionOut(BaseModel):
    """One open paper position. `last_price` is null until first marked."""

    id: str
    deployment_id: str
    symbol: str
    quantity: int
    avg_entry_price: float
    last_price: float | None = None
    opened_at: str | None = None
    updated_at: str | None = None


class PaperTradeOut(BaseModel):
    """One closed paper trade with its realised P&L already booked."""

    id: str
    deployment_id: str
    symbol: str
    direction: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_date: str | None = None
    exit_date: str | None = None
    gross_pnl: float
    commission: float
    net_pnl: float
    won: bool
    created_at: str | None = None


class PaperOrderOut(BaseModel):
    """Audit record of a simulated order: what was asked for and what happened."""

    id: str
    deployment_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    status: str
    reason: str | None = None
    created_at: str | None = None
    filled_at: str | None = None
    fill_price: float | None = None


class PaperAccountSnapshot(BaseModel):
    """Point-in-time valuation of a deployment's virtual paper account.

    `initial_balance` is the capital the deployment was configured with
    (`PaperDeployment.cash`, immutable). Everything below it is derived:

        position_value    = sum(quantity * last_price)
        unrealized_pnl    = sum((last_price - avg_entry_price) * quantity)
        equity            = balance + position_value
        total_pnl         = equity - initial_balance
        total_return_pct  = (total_pnl / initial_balance) * 100

    `total_pnl` is derived from cash rather than by adding the two P&L legs, so
    it stays truthful even if a leg is mid-settlement. Because closing a trade
    credits cash and books `realized_pnl` together, the identity
    `realized_pnl + unrealized_pnl == total_pnl` holds.
    """

    deployment_id: str
    strategy_id: str
    status: str
    initial_balance: float
    cash_balance: float
    position_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_return_pct: float
    open_positions: int = 0
    closed_trades: int = 0
    last_bar_date: str | None = None
    last_error: str | None = None


class PaperTickIn(BaseModel):
    """Optional controls for one paper-trading bar.

    Both fields are deliberately optional so the common case — "advance to the
    next unprocessed bar" — is a bodyless POST. `bar_date` pins an exact
    trading day, which is what makes stepping through history reproducible; with
    no `bar_date` the engine picks the first bar after the account's
    `last_bar_date` watermark. `quantity` overrides the deployment's position
    sizing, which lets a demo trade a known unit count instead of a
    percentage of cash.
    """

    bar_date: str | None = None
    quantity: int | None = Field(default=None, ge=1)


class PaperTickResult(BaseModel):
    """Outcome of processing one bar, plus the resulting account.

    `duplicate=True` means the requested bar had already been consumed by an
    earlier tick: nothing was executed, the watermark and balance are
    unchanged, and `reason` explains why. That is a successful no-op rather
    than an error, so a client that retries the same day is always safe.
    """

    strategy_id: str
    deployment_id: str
    symbol: str
    bar_date: str
    price: float
    action: str
    duplicate: bool = False
    reason: str | None = None
    order: PaperOrderOut | None = None
    fill_price: float | None = None
    quantity: int | None = None
    marked_positions: int = 0
    account: PaperAccountSnapshot


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

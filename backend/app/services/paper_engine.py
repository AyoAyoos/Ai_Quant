"""
Virtual paper account — the Phase 1 foundation for paper trading.

A deployment's virtual account is a virtual/dummy balance that strategy
signals will later move around. Nothing here talks to a broker, and nothing
places an order: this module owns the *bookkeeping* only.

Scope of this phase
-------------------
* :func:`open_account` — seed the mutable account state from the deployment's
  config snapshot when a deployment is created.
* :func:`snapshot`     — value the account at a point in time.

Deliberately NOT here yet (later phases): consuming BUY/SELL signals, filling
orders, opening/closing positions, advancing market data, and the
``last_bar_date`` watermark that makes tick processing idempotent. The
``paper_orders`` / ``paper_trades`` / ``paper_positions`` tables exist and are
readable, but this phase writes only the account itself.

Accounting model
----------------
``PaperDeployment.cash`` is immutable — the capital the deploy request asked
for, and the account's ``initial_balance``. Two mutable columns carry the
rest of the state:

* ``balance``      — cash on hand right now.
* ``realized_pnl`` — profit/loss banked by closed trades.

Closing a trade credits ``balance`` with the proceeds *and* books the profit in
``realized_pnl`` in the same step, which is what makes the account identity
``total_pnl == realized_pnl + unrealized_pnl`` hold at all times.

Money is plain ``float`` throughout, matching every other monetary column in
this project (``BacktestResult``, ``PaperDeployment.cash``). Introducing
``Decimal`` for one phase would create a second representation of money and a
conversion boundary to get wrong, so the arithmetic is done in float and
rounded to 2dp only at the reporting edge.
"""
from app.models import PaperDeployment
from app.schemas import PaperAccountSnapshot

# Reporting precision. The project rounds money to 2dp elsewhere (see
# ``strategy_runner``'s metrics), so the snapshot matches what the UI shows.
MONEY_DP = 2
PCT_DP = 2


def open_account(deployment: PaperDeployment) -> PaperDeployment:
    """Initialise the mutable paper state for a newly created deployment.

    The account opens fully funded: the configured capital becomes both the
    immutable ``initial_balance`` (``cash``) and the live ``balance``, with no
    realised P&L and no positions, trades or orders yet.

    Mutates in place and returns the same row; the caller owns the commit, so
    this composes with the router's existing single-transaction deploy.

    A redeploy after a stop creates a *new* ``PaperDeployment`` row, so each
    account starts clean and the previous run's history stays on its own row.
    """
    deployment.balance = float(deployment.cash)
    deployment.realized_pnl = 0.0
    deployment.last_bar_date = None
    deployment.last_error = None
    return deployment


def _marked_price(position) -> float:
    """Price to value a position at.

    An unmarked position (``last_price is None``) is marked at its entry
    price, so it contributes its cost basis to ``position_value`` and zero to
    ``unrealized_pnl`` rather than silently vanishing from the account.
    """
    if position.last_price is not None:
        return float(position.last_price)
    return float(position.avg_entry_price)


def snapshot(deployment: PaperDeployment) -> PaperAccountSnapshot:
    """Value a deployment's virtual account and return its derived totals.

        position_value   = sum(quantity * marked price)
        unrealized_pnl   = sum((marked price - avg_entry_price) * quantity)
        equity           = balance + position_value
        total_pnl        = equity - initial_balance
        total_return_pct = (total_pnl / initial_balance) * 100
    """
    initial_balance = float(deployment.cash or 0.0)
    cash_balance = float(deployment.balance or 0.0)

    positions = list(deployment.positions or [])
    position_value = 0.0
    unrealized_pnl = 0.0
    for position in positions:
        price = _marked_price(position)
        quantity = int(position.quantity or 0)
        position_value += quantity * price
        unrealized_pnl += (price - float(position.avg_entry_price or 0.0)) * quantity

    equity = cash_balance + position_value
    total_pnl = equity - initial_balance

    # ``DeployIn.cash`` is gt=0 so this cannot normally happen, but a snapshot
    # must never raise: report a flat 0% rather than dividing by zero.
    total_return_pct = (total_pnl / initial_balance * 100.0) if initial_balance else 0.0

    realized_pnl = float(deployment.realized_pnl or 0.0)
    trades = list(deployment.trades or [])

    return PaperAccountSnapshot(
        deployment_id=deployment.id,
        strategy_id=deployment.strategy_id,
        status=deployment.status.value,
        initial_balance=round(initial_balance, MONEY_DP),
        cash_balance=round(cash_balance, MONEY_DP),
        position_value=round(position_value, MONEY_DP),
        equity=round(equity, MONEY_DP),
        realized_pnl=round(realized_pnl, MONEY_DP),
        unrealized_pnl=round(unrealized_pnl, MONEY_DP),
        total_pnl=round(total_pnl, MONEY_DP),
        total_return_pct=round(total_return_pct, PCT_DP),
        open_positions=len(positions),
        closed_trades=len(trades),
        last_bar_date=(
            deployment.last_bar_date.isoformat() if deployment.last_bar_date else None
        ),
        last_error=deployment.last_error,
    )
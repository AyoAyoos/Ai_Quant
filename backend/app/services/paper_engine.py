"""
Virtual paper account — the Phase 1 foundation plus Phase 2 execution.

A deployment's virtual account is a virtual/dummy balance that strategy
signals move around. Nothing here talks to a broker, and nothing reaches a
real exchange: this module owns the *bookkeeping* only.

Phase 1 (foundation)
--------------------
* :func:`open_account` — seed the mutable account state from the deployment's
  config snapshot when a deployment is created.
* :func:`snapshot`     — value the account at a point in time.

Phase 2 (simulated execution)
----------------------------
* :func:`execute_buy`  — validate, fill and book a long entry.
* :func:`execute_sell` — validate, close a long position and book the trade.
* :func:`run_tick`     — apply one bar: decide, execute, mark, watermark.

Deliberately NOT here (later phases): a background scheduler, multi-asset
portfolio allocation, short selling, leverage, and any broker integration.

Scope limits (Phase 2 is long-only and deliberately simple)
-----------------------------------------------------------
* long only — a SELL with no open long position is rejected, never shorted
* one open position per (deployment, symbol); the unique constraint enforces it
* integer quantity, no fractional units, no pyramiding, no leverage/margin
* a SELL closes the whole position (no partial exits)

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

Fill price
----------
A tick fills at the bar's **close**. The strategy's decision for a bar is
derived from that bar's completed OHLC, so closing at the same bar's close keeps
``last_price`` and the fill price consistent — unrealised P&L and the cash
ledger then agree on one price. (Backtrader's own market orders fill at the
*next* bar's open; that one-bar lag is not reproduced here, and the difference
is deliberate and documented rather than accidental.)

Commission
----------
``PaperDeployment.commission_pct`` is a percentage of notional, matching
``strategy_runner``'s ``COMM_PERC`` broker configuration. Phase 2 charges it on
**both** legs of a round trip and stores the **total** on the completed
``PaperTrade.commission``, so ``net_pnl = gross_pnl - commission`` is directly
explainable from a single row (which is also what the Phase 1 check constraint
on the table asserts).

Money is plain ``float`` throughout, matching every other monetary column in
this project (``BacktestResult``, ``PaperDeployment.cash``). Introducing
``Decimal`` for one phase would create a second representation of money and a
conversion boundary to get wrong, so the arithmetic is done in float and
rounded to 2dp only at the reporting edge.
"""
import math
from datetime import datetime

from app.models import PaperDeployment, PaperOrder, PaperPosition, PaperTrade
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


# --------------------------------------------------------------------------- #
# Phase 2: simulated execution
# --------------------------------------------------------------------------- #
class PaperExecutionError(ValueError):
    """An order could not be simulated. Never leaves the account half-mutated."""


# Order statuses, mirroring the Phase 1 check constraint on ``paper_orders``.
ORDER_PENDING = "pending"
ORDER_FILLED = "filled"
ORDER_REJECTED = "rejected"
ORDER_CANCELLED = "cancelled"

SIDE_BUY = "buy"
SIDE_SELL = "sell"

ACTION_BUY = "buy"
ACTION_SELL = "sell"
ACTION_HOLD = "hold"


def validate_price(price, label: str = "price") -> float:
    """Reject a price that cannot be traded against.

    Guards the NaN / infinity / non-positive cases: any of them reaching the
    arithmetic below would poison ``balance`` and every derived snapshot, and
    ``NaN`` would silently satisfy every comparison.
    """
    try:
        number = float(price)
    except (TypeError, ValueError):
        raise PaperExecutionError(f"{label} is not a number ({price!r})") from None
    if math.isnan(number):
        raise PaperExecutionError(f"{label} is NaN")
    if math.isinf(number):
        raise PaperExecutionError(f"{label} is infinite")
    if number <= 0.0:
        raise PaperExecutionError(f"{label} must be > 0 (got {number})")
    return number


def commission_for(commission_pct: float, quantity: int, price: float) -> float:
    """Commission for one leg: ``commission_pct`` percent of notional.

    Mirrors ``strategy_runner``'s ``COMM_PERC`` / ``stocklike=True`` broker
    config, which charges ``commission * size * price`` per execution.
    """
    notional = abs(int(quantity)) * float(price)
    return float(commission_pct) / 100.0 * notional


def size_for_cash(
    cash: float,
    price: float,
    sizer_percents: float,
    quantity: int | None = None,
) -> int:
    """Whole-unit quantity to buy with ``sizer_percents`` of ``cash``.

    When ``quantity`` is given it is validated and returned as-is — that is the
    hook tests use to isolate the accounting from the sizing rule.

    Otherwise this reproduces ``bt.sizers.PercentSizer._getsizing``:
    ``cash / close * (percents / 100)``. The project adds that sizer with the
    default ``retint=False``, so backtrader hands the broker a float and the
    broker truncates it to whole units; ``int()`` here matches that, and keeps
    Phase 2 free of fractional quantity. Can return 0 when cash cannot afford a
    single unit, which the caller treats as insufficient funds.
    """
    price = validate_price(price, "price")
    if quantity is not None:
        units = int(quantity)
        if units < 1:
            raise PaperExecutionError(f"quantity must be >= 1 (got {quantity!r})")
        return units

    if float(cash) <= 0.0:
        return 0
    units = int(float(cash) / price * (float(sizer_percents) / 100.0))
    return max(units, 0)


def _at(bar_date):
    """Coerce a bar date for a NOT NULL datetime column.

    ``PaperPosition.opened_at`` and ``PaperTrade.entry_date`` are NOT NULL with
    no server default, so passing an explicit ``None`` would fail the insert
    rather than fall back to the column default.
    """
    return bar_date if bar_date is not None else datetime.utcnow()


def find_position(deployment: PaperDeployment, symbol: str) -> PaperPosition | None:
    """The deployment's open position for ``symbol``, if any (case-insensitive)."""
    wanted = symbol.strip().upper()
    for position in deployment.positions or []:
        if position.symbol.strip().upper() == wanted:
            return position
    return None


def _new_order(deployment, symbol, side, quantity, status, reason=None) -> PaperOrder:
    return PaperOrder(
        deployment_id=deployment.id,
        symbol=symbol.strip().upper(),
        side=side,
        quantity=int(quantity),
        order_type="market",
        status=status,
        reason=reason,
    )


def _requested_quantity(quantity: int | None, sized: int) -> int:
    """The lot size to record on a *rejected* order.

    An audit trail must show what was asked for, not a placeholder, so an
    explicit request is recorded verbatim. ``PaperOrder.quantity`` is
    constrained to ``> 0``, so a request that sized to nothing is recorded as the
    one unit that could not be afforded.
    """
    if quantity is not None:
        return max(int(quantity), 1)
    return max(int(sized), 1)


def execute_buy(
    deployment: PaperDeployment,
    symbol: str,
    price: float,
    bar_date=None,
    quantity: int | None = None,
) -> PaperOrder:
    """Simulate a long entry. Returns the (filled or rejected) order.

    Validation happens before any mutation, so a rejected buy leaves
    ``balance``, positions and trades exactly as they were. On success it
    debits ``quantity * price + commission`` from the balance and opens the
    position, marking it at ``price``.

    ``quantity=None`` sizes the order with the deployment's ``sizer_percents``.
    """
    symbol = symbol.strip().upper()
    price = validate_price(price, "fill price")
    balance = float(deployment.balance or 0.0)
    commission_pct = float(deployment.commission_pct or 0.0)

    existing = find_position(deployment, symbol)
    if existing is not None:
        return _new_order(
            deployment, symbol, SIDE_BUY, _requested_quantity(quantity, 1), ORDER_REJECTED,
            reason=(
                f"already holding {existing.quantity} {symbol} "
                f"(no pyramiding, one open position per symbol)"
            ),
        )

    units = size_for_cash(balance, price, deployment.sizer_percents, quantity)
    if units < 1:
        return _new_order(
            deployment, symbol, SIDE_BUY, _requested_quantity(quantity, units), ORDER_REJECTED,
            reason=f"balance {balance:.2f} cannot afford 1 unit at {price:.2f}",
        )

    commission = commission_for(commission_pct, units, price)
    cost = units * price + commission

    if cost > balance:
        return _new_order(
            deployment, symbol, SIDE_BUY, _requested_quantity(quantity, units), ORDER_REJECTED,
            reason=(
                f"insufficient funds: need {cost:.2f} "
                f"({units} x {price:.2f} + {commission:.2f} commission) "
                f"but balance is {balance:.2f}"
            ),
        )

    order = _new_order(deployment, symbol, SIDE_BUY, units, ORDER_FILLED)
    order.fill_price = price
    order.filled_at = bar_date
    deployment.balance = balance - cost

    position = PaperPosition(
        deployment_id=deployment.id,
        symbol=symbol,
        quantity=units,
        avg_entry_price=price,
        last_price=price,
        opened_at=_at(bar_date),
    )
    deployment.positions.append(position)
    return order


def execute_sell(
    deployment: PaperDeployment,
    symbol: str,
    price: float,
    bar_date=None,
    quantity: int | None = None,
) -> PaperOrder:
    """Simulate closing a long position. Returns the (filled or rejected) order.

    Long-only: with no open position the sell is rejected rather than opening a
    short. Phase 2 closes the entire position; ``quantity`` exists only to
    validate an expected size, it does not enable partial exits.

    The buy-leg commission is not stored on the position, so it is recomputed
    here from ``avg_entry_price``; the round-trip total then lands on
    ``PaperTrade.commission`` and ``net_pnl = gross_pnl - commission`` exactly.
    """
    symbol = symbol.strip().upper()
    price = validate_price(price, "fill price")
    commission_pct = float(deployment.commission_pct or 0.0)

    position = find_position(deployment, symbol)
    if position is None:
        return _new_order(
            deployment, symbol, SIDE_SELL, _requested_quantity(quantity, 1), ORDER_REJECTED,
            reason=f"no open position in {symbol} to sell (long-only, never shorts)",
        )

    units = int(position.quantity)
    if quantity is not None and int(quantity) != units:
        return _new_order(
            deployment, symbol, SIDE_SELL, units, ORDER_REJECTED,
            reason=(
                f"partial exits are not supported: holding {units} {symbol}, "
                f"asked to sell {int(quantity)}"
            ),
        )

    entry_price = float(position.avg_entry_price)
    entry_date = position.opened_at

    buy_commission = commission_for(commission_pct, units, entry_price)
    sell_commission = commission_for(commission_pct, units, price)
    total_commission = buy_commission + sell_commission

    gross_pnl = (price - entry_price) * units
    net_pnl = gross_pnl - total_commission

    balance = float(deployment.balance or 0.0)
    deployment.balance = balance + (units * price - sell_commission)
    deployment.realized_pnl = float(deployment.realized_pnl or 0.0) + net_pnl

    trade = PaperTrade(
        deployment_id=deployment.id,
        symbol=symbol,
        direction="long",  # long-only book
        quantity=units,
        entry_price=entry_price,
        exit_price=price,
        entry_date=_at(entry_date or bar_date),
        exit_date=_at(bar_date),
        gross_pnl=gross_pnl,
        commission=total_commission,
        net_pnl=net_pnl,
        won=net_pnl >= 0.0,
    )
    deployment.trades.append(trade)

    order = _new_order(deployment, symbol, SIDE_SELL, units, ORDER_FILLED)
    order.fill_price = price
    order.filled_at = bar_date

    # Phase 1 models one open position per (deployment, symbol), so closing is
    # a removal rather than a quantity update.
    deployment.positions.remove(position)
    return order


def mark_positions(deployment: PaperDeployment, price: float) -> int:
    """Re-mark every open position at ``price``; returns how many moved.

    Runs on every processed bar, including HOLD, which is what makes unrealised
    P&L track the market between trades.
    """
    price = validate_price(price, "mark price")
    marked = 0
    for position in deployment.positions or []:
        position.last_price = price
        marked += 1
    return marked


def run_tick(
    deployment: PaperDeployment,
    bar,
    action: str,
    quantity: int | None = None,
) -> dict:
    """Process one bar: execute the decided action, then re-mark and watermark.

    ``action`` is one of ``buy`` / ``sell`` / ``hold`` and normally comes from
    the strategy replay in :mod:`app.services.paper_signals`. This function
    performs no strategy interpretation itself and never touches a subprocess,
    so it can be driven directly from synthetic bars in tests.

    The ``last_bar_date`` watermark advances whenever the bar was processed —
    including HOLD and a rejected order — because the bar *was* consumed.
    Duplicates are refused by the caller (:mod:`app.services.paper_bars`
    returns nothing at or before the watermark), so this cannot run twice for
    the same bar.

    Returns a small dict for the router to fold into its response.
    """
    action = (action or ACTION_HOLD).strip().lower()
    if action not in (ACTION_BUY, ACTION_SELL, ACTION_HOLD):
        raise PaperExecutionError(f"unknown action {action!r}")

    bar_date = bar.bar_date
    price = bar.close

    order = None
    if action == ACTION_BUY:
        order = execute_buy(
            deployment, bar.symbol, price, bar_date=bar_date, quantity=quantity
        )
    elif action == ACTION_SELL:
        order = execute_sell(
            deployment, bar.symbol, price, bar_date=bar_date, quantity=quantity
        )

    marked = mark_positions(deployment, price)

    deployment.last_bar_date = bar_date
    deployment.last_error = order.reason if (order and order.status == ORDER_REJECTED) else None

    return {
        "action": action,
        "bar_date": bar_date,
        "price": price,
        "order": order,
        "marked_positions": marked,
    }
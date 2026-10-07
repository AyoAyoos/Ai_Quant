"""
Simulated paper-trading execution engine.

100% simulation: no broker, no live orders, no real money. A paper tick
advances ONE cached NIFTY market bar, replays the DEPLOYED strategy's own
code over the data slice ``[first bar .. current bar]`` in the same
sandboxed worker the backtester uses, reads the end-of-slice broker
position as the strategy's signal, and applies deterministic simulated
fills against the virtual account:

* long-only, integer quantities, no leverage, no margin, no short selling
* one open position per deployment/symbol
* commission on every simulated fill, exactly like the backtester
* fill price is always the processed bar's close (documented, deterministic)
* HOLD never creates orders, trades, or markers
* rejected orders are STORED as rejected — never rendered as fills

The trading decision always comes from the strategy code. Nothing here
invents signals, and no LLM is involved.

Signal timing note: the replay slice ends at the tick's bar, so an order
the strategy *places* on that bar (market orders fill on the next bar,
Close orders at the next bar's close) is only *filled* inside the replay
on the following tick. The paper signal therefore lags order placement by
one bar — the same lag a live deployment of the strategy would exhibit.
"""
import csv
import tempfile
from pathlib import Path

from app.services.backtest_service import (
    BacktestError,
    BacktestTimeout,
    run_backtest_sandboxed,
)
from app.services.paper_bars import (
    PaperBarsError,
    load_bars,
    select_next_bar,
)
from app.services.strategy_runner import TIMEOUT_DEFAULT_SECONDS


class PaperTickError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Pure account helpers (unit-testable without a database)
# --------------------------------------------------------------------------- #
def balance_of(deployment) -> float:
    """Current virtual cash. Pre-ledger rows (cash_balance NULL) read as untouched."""
    if deployment.cash_balance is not None:
        return float(deployment.cash_balance)
    return float(deployment.cash)


def realized_of(deployment) -> float:
    return float(deployment.realized_pnl or 0.0)


def map_signal(slice_long: bool, has_open_position: bool) -> tuple[str, str]:
    """Map (strategy signal, stored position) to (signal, executed action).

    The strategy is long/flat at the end of its replay slice. We are
    long-only, so a flat-or-short end state while holding a simulated long
    means SELL (exit); we never open simulated shorts.
    """
    if slice_long:
        if has_open_position:
            return ("BUY", "HOLD")  # signal says buy, but one position is already open
        return ("BUY", "BUY")
    if has_open_position:
        return ("SELL", "SELL")
    return ("HOLD", "HOLD")


class OrderRejected(Exception):
    """A simulated order that cannot be filled (carries the human reason)."""


def compute_buy_fill(
    close: float,
    cash_balance: float,
    commission_pct: float,
    sizer_percents: float,
) -> dict:
    """Size a simulated BUY at ``close``. Raises :class:`OrderRejected`.

    Mirrors backtrader's PercentSizer (``sizer_percents``% of available cash)
    floored to integer units, then refuses when even one unit is
    unaffordable including commission — no leverage, no margin, no partial.
    """
    if close <= 0:
        raise OrderRejected(f"bar close {close} is not tradeable")
    rate = float(commission_pct) / 100.0
    target_cash = float(cash_balance) * (float(sizer_percents) / 100.0)
    quantity = int(target_cash // (close * (1.0 + rate)))
    if quantity < 1:
        raise OrderRejected(
            f"insufficient virtual cash for one unit at {close:.2f} "
            f"(balance {cash_balance:.2f})"
        )
    commission = quantity * close * rate
    cost = quantity * close + commission
    if cost > cash_balance:
        # Floor division already guards this; kept as a no-leverage invariant.
        raise OrderRejected(
            f"order cost {cost:.2f} exceeds virtual balance {cash_balance:.2f}"
        )
    return {
        "quantity": quantity,
        "price": round(close, 2),
        "commission": round(commission, 2),
        "cost": round(cost, 2),
    }


def compute_sell_fill(close: float, position, commission_pct: float) -> dict:
    """Close a whole simulated long at ``close``. No partial exits."""
    if close <= 0:
        raise PaperTickError(f"bar close {close} is not tradeable")
    rate = float(commission_pct) / 100.0
    quantity = int(position.quantity)
    entry_commission = quantity * float(position.avg_price) * rate
    exit_commission = quantity * close * rate
    gross = (close - float(position.avg_price)) * quantity
    net = gross - entry_commission - exit_commission
    return {
        "quantity": quantity,
        "price": round(close, 2),
        "commission": round(exit_commission, 2),
        "proceeds": round(quantity * close - exit_commission, 2),
        "pnl": round(gross, 2),
        "pnl_net": round(net, 2),
    }


def account_snapshot(
    deployment,
    positions: list,
    completed_trades: int,
    last_close: float | None,
) -> dict:
    """Authoritative virtual-account numbers. The frontend must not recompute these."""
    from app.models import DeploymentStatus

    starting = float(deployment.cash)
    balance = balance_of(deployment)
    realized = realized_of(deployment)
    unrealized: float | None = None
    if last_close is not None:
        unrealized = round(
            sum((float(last_close) - float(p.avg_price)) * int(p.quantity) for p in positions),
            2,
        )
    equity = round(balance + (unrealized or 0.0), 2)
    total = round(equity - starting, 2)
    return {
        "deployment_id": deployment.id,
        "strategy_id": deployment.strategy_id,
        "status": deployment.status.value,
        "starting_cash": starting,
        "cash_balance": round(balance, 2),
        "equity": equity,
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": unrealized,
        "total_pnl": total,
        "return_pct": round(total / starting * 100.0, 4) if starting else None,
        "open_positions": len(positions),
        "completed_trades": int(completed_trades),
        "last_bar_date": deployment.last_bar_date,
        "last_error": deployment.last_error,
        "deployed_at": deployment.deployed_at.isoformat() if deployment.deployed_at else None,
        "stopped_at": deployment.stopped_at.isoformat() if deployment.stopped_at else None,
        "is_active": deployment.status == DeploymentStatus.active,
    }


# --------------------------------------------------------------------------- #
# Tick orchestration (database)
# --------------------------------------------------------------------------- #
def _write_slice_csv(slice_bars: list[dict]) -> Path:
    """Materialise the replay slice as the CSV shape the worker expects."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", prefix="paper_slice_", delete=False, newline=""
    )
    try:
        writer = csv.DictWriter(
            handle, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"]
        )
        writer.writeheader()
        for bar in slice_bars:
            writer.writerow(
                {
                    "Date": bar["date"],
                    "Open": bar["open"],
                    "High": bar["high"],
                    "Low": bar["low"],
                    "Close": bar["close"],
                    "Volume": bar.get("volume", 0),
                }
            )
    finally:
        handle.close()
    return Path(handle.name)


def _is_warmup_insufficiency(exc: BaseException, slice_len: int) -> bool:
    """True when the replay failed only because the slice is too short.

    Backtrader 1.9.78.123 raises ``IndexError: array assignment index out of
    range`` from its indicator pre-roll (e.g. EMA/SMA ``once()``) whenever the
    data slice is shorter than the indicator's minimum period. That is not a
    strategy bug — it means the deployment has not yet replayed enough history
    for the strategy to evaluate. Only treat short slices as warmup so a real
    IndexError on a long slice still surfaces as a tick failure.
    """
    if slice_len >= 250:
        return False
    return "index out of range" in str(exc).lower()


def _warmup_hold_result(deployment, strategy, bar: dict, note: str) -> dict:
    """Honest HOLD that still advances the watermark past a warmup bar."""
    deployment.last_bar_date = bar["date"]
    deployment.last_error = None
    balance = balance_of(deployment)
    return {
        "deployment_id": deployment.id,
        "strategy_id": strategy.id,
        "bar_date": bar["date"],
        "signal": "HOLD",
        "action": "HOLD",
        "price": round(bar["close"], 2),
        "quantity": 0,
        "order_id": None,
        "order_status": None,
        "trade_id": None,
        "pnl_net": None,
        "cash_balance": round(balance, 2),
        "equity": round(balance, 2),
        "realized_pnl": realized_of(deployment),
        "note": note,
    }


def run_paper_tick(
    db,
    strategy,
    deployment,
    requested_date: str | None = None,
    timeout_seconds: int = TIMEOUT_DEFAULT_SECONDS,
) -> dict:
    """Advance one cached market bar and apply the strategy's simulated decision.

    Returns the tick result dict (see ``PaperTickOut``). The deployment
    watermark advances exactly one bar per successful tick and failed ticks
    record ``last_error`` without moving the watermark.
    """
    from app.models import PaperOrder, PaperPosition, PaperTrade

    symbol = (strategy.market or "NIFTY50").strip().upper()

    try:
        bars = load_bars(strategy.market or "NIFTY50")
    except PaperBarsError as exc:
        deployment.last_error = str(exc)
        db.commit()
        raise PaperTickError(str(exc)) from exc

    try:
        bar = select_next_bar(bars, deployment.last_bar_date, requested_date)
    except PaperBarsError as exc:
        deployment.last_error = str(exc)
        db.commit()
        raise PaperTickError(str(exc)) from exc

    end_index = next(i for i, b in enumerate(bars) if b["date"] == bar["date"])
    slice_bars = bars[: end_index + 1]

    if len(slice_bars) < 2:
        # One bar is not a replay: the worker needs >= 2 rows and no
        # strategy can form a signal from a single bar. Honest HOLD that
        # still advances the watermark past the warmup bar.
        deployment.last_bar_date = bar["date"]
        deployment.last_error = None
        db.commit()
        balance = balance_of(deployment)
        return {
            "deployment_id": deployment.id,
            "strategy_id": strategy.id,
            "bar_date": bar["date"],
            "signal": "HOLD",
            "action": "HOLD",
            "price": round(bar["close"], 2),
            "quantity": 0,
            "order_id": None,
            "order_status": None,
            "trade_id": None,
            "pnl_net": None,
            "cash_balance": round(balance, 2),
            "equity": round(balance, 2),
            "realized_pnl": realized_of(deployment),
            "note": "warmup bar: single-bar history cannot form a strategy signal",
        }

    slice_path = _write_slice_csv(slice_bars)
    try:
        try:
            metrics = run_backtest_sandboxed(
                code=strategy.generated_code,
                data_path=str(slice_path),
                cash=float(deployment.cash),
                commission_pct=float(deployment.commission_pct),
                sizer_percents=float(deployment.sizer_percents),
                timeout_seconds=timeout_seconds,
            )
        except (BacktestError, BacktestTimeout) as exc:
            if _is_warmup_insufficiency(exc, len(slice_bars)):
                db.rollback()
                result = _warmup_hold_result(
                    deployment,
                    strategy,
                    bar,
                    f"warmup bar {len(slice_bars)}: insufficient history for "
                    "strategy indicators — HOLD, watermark advanced",
                )
                db.commit()
                return result
            deployment.last_error = f"signal replay failed on {bar['date']}: {exc}"
            db.commit()
            raise PaperTickError(deployment.last_error) from exc
    finally:
        try:
            slice_path.unlink(missing_ok=True)
        except OSError:
            pass

    open_position = metrics.get("open_position") or {}
    slice_long = int(open_position.get("size") or 0) > 0

    stored = (
        db.query(PaperPosition)
        .filter(
            PaperPosition.deployment_id == deployment.id,
            PaperPosition.symbol == symbol,
        )
        .first()
    )
    signal, action = map_signal(slice_long, stored is not None)
    close = float(bar["close"])
    balance = balance_of(deployment)

    result = {
        "deployment_id": deployment.id,
        "strategy_id": strategy.id,
        "bar_date": bar["date"],
        "signal": signal,
        "action": "HOLD",
        "price": round(close, 2),
        "quantity": 0,
        "order_id": None,
        "order_status": None,
        "trade_id": None,
        "pnl_net": None,
        "cash_balance": round(balance, 2),
        "equity": round(balance, 2),
        "realized_pnl": realized_of(deployment),
        "note": None,
    }

    if action == "BUY":
        try:
            fill = compute_buy_fill(
                close, balance, float(deployment.commission_pct),
                float(deployment.sizer_percents),
            )
        except OrderRejected as exc:
            order = PaperOrder(
                deployment_id=deployment.id,
                symbol=symbol,
                side="BUY",
                quantity=0,
                price=round(close, 2),
                bar_date=bar["date"],
                status="rejected",
                commission=0.0,
                note=str(exc),
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            deployment.last_bar_date = bar["date"]
            deployment.last_error = str(exc)
            db.commit()
            result.update(
                {
                    "order_id": order.id,
                    "order_status": "rejected",
                    "note": f"BUY signal rejected: {exc}",
                }
            )
            return result
        order = PaperOrder(
            deployment_id=deployment.id,
            symbol=symbol,
            side="BUY",
            quantity=fill["quantity"],
            price=fill["price"],
            bar_date=bar["date"],
            status="filled",
            commission=fill["commission"],
        )
        db.add(order)
        db.flush()
        db.add(
            PaperPosition(
                deployment_id=deployment.id,
                symbol=symbol,
                quantity=fill["quantity"],
                avg_price=fill["price"],
                entry_date=bar["date"],
            )
        )
        deployment.cash_balance = round(balance - fill["cost"], 2)
        deployment.last_bar_date = bar["date"]
        deployment.last_error = None
        db.commit()
        db.refresh(order)
        balance = balance_of(deployment)
        result.update(
            {
                "action": "BUY",
                "quantity": fill["quantity"],
                "order_id": order.id,
                "order_status": "filled",
                "cash_balance": round(balance, 2),
                "equity": round(balance + fill["quantity"] * close, 2),
                "note": (
                    f"simulated BUY {fill['quantity']} {symbol} @ {fill['price']:.2f} "
                    f"on {bar['date']}"
                ),
            }
        )
        return result

    if action == "SELL" and stored is not None:
        fill = compute_sell_fill(close, stored, float(deployment.commission_pct))
        buy_order = PaperOrder(
            deployment_id=deployment.id,
            symbol=symbol,
            side="SELL",
            quantity=fill["quantity"],
            price=fill["price"],
            bar_date=bar["date"],
            status="filled",
            commission=fill["commission"],
        )
        db.add(buy_order)
        db.flush()
        trade = PaperTrade(
            deployment_id=deployment.id,
            symbol=symbol,
            quantity=fill["quantity"],
            entry_price=float(stored.avg_price),
            exit_price=fill["price"],
            entry_date=stored.entry_date,
            exit_date=bar["date"],
            pnl=fill["pnl"],
            pnl_net=fill["pnl_net"],
            exit_order_id=buy_order.id,
        )
        db.add(trade)
        db.flush()
        db.delete(stored)
        deployment.cash_balance = round(balance + fill["proceeds"], 2)
        deployment.realized_pnl = round(realized_of(deployment) + fill["pnl_net"], 2)
        deployment.last_bar_date = bar["date"]
        deployment.last_error = None
        db.commit()
        db.refresh(buy_order)
        db.refresh(trade)
        balance = balance_of(deployment)
        result.update(
            {
                "action": "SELL",
                "quantity": fill["quantity"],
                "order_id": buy_order.id,
                "order_status": "filled",
                "trade_id": trade.id,
                "pnl_net": fill["pnl_net"],
                "cash_balance": round(balance, 2),
                "equity": round(balance, 2),
                "realized_pnl": realized_of(deployment),
                "note": (
                    f"simulated SELL {fill['quantity']} {symbol} @ {fill['price']:.2f} "
                    f"on {bar['date']} (net {fill['pnl_net']:+.2f})"
                ),
            }
        )
        return result

    # HOLD: no order, no position change — only the watermark moves.
    deployment.last_bar_date = bar["date"]
    deployment.last_error = None
    db.commit()
    unrealized = 0.0
    if stored is not None:
        unrealized = (close - float(stored.avg_price)) * int(stored.quantity)
    result.update(
        {
            "equity": round(balance + unrealized, 2),
            "note": (
                "strategy is flat and the account holds no position"
                if stored is None
                else "holding the open simulated position (no exit signal)"
                if signal == "BUY"
                else "strategy signal is HOLD"
            ),
        }
    )
    if signal == "BUY" and stored is not None:
        result["note"] = "BUY signal ignored: one simulated position is already open"
    return result

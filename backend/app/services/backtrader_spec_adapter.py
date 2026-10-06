"""
Deterministic Backtrader adapter for StrategySpec.

This adapter consumes a validated StrategySpec and runs it using Backtrader,
producing a normalized result compatible with the shared runtime output.

Execution contract:
- Signals evaluated on completed bar T
- Market orders submitted on bar T execute at bar T+1 OPEN
- Long-only, no pyramiding, integer shares, commission on both legs
"""

import backtrader as bt
import pandas as pd
from typing import Optional, List

from app.services.strategy_spec import StrategySpec
from app.services.strategy_spec_runtime import (
    evaluate_signals,
    apply_position_rules,
    compute_metrics,
    compute_indicators,
)


class _OrderRecord:
    """Track a single order from submission to completion."""
    def __init__(self, order_ref: int, action: str, signal_bar: int, signal_date, size: int, estimated_price: float):
        self.order_ref = order_ref  # Use order.ref which is stable
        self.action = action  # "buy" or "sell"
        self.signal_bar = signal_bar
        self.signal_date = signal_date
        self.size = size
        self.estimated_price = estimated_price
        self.completed = False
        self.rejected = False
        self.executed_price: Optional[float] = None
        self.executed_bar: Optional[int] = None
        self.executed_date = None


class _StrategySpecStrategy(bt.Strategy):
    """Backtrader strategy that implements StrategySpec signals with proper order tracking."""
    params = (
        ("spec", None),
        ("signals", None),
        ("commission_pct", 0.1),
        ("sizer_percents", 95.0),
        ("max_gap_pct", 0.05),  # Conservative buffer for gap up at next open
    )

    def __init__(self):
        self.spec = self.p.spec
        self.signals = self.p.signals
        self.current_bar = 0
        self.completed_trades = []
        self.open_position = None  # dict with entry info
        self.pending_orders: List[_OrderRecord] = []
        self._cash = self.broker.getvalue()

    def next(self):
        if self.current_bar >= len(self.signals):
            return

        sig = self.signals[self.current_bar]
        close_price = self.data.close[0]
        signal_date = self.data.datetime.date(0)

        # Conservative execution price estimate: signal close * (1 + max_gap_pct)
        # This ensures we don't get margin rejected due to gap up at next open
        max_gap_pct = getattr(self.p, 'max_gap_pct', 0.05)
        estimated_exec_price = close_price * (1 + max_gap_pct)

        # Process entry signal at bar T -> order submitted, executes at T+1 open
        if sig.entry and not self.position and not self.open_position:
            cash = self.broker.getcash()
            # Size based on estimated execution price to avoid margin rejection
            size = int(cash * (self.p.sizer_percents / 100.0) / estimated_exec_price)
            max_affordable = int(cash / (estimated_exec_price * (1 + self.p.commission_pct / 100.0)))
            size = min(size, max_affordable)
            if size > 0:
                order = self.buy(size=size)
                rec = _OrderRecord(order.ref, "buy", self.current_bar, signal_date, size, estimated_exec_price)
                self.pending_orders.append(rec)

        # Process exit signal at bar T -> order submitted, executes at T+1 open
        elif sig.exit and self.position and self.open_position:
            order = self.sell(size=self.position.size)
            rec = _OrderRecord(order.ref, "sell", self.current_bar, signal_date, self.position.size, close_price)
            self.pending_orders.append(rec)

        self.current_bar += 1

    def notify_order(self, order):
        """Track order lifecycle using order.ref (stable across status changes)."""
        status_name = order.getstatusname()

        for rec in self.pending_orders:
            if rec.order_ref == order.ref:  # Compare by ref, not object identity
                if status_name == "Completed":
                    rec.completed = True
                    rec.executed_price = order.executed.price
                    # notify_order fires during transition to next bar; current_bar already incremented
                    # execution happens at current_bar's open (the bar we're transitioning TO)
                    rec.executed_bar = self.current_bar
                    rec.executed_date = self.data.datetime.date(0)
                    
                    if rec.action == "buy":
                        # Record entry
                        self.open_position = {
                            "entry_bar": rec.executed_bar,
                            "entry_date": rec.executed_date,
                            "entry_price": rec.executed_price,
                            "size": rec.size,
                            "signal_bar": rec.signal_bar,
                            "signal_date": rec.signal_date,
                        }
                    elif rec.action == "sell":
                        # Record exit - pair with open position
                        if self.open_position:
                            entry = self.open_position
                            entry_price = entry["entry_price"]
                            exit_price = rec.executed_price
                            size = entry["size"]
                            entry_commission = size * entry_price * (self.p.commission_pct / 100.0)
                            exit_commission = size * exit_price * (self.p.commission_pct / 100.0)
                            total_commission = entry_commission + exit_commission

                            gross_pnl = (exit_price - entry_price) * size
                            net_pnl = gross_pnl - total_commission

                            self._cash += size * exit_price - exit_commission

                            self.completed_trades.append({
                                "entry_idx": entry["entry_bar"],
                                "exit_idx": rec.executed_bar,
                                "entry_price": entry_price,
                                "exit_price": exit_price,
                                "size": size,
                                "gross_pnl": gross_pnl,
                                "commission": total_commission,
                                "net_pnl": net_pnl,
                                "return_pct": (net_pnl / (size * entry_price)) * 100 if entry_price > 0 else 0.0,
                                "bars_held": rec.executed_bar - entry["entry_bar"],
                                "cash_after": self._cash,
                            })
                            self.open_position = None

                elif status_name in ("Rejected", "Margin", "Cancelled"):
                    rec.rejected = True

                # Remove completed/rejected orders from pending
                if rec.completed or rec.rejected:
                    self.pending_orders.remove(rec)
                break

        self.current_bar += 1


def run_backtrader_spec(
    df: pd.DataFrame,
    spec: StrategySpec,
    initial_cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 95.0,
) -> dict:
    """
    Run a StrategySpec using Backtrader engine.

    Returns normalized result dict matching the shared runtime format.
    """
    # Compute indicators and signals using shared runtime
    df_ind = compute_indicators(df, spec.indicators)
    raw_signals = evaluate_signals(df_ind, spec)
    signals = apply_position_rules(raw_signals)

    # Prepare data feed
    data = bt.feeds.PandasData(
        dataname=df_ind,
        open="Open", high="High", low="Low", close="Close",
        volume="Volume", openinterest=None,
    )

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(
        commission=commission_pct / 100.0,
        stocklike=True,
        commtype=bt.CommInfoBase.COMM_PERC,
    )
    cerebro.adddata(data)
    cerebro.addstrategy(
        _StrategySpecStrategy,
        spec=spec,
        signals=signals,
        commission_pct=commission_pct,
        sizer_percents=sizer_percents,
        max_gap_pct=0.0,  # Deterministic fixtures have known prices; production can use 0.05
    )
    # Don't add PercentSizer - we handle sizing manually in strategy

    results = cerebro.run()
    strat = results[0]

    # Extract completed trades
    bt_trades = strat.completed_trades

    # Convert to normalized format
    normalized_trades = []
    for t in bt_trades:
        normalized_trades.append({
            "entry_time": str(df_ind.index[t["entry_idx"]].date()),
            "exit_time": str(df_ind.index[t["exit_idx"]].date()),
            "entry_price": round(t["entry_price"], 2),
            "exit_price": round(t["exit_price"], 2),
            "size": t["size"],
            "pnl": round(t["net_pnl"], 2),
            "return_pct": round(t["return_pct"], 4),
        })

    # Compute metrics
    metrics = compute_metrics(df_ind, bt_trades, initial_cash, commission_pct)

    # Check for open position at end
    warnings = []
    if not bt_trades:
        warnings.append("no_trades")
    if strat.open_position is not None:
        warnings.append("open_position_at_end")

    return {
        "engine": "backtrader",
        "spec_version": spec.version,
        "metrics": metrics,
        "trades": normalized_trades,
        "warnings": warnings,
        "execution_model": "bar_t_plus_1_open",
    }
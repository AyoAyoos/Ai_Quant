"""
Deterministic Backtesting.py adapter for StrategySpec.

This adapter consumes a validated StrategySpec and runs it using the
third-party Backtesting.py package, producing a normalized result
compatible with the shared runtime output.

Execution contract:
- Signals evaluated on completed bar T
- Market orders submitted on bar T execute at bar T+1 OPEN
- Long-only, no pyramiding, integer shares, commission on both legs
"""

from backtesting import Backtest, Strategy
import pandas as pd
import numpy as np

from app.services.strategy_spec import StrategySpec
from app.services.strategy_spec_runtime import (
    compute_indicators,
    evaluate_signals,
    apply_position_rules,
    compute_metrics,
)


class _StrategySpecBacktestingStrategy(Strategy):
    """Backtesting.py strategy that implements StrategySpec signals."""
    
    spec = None
    signals = None
    commission_pct = 0.1
    sizer_percents = 95.0
    max_gap_pct = 0.0  # Deterministic fixtures have known prices
    
    def init(self):
        # Pre-compute all indicators using pandas (matching shared runtime)
        self.indicators = {}
        for ind_spec in self.spec.indicators:
            if ind_spec.type == "sma":
                self.indicators[ind_spec.name] = self.I(
                    lambda x, p=ind_spec.period: pd.Series(x).rolling(p, min_periods=p).mean(),
                    self.data.Close,
                    name=ind_spec.name
                )
            elif ind_spec.type == "ema":
                self.indicators[ind_spec.name] = self.I(
                    lambda x, p=ind_spec.period: pd.Series(x).ewm(span=p, adjust=False, min_periods=p).mean(),
                    self.data.Close,
                    name=ind_spec.name
                )
            elif ind_spec.type == "rsi":
                self.indicators[ind_spec.name] = self.I(
                    self._rsi,
                    self.data.Close,
                    ind_spec.period,
                    name=ind_spec.name
                )
        
        self._entry_signals = [s.entry for s in self.signals]
        self._exit_signals = [s.exit for s in self.signals]
        self._current_idx = 0
    
    def _rsi(self, close: np.ndarray, period: int) -> np.ndarray:
        """RSI implementation matching shared runtime (Wilder's smoothing)."""
        close_series = pd.Series(close)
        delta = close_series.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1.0/period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1.0/period, adjust=False, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi.to_numpy()

    def next(self):
        if self._current_idx >= len(self._entry_signals):
            return

        entry_sig = self._entry_signals[self._current_idx]
        exit_sig = self._exit_signals[self._current_idx]
        # Use current bar's close for sizing estimation (execution will be at next bar's open)
        close_price = self.data.Close[-1]
        # Conservative execution price estimate
        estimated_exec_price = close_price * (1 + self.max_gap_pct)

        # Available cash = equity - position value (for long-only, position value = size * current_price)
        if self.position:
            position_value = self.position.size * close_price
            available_cash = self.equity - position_value
        else:
            available_cash = self.equity

        if entry_sig and not self.position:
            # Size using PercentSizer logic: percent of available cash
            # Use estimated execution price for sizing to avoid margin issues
            size = int(available_cash * (self.sizer_percents / 100.0) / estimated_exec_price)
            # Ensure we can afford it at execution
            max_affordable = int(available_cash / (estimated_exec_price * (1 + self.commission_pct / 100.0)))
            size = min(size, max_affordable)
            if size > 0:
                self.buy(size=size)

        elif exit_sig and self.position:
            self.position.close()

        self._current_idx += 1


def run_backtesting_py_spec(
    df: pd.DataFrame,
    spec: StrategySpec,
    initial_cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 95.0,
) -> dict:
    """
    Run a StrategySpec using Backtesting.py engine.

    Returns normalized result dict matching the shared runtime format.
    """
    # Compute indicators and signals using shared runtime
    df_ind = compute_indicators(df, spec.indicators)
    raw_signals = evaluate_signals(df_ind, spec)
    signals = apply_position_rules(raw_signals)

    # Prepare data for Backtesting.py (expects Open, High, Low, Close, Volume)
    bt_data = df_ind[["Open", "High", "Low", "Close", "Volume"]].copy()
    bt_data.index = pd.to_datetime(bt_data.index)

    # Inject signals into strategy class
    _StrategySpecBacktestingStrategy.spec = spec
    _StrategySpecBacktestingStrategy.signals = signals
    _StrategySpecBacktestingStrategy.commission_pct = commission_pct
    _StrategySpecBacktestingStrategy.sizer_percents = sizer_percents
    _StrategySpecBacktestingStrategy.max_gap_pct = 0.0  # Deterministic fixtures have known prices

    # Run backtest - DISABLE finalize_trades to avoid forced closure at end
    bt = Backtest(
        bt_data,
        _StrategySpecBacktestingStrategy,
        cash=initial_cash,
        commission=commission_pct / 100.0,
        exclusive_orders=True,  # One order at a time (long-only, no pyramiding)
        finalize_trades=False,  # Do NOT force-close at end
    )
    
    stats = bt.run()

    # Extract trades from stats._trades (reliable source)
    bt_trades_raw = stats._trades
    bt_trades = []
    cash = initial_cash
    for _, trade in bt_trades_raw.iterrows():
        entry_idx = int(trade.EntryBar)
        exit_idx = int(trade.ExitBar)
        entry_price = float(trade.EntryPrice)
        exit_price = float(trade.ExitPrice)
        size = int(trade.Size)
        gross_pnl = float(trade.PnL)  # This is net P&L after commission in Backtesting.py
        
        # Backtesting.py's PnL already includes commission
        # We need to decompose it to match our model
        entry_commission = size * entry_price * (commission_pct / 100.0)
        exit_commission = size * exit_price * (commission_pct / 100.0)
        total_commission = entry_commission + exit_commission
        net_pnl = gross_pnl  # Already net of commission
        gross_pnl = net_pnl + total_commission
        
        # Track cash like shared runtime: subtract entry cost, add exit proceeds
        cash -= size * entry_price + entry_commission
        cash += size * exit_price - exit_commission
        
        bt_trades.append({
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "size": size,
            "gross_pnl": gross_pnl,
            "commission": total_commission,
            "net_pnl": net_pnl,
            "return_pct": (net_pnl / (size * entry_price)) * 100 if entry_price > 0 else 0.0,
            "bars_held": exit_idx - entry_idx,
            "cash_after": cash,
        })

    # Convert to normalized format
    normalized_trades = []
    for t in bt_trades:
        normalized_trades.append({
            "entry_time": str(bt_data.index[t["entry_idx"]].date()),
            "exit_time": str(bt_data.index[t["exit_idx"]].date()),
            "entry_price": round(t["entry_price"], 2),
            "exit_price": round(t["exit_price"], 2),
            "size": t["size"],
            "pnl": round(t["net_pnl"], 2),
            "return_pct": round(t["return_pct"], 4),
        })

    # Compute metrics
    metrics = compute_metrics(df_ind, bt_trades, initial_cash, commission_pct)

    # Warnings
    warnings = []
    if not bt_trades:
        warnings.append("no_trades")
    # Check for open position at end (stats._trades doesn't include open positions)
    # We could check strategy instance but stats._trades is more reliable

    return {
        "engine": "backtesting.py",
        "spec_version": spec.version,
        "metrics": metrics,
        "trades": normalized_trades,
        "warnings": warnings,
        "execution_model": "bar_t_plus_1_open",
    }
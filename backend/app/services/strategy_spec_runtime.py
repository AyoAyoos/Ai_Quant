"""
Shared deterministic StrategySpec evaluation layer.

This module provides common indicator computation and signal evaluation logic
used by both Backtrader and Backtesting.py adapters. It contains NO engine-
specific code — only pure pandas/numpy operations on OHLCV data.

Rules:
- Signals evaluated on completed bar T (no look-ahead)
- Warm-up bars (NaN indicator values) cannot generate signals
- Long-only, no pyramiding, no shorting
- Entry while long -> ignored
- Exit while flat -> ignored
"""

from dataclasses import dataclass
from typing import Literal
import numpy as np
import pandas as pd

from app.services.strategy_spec import (
    StrategySpec,
    IndicatorSpec,
    ConditionSpec,
    IndicatorType,
    ConditionOperator,
)


@dataclass(frozen=True)
class Signal:
    """One evaluated signal for a single bar."""
    entry: bool
    exit: bool


def compute_indicators(df: pd.DataFrame, indicators: list[IndicatorSpec]) -> pd.DataFrame:
    """
    Compute all indicators for a StrategySpec and return a new DataFrame
    with indicator columns added (named by IndicatorSpec.name).
    """
    out = df.copy()
    for ind in indicators:
        if ind.type == "sma":
            out[ind.name] = out["Close"].rolling(window=ind.period, min_periods=ind.period).mean()
        elif ind.type == "ema":
            out[ind.name] = out["Close"].ewm(span=ind.period, adjust=False, min_periods=ind.period).mean()
        elif ind.type == "rsi":
            out[ind.name] = _compute_rsi(out["Close"], ind.period)
        else:
            raise ValueError(f"Unsupported indicator type: {ind.type}")
    return out


def _compute_rsi(close: pd.Series, period: int) -> pd.Series:
    """Compute RSI using Wilder's smoothing (standard definition)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _get_operand_value(df: pd.DataFrame, operand: str, idx: int) -> float | None:
    """Get the value of an operand (close or indicator) at index idx."""
    if operand == "close":
        return float(df.iloc[idx]["Close"])
    if operand in df.columns:
        val = df.iloc[idx][operand]
        return float(val) if pd.notna(val) else None
    raise ValueError(f"Unknown operand: {operand}")


def _get_right_value(df: pd.DataFrame, condition: ConditionSpec, idx: int) -> float | None:
    """Get the right-hand side value for a condition at index idx."""
    if condition.right_value is not None:
        return float(condition.right_value)
    if condition.right_indicator is not None:
        return _get_operand_value(df, condition.right_indicator, idx)
    return None


def evaluate_condition(df: pd.DataFrame, condition: ConditionSpec, idx: int) -> bool:
    """
    Evaluate a single condition at bar index idx.

    Returns False (not True) if any operand is NaN/warm-up — this prevents
    false signals during indicator warm-up periods.
    """
    left_val = _get_operand_value(df, condition.left, idx)
    right_val = _get_right_value(df, condition, idx)

    if left_val is None or right_val is None:
        return False

    op = condition.operator
    if op == "greater_than":
        return left_val > right_val
    elif op == "less_than":
        return left_val < right_val
    elif op == "crosses_above":
        if idx == 0:
            return False
        left_prev = _get_operand_value(df, condition.left, idx - 1)
        right_prev = _get_right_value(df, condition, idx - 1)
        if left_prev is None or right_prev is None:
            return False
        return left_prev <= right_prev and left_val > right_val
    elif op == "crosses_below":
        if idx == 0:
            return False
        left_prev = _get_operand_value(df, condition.left, idx - 1)
        right_prev = _get_right_value(df, condition, idx - 1)
        if left_prev is None or right_prev is None:
            return False
        return left_prev >= right_prev and left_val < right_val
    else:
        raise ValueError(f"Unsupported operator: {op}")


def evaluate_signals(df: pd.DataFrame, spec: StrategySpec) -> list[Signal]:
    """
    Evaluate entry/exit signals for every bar in the DataFrame.

    Returns a list of Signal (one per bar). Warm-up bars produce Signal(False, False).
    """
    signals = []
    for i in range(len(df)):
        entry = evaluate_condition(df, spec.entry, i)
        exit_ = evaluate_condition(df, spec.exit, i)
        signals.append(Signal(entry=entry, exit=exit_))
    return signals


def apply_position_rules(signals: list[Signal]) -> list[Signal]:
    """
    Apply long-only, no-pyramiding, no-shorting rules to raw signals.

    - Cannot enter while already long
    - Cannot exit while flat
    - Only one position at a time
    """
    filtered = []
    is_long = False
    for sig in signals:
        entry = sig.entry and not is_long
        exit_ = sig.exit and is_long
        filtered.append(Signal(entry=entry, exit=exit_))
        if entry:
            is_long = True
        elif exit_:
            is_long = False
    return filtered


def generate_trades(
    df: pd.DataFrame,
    signals: list[Signal],
    initial_cash: float,
    commission_pct: float,
    sizer_percents: float,
) -> list[dict]:
    """
    Simulate trade execution using deterministic sizing (matching PercentSizer behavior).

    Returns list of trade dicts with: entry_idx, exit_idx, entry_price, exit_price,
    size, gross_pnl, commission, net_pnl, return_pct, bars_held, cash_after.
    """
    trades = []
    position = None  # dict with keys: entry_idx, entry_price, size
    cash = initial_cash

    for i, sig in enumerate(signals):
        close_price = float(df.iloc[i]["Close"])

        if sig.entry and position is None:
            # Size: floor(cash * sizer_pct / 100 / close)
            size = int(cash * (sizer_percents / 100.0) / close_price)
            if size > 0:
                cost = size * close_price * (1 + commission_pct / 100.0)
                if cost <= cash:
                    position = {
                        "entry_idx": i,
                        "entry_price": close_price,
                        "size": size,
                        "entry_commission": size * close_price * (commission_pct / 100.0),
                        "cash_before": cash,
                    }
                    cash -= cost

        elif sig.exit and position is not None:
            # Close position
            size = position["size"]
            entry_price = position["entry_price"]
            entry_commission = position["entry_commission"]
            exit_commission = size * close_price * (commission_pct / 100.0)
            total_commission = entry_commission + exit_commission

            gross_pnl = (close_price - entry_price) * size
            net_pnl = gross_pnl - total_commission

            cash += size * close_price - exit_commission

            trades.append({
                "entry_idx": position["entry_idx"],
                "exit_idx": i,
                "entry_price": entry_price,
                "exit_price": close_price,
                "size": size,
                "gross_pnl": gross_pnl,
                "commission": total_commission,
                "net_pnl": net_pnl,
                "return_pct": (net_pnl / (position["size"] * entry_price)) * 100 if entry_price > 0 else 0.0,
                "bars_held": i - position["entry_idx"],
                "cash_after": cash,
            })
            position = None

    return trades


def compute_metrics(
    df: pd.DataFrame,
    trades: list[dict],
    initial_cash: float,
    commission_pct: float,
) -> dict:
    """Compute normalized backtest metrics from trades."""
    if not trades:
        final_equity = initial_cash
        return {
            "initial_cash": initial_cash,
            "final_equity": final_equity,
            "return_pct": 0.0,
            "trade_count": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": None,
            "total_commission": 0.0,
            "start_date": str(df.index[0].date()),
            "end_date": str(df.index[-1].date()),
            "bars_processed": len(df),
        }

    final_equity = trades[-1].get("cash_after", initial_cash)
    total_return = (final_equity / initial_cash - 1.0) * 100.0

    winning = sum(1 for t in trades if t["net_pnl"] > 0)
    losing = sum(1 for t in trades if t["net_pnl"] <= 0)
    win_rate = (winning / len(trades)) * 100.0 if trades else 0.0

    gross_profit = sum(t["gross_pnl"] for t in trades if t["gross_pnl"] > 0)
    gross_loss = abs(sum(t["gross_pnl"] for t in trades if t["gross_pnl"] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

    total_commission = sum(t["commission"] for t in trades)

    # Max drawdown from equity curve
    equity_curve = [initial_cash]
    for t in trades:
        equity_curve.append(t["cash_after"])
    equity_series = pd.Series(equity_curve)
    rolling_max = equity_series.expanding().max()
    drawdown = (equity_series - rolling_max) / rolling_max * 100.0
    max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0.0

    return {
        "initial_cash": initial_cash,
        "final_equity": final_equity,
        "return_pct": round(total_return, 4),
        "trade_count": len(trades),
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate_pct": round(win_rate, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor else None,
        "total_commission": round(total_commission, 4),
        "start_date": str(df.index[0].date()),
        "end_date": str(df.index[-1].date()),
        "bars_processed": len(df),
    }


def run_strategy_spec_backtest(
    df: pd.DataFrame,
    spec: StrategySpec,
    initial_cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 95.0,
) -> dict:
    """
    Complete StrategySpec backtest using shared runtime.

    Returns normalized result dict with metrics and trade list.
    """
    # Compute indicators
    df_with_indicators = compute_indicators(df, spec.indicators)

    # Evaluate raw signals
    raw_signals = evaluate_signals(df_with_indicators, spec)

    # Apply position rules
    signals = apply_position_rules(raw_signals)

    # Generate trades
    trades = generate_trades(df_with_indicators, signals, initial_cash, commission_pct, sizer_percents)

    # Compute metrics
    metrics = compute_metrics(df_with_indicators, trades, initial_cash, commission_pct)

    # Build normalized trade list for output
    normalized_trades = []
    for t in trades:
        normalized_trades.append({
            "entry_time": str(df_with_indicators.index[t["entry_idx"]].date()),
            "exit_time": str(df_with_indicators.index[t["exit_idx"]].date()),
            "entry_price": round(t["entry_price"], 2),
            "exit_price": round(t["exit_price"], 2),
            "size": t["size"],
            "pnl": round(t["net_pnl"], 2),
            "return_pct": round(t["return_pct"], 4),
        })

    return {
        "engine": "shared_runtime",
        "spec_version": spec.version,
        "metrics": metrics,
        "trades": normalized_trades,
        "warnings": ["no_trades"] if not trades else [],
        "execution_model": "bar_t_plus_1_open",
    }
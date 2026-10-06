"""
Cross-engine comparison service for StrategySpec validation.

Compares normalized Backtrader and Backtesting.py results to produce
objective comparison evidence. No LLM, no subjective verdicts.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd

from app.services.strategy_result import NormalizedResult, NormalizedTrade


@dataclass(frozen=True)
class ComparisonEvidence:
    """Objective comparison evidence between two engine results."""
    # Core metric deltas
    return_delta_pct: float
    max_drawdown_delta_pct: float
    win_rate_delta_pct: float
    final_equity_delta: float
    trade_count_delta: int
    total_commission_delta: float

    # Trade alignment (where practical)
    aligned_trades: int  # Number of trades with similar entry/exit dates
    trade_alignment_pct: float

    # Execution metadata
    engine_a: str
    engine_b: str
    execution_model_a: str
    execution_model_b: str

    # Warnings
    warnings: list[str]


def _align_trades(trades_a: list[NormalizedTrade], trades_b: list[NormalizedTrade]) -> list[tuple[NormalizedTrade, NormalizedTrade]]:
    """
    Align trades by entry/exit dates. Simple greedy matching by entry_time.
    Returns list of (trade_a, trade_b) pairs.
    """
    aligned = []
    used_b = set()
    
    for ta in trades_a:
        best_idx = -1
        best_score = 2  # Max 1 day difference on entry + 1 on exit = 2
        for j, tb in enumerate(trades_b):
            if j in used_b:
                continue
            entry_diff = abs(pd.Timestamp(ta.entry_time) - pd.Timestamp(tb.entry_time)).days
            exit_diff = abs(pd.Timestamp(ta.exit_time) - pd.Timestamp(tb.exit_time)).days
            score = entry_diff + exit_diff
            if score < best_score:
                best_score = score
                best_idx = j
        if best_idx >= 0:
            aligned.append((ta, trades_b[best_idx]))
            used_b.add(best_idx)
    
    return aligned


def compare_results(result_a: NormalizedResult, result_b: NormalizedResult) -> ComparisonEvidence:
    """
    Compare two normalized results and return objective evidence.
    
    Does NOT issue a VALID/INVALID verdict - only produces measurable differences.
    """
    m_a = result_a.metrics
    m_b = result_b.metrics

    # Core metric deltas
    return_delta = abs(m_a.return_pct - m_b.return_pct)
    dd_delta = abs(m_a.max_drawdown_pct - m_b.max_drawdown_pct)
    wr_delta = abs(m_a.win_rate_pct - m_b.win_rate_pct)
    equity_delta = abs(m_a.final_equity - m_b.final_equity)
    trade_count_delta = abs(m_a.trade_count - m_b.trade_count)
    commission_delta = abs(m_a.total_commission - m_b.total_commission)

    # Trade alignment
    aligned = _align_trades(result_a.trades, result_b.trades)
    aligned_count = len(aligned)
    total_trades = max(len(result_a.trades), len(result_b.trades))
    alignment_pct = (aligned_count / total_trades * 100.0) if total_trades > 0 else 100.0

    # Warnings
    warnings = []
    if return_delta > 5.0:
        warnings.append(f"return_delta_pct > 5%: {return_delta:.2f}%")
    if dd_delta > 5.0:
        warnings.append(f"max_drawdown_delta_pct > 5%: {dd_delta:.2f}%")
    if trade_count_delta > 2:
        warnings.append(f"trade_count_delta > 2: {trade_count_delta}")
    if alignment_pct < 80.0 and total_trades > 0:
        warnings.append(f"low_trade_alignment: {alignment_pct:.1f}%")

    return ComparisonEvidence(
        return_delta_pct=round(return_delta, 4),
        max_drawdown_delta_pct=round(dd_delta, 4),
        win_rate_delta_pct=round(wr_delta, 4),
        final_equity_delta=round(equity_delta, 2),
        trade_count_delta=trade_count_delta,
        total_commission_delta=round(commission_delta, 2),
        aligned_trades=aligned_count,
        trade_alignment_pct=round(alignment_pct, 2),
        engine_a=result_a.engine,
        engine_b=result_b.engine,
        execution_model_a=result_a.execution_model,
        execution_model_b=result_b.execution_model,
        warnings=warnings,
    )


def run_dual_engine_backtest(
    df: pd.DataFrame,
    spec,
    initial_cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 95.0,
) -> tuple[NormalizedResult, NormalizedResult, ComparisonEvidence]:
    """
    Run StrategySpec on both engines and compare.

    Returns (backtrader_result, backtesting_result, comparison_evidence).
    """
    from app.services.backtrader_spec_adapter import run_backtrader_spec
    from app.services.backtesting_py_adapter import run_backtesting_py_spec
    from app.services.strategy_result import to_normalized_result

    # Run both engines
    bt_raw = run_backtrader_spec(df, spec, initial_cash, commission_pct, sizer_percents)
    bp_raw = run_backtesting_py_spec(df, spec, initial_cash, commission_pct, sizer_percents)

    # Normalize
    bt_result = to_normalized_result(bt_raw)
    bp_result = to_normalized_result(bp_raw)

    # Compare
    evidence = compare_results(bt_result, bp_result)

    return bt_result, bp_result, evidence
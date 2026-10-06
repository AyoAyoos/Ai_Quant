"""
High-level orchestration service for independent strategy validation.

This service coordinates the complete validation pipeline:
1. Receives validated StrategySpec
2. Runs Backtrader StrategySpec adapter
3. Runs Backtesting.py StrategySpec adapter
4. Normalizes results
4. Calls strategy_validation_compare
5. Evaluates engine agreement
6. Incorporates paper evidence when available
7. Evaluates deterministic risk/performance rules
8. Produces final verdict + reason codes + evidence
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal
from enum import Enum

import pandas as pd

from app.services.strategy_spec import StrategySpec, parse_strategy_spec
from app.services.backtrader_spec_adapter import run_backtrader_spec
from app.services.backtesting_py_adapter import run_backtesting_py_spec
from app.services.strategy_validation_compare import (
    compare_results,
    ComparisonEvidence,
    run_dual_engine_backtest,
)
from app.services.strategy_result import NormalizedResult, to_normalized_result
from app.services.paper_engine import snapshot
from app.services.market_data import ensure_market_data, MarketDataError
from app.models import Strategy, PaperDeployment, DeploymentStatus, BacktestResult
from app.config import settings


class Verdict(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ReasonCode(str, Enum):
    ENGINE_DISAGREEMENT = "ENGINE_DISAGREEMENT"
    INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
    INSUFFICIENT_PAPER_EVIDENCE = "INSUFFICIENT_PAPER_EVIDENCE"
    NEGATIVE_RETURN = "NEGATIVE_RETURN"
    WIN_RATE_BELOW_THRESHOLD = "WIN_RATE_BELOW_THRESHOLD"
    MAX_DRAWDOWN_EXCEEDED = "MAX_DRAWDOWN_EXCEEDED"
    INVALID_STRATEGY_SPEC = "INVALID_STRATEGY_SPEC"
    BACKTRADER_EXECUTION_ERROR = "BACKTRADER_EXECUTION_ERROR"
    THIRD_PARTY_EXECUTION_ERROR = "THIRD_PARTY_EXECUTION_ERROR"
    MARKET_DATA_ERROR = "MARKET_DATA_ERROR"
    NO_BACKTEST = "NO_BACKTEST"
    GUARDRAIL_REJECTION = "GUARDRAIL_REJECTION"


class AgreementStatus(str, Enum):
    AGREEMENT = "AGREEMENT"
    WARNING = "WARNING"
    MAJOR_DISAGREEMENT = "MAJOR_DISAGREEMENT"





@dataclass(frozen=True)
class RiskCheckResult:
    """Result of a single risk/performance check."""
    check_name: str
    passed: bool
    value: float
    threshold: float
    reason_code: ReasonCode | None = None


@dataclass(frozen=True)
class PaperEvidenceSummary:
    """Summary of paper trading evidence for validation."""
    status: Literal["AVAILABLE", "INSUFFICIENT", "UNAVAILABLE"]
    deployment_id: str | None = None
    completed_trades: int = 0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    current_equity: float | None = None
    open_position: bool = False
    last_bar_date: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ValidationVerdict:
    """Final validation verdict with all supporting evidence."""
    strategy_id: str
    spec_version: int
    verdict: Verdict
    reason_codes: list[ReasonCode]
    warnings: list[str]
    engine_agreement: AgreementStatus
    comparison_evidence: object  # ComparisonEvidence
    backtrader_result: object  # NormalizedResult
    backtesting_py_result: object  # NormalizedResult
    paper_evidence: PaperEvidenceSummary
    risk_checks: list[RiskCheckResult]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.utcnow())


# Configuration constants (demo validation thresholds - documented as such)
MIN_TRADES = 3
MIN_WIN_RATE_PCT = 40.0
MIN_RETURN_PCT = 0.0
MAX_DRAWDOWN_PCT = 20.0
MIN_PAPER_TRADES = 5  # Minimum paper trades for evidence to be considered "AVAILABLE"
MAX_RETURN_DELTA_PCT = 5.0  # For AGREEMENT classification
MAX_DD_DELTA_PCT = 5.0
MAX_TRADE_COUNT_DELTA = 2
MIN_TRADE_ALIGNMENT_PCT = 80.0


class StrategyValidationService:
    """
    Orchestrates the complete independent strategy validation pipeline.
    
    This is the main entry point for the validation workflow.
    """

    def __init__(self):
        pass

    def validate_strategy_spec(
        self,
        strategy_spec: StrategySpec,
        market: str = "NIFTY50",
        initial_cash: float = 100000.0,
        commission_pct: float = 0.1,
        sizer_percents: float = 95.0,
    ) -> tuple[NormalizedResult, NormalizedResult, object]:
        """
        Run dual-engine backtest and return normalized results + comparison evidence.
        
        Returns (backtrader_result, backtesting_py_result, comparison_evidence)
        """
        # Get market data
        try:
            data_path = ensure_market_data(market)
        except MarketDataError as e:
            raise ValueError(f"Market data error: {e}")

        df = pd.read_csv(data_path, parse_dates=["Date"], index_col="Date")

        # Run dual engine backtest
        bt_result, bp_result, evidence = run_dual_engine_backtest(
            df=df,
            spec=strategy_spec,
            initial_cash=initial_cash,
            commission_pct=commission_pct,
            sizer_percents=sizer_percents,
        )

        return bt_result, bp_result, evidence

    def evaluate_engine_agreement(self, evidence) -> AgreementStatus:
        """
        Classify engine agreement based on comparison evidence.
        
        Thresholds (configurable):
        - AGREEMENT: all deltas within thresholds
        - WARNING: some deltas exceed thresholds but not severely
        - MAJOR_DISAGREEMENT: significant deltas in critical metrics
        """
        # Major disagreement criteria (any one triggers)
        if evidence.return_delta_pct > MAX_RETURN_DELTA_PCT:
            return AgreementStatus.MAJOR_DISAGREEMENT
        if evidence.max_drawdown_delta_pct > MAX_DD_DELTA_PCT:
            return AgreementStatus.MAJOR_DISAGREEMENT
        if evidence.trade_count_delta > MAX_TRADE_COUNT_DELTA:
            return AgreementStatus.MAJOR_DISAGREEMENT
        if evidence.trade_alignment_pct < MIN_TRADE_ALIGNMENT_PCT and max(evidence.aligned_trades) > 0:
            return AgreementStatus.MAJOR_DISAGREEMENT

        # Warning criteria (any one triggers warning but not major)
        warning_conditions = []
        if evidence.return_delta_pct > 2.0:
            warning_conditions.append("return_delta_pct > 2%")
        if evidence.max_drawdown_delta_pct > 2.0:
            warning_conditions.append("max_drawdown_delta_pct > 2%")
        if evidence.trade_count_delta > 1:
            warning_conditions.append("trade_count_delta > 1")
        if evidence.trade_alignment_pct < 90.0:
            warning_conditions.append("trade_alignment_pct < 90%")

        if warning_conditions:
            return AgreementStatus.WARNING

        return AgreementStatus.AGREEMENT

    def collect_paper_evidence(self, strategy: Strategy) -> PaperEvidenceSummary:
        """Collect paper trading evidence for a strategy."""
        dep = None
        for dep in strategy.deployments or []:
            if dep.status == DeploymentStatus.active:
                break
        
        if dep is None:
            # Check for stopped deployments with history
            for dep in strategy.deployments or []:
                if dep.status == DeploymentStatus.stopped and dep.trades:
                    break
        
        if dep is None:
            return PaperEvidenceSummary(
                status="UNAVAILABLE",
                error="No paper deployment found"
            )

        # Get snapshot
        snap = snapshot(dep)
        trades = list(dep.trades or [])
        
        if len(trades) < MIN_PAPER_TRADES:
            return PaperEvidenceSummary(
                status="INSUFFICIENT",
                deployment_id=dep.id,
                completed_trades=len(trades),
                realized_pnl=snap.realized_pnl,
                unrealized_pnl=snap.unrealized_pnl,
                current_equity=snap.equity,
                open_position=snap.open_positions > 0,
                last_bar_date=dep.last_bar_date.isoformat() if dep.last_bar_date else None,
            )

        return PaperEvidenceSummary(
            status="AVAILABLE",
            deployment_id=dep.id,
            completed_trades=len(trades),
            realized_pnl=snap.realized_pnl,
            unrealized_pnl=snap.unrealized_pnl,
            current_equity=snap.equity,
            open_position=snap.open_positions > 0,
            last_bar_date=dep.last_bar_date.isoformat() if dep.last_bar_date else None,
        )

    def evaluate_risk_checks(
        self,
        bt_result: object,  # NormalizedResult
        bp_result: object,  # NormalizedResult
        paper_evidence: PaperEvidenceSummary,
    ) -> list[RiskCheckResult]:
        """Run all deterministic risk/performance checks."""
        checks = []

        # Use the more conservative result for checks (worst case)
        m = None
        if bt_result.metrics.return_pct < 0 or bp_result.metrics.return_pct < 0:
            # Use the worse result
            if bt_result.metrics.return_pct < bp_result.metrics.return_pct:
                m = bt_result.metrics
            else:
                m = bp_result.metrics
        else:
            m = bt_result.metrics  # default to Backtrader

        # Minimum trades check
        trades_ok = m.trade_count >= MIN_TRADES
        checks.append(RiskCheckResult(
            check_name="min_trades",
            passed=trades_ok,
            value=float(m.trade_count),
            threshold=float(MIN_TRADES),
            reason_code=ReasonCode.INSUFFICIENT_TRADES if not trades_ok else None,
        ))

        # Minimum return
        return_ok = m.return_pct >= MIN_RETURN_PCT
        checks.append(RiskCheckResult(
            check_name="min_return",
            passed=return_ok,
            value=m.return_pct,
            threshold=MIN_RETURN_PCT,
            reason_code=ReasonCode.NEGATIVE_RETURN if not return_ok else None,
        ))

        # Win rate
        win_rate_ok = m.win_rate_pct >= MIN_WIN_RATE_PCT
        checks.append(RiskCheckResult(
            check_name="min_win_rate",
            passed=win_rate_ok,
            value=m.win_rate_pct,
            threshold=MIN_WIN_RATE_PCT,
            reason_code=ReasonCode.WIN_RATE_BELOW_THRESHOLD if not win_rate_ok else None,
        ))

        # Max drawdown
        dd_ok = m.max_drawdown_pct <= MAX_DRAWDOWN_PCT
        checks.append(RiskCheckResult(
            check_name="max_drawdown",
            passed=dd_ok,
            value=m.max_drawdown_pct,
            threshold=MAX_DRAWDOWN_PCT,
            reason_code=ReasonCode.MAX_DRAWDOWN_EXCEEDED if not dd_ok else None,
        ))

        # Paper evidence check
        if paper_evidence.status == "UNAVAILABLE":
            paper_ok = False
        elif paper_evidence.status == "INSUFFICIENT":
            paper_ok = False
        else:
            paper_ok = True

        checks.append(RiskCheckResult(
            check_name="paper_evidence",
            passed=paper_ok,
            value=float(paper_evidence.completed_trades),
            threshold=float(MIN_PAPER_TRADES),
            reason_code=ReasonCode.INSUFFICIENT_PAPER_EVIDENCE if not paper_ok else None,
        ))

        return checks

    def determine_verdict(
        self,
        engine_agreement: AgreementStatus,
        risk_checks: list[RiskCheckResult],
        paper_evidence: PaperEvidenceSummary,
    ) -> tuple[Verdict, list[ReasonCode], list[str]]:
        """
        Determine final verdict based on precedence:
        1. Invalid spec / execution failure -> INVALID or INSUFFICIENT_DATA
        2. Major engine disagreement -> INSUFFICIENT_DATA
        3. Insufficient required observations -> INSUFFICIENT_DATA
        4. Deterministic risk/performance hard failure -> INVALID
        5. All required gates pass -> VALID
        """
        reason_codes = []
        warnings = []

        # Priority 1: Engine execution errors (would be caught earlier as exceptions)
        # Not applicable here as exceptions would propagate

        # Priority 2: Major engine disagreement
        if hasattr(self, '_last_agreement') and self._last_agreement == AgreementStatus.MAJOR_DISAGREEMENT:
            return Verdict.INSUFFICIENT_DATA, [ReasonCode.ENGINE_DISAGREEMENT], ["Major engine disagreement detected"]

        # Priority 3: Insufficient required observations
        failed_checks = [c for c in self._last_risk_checks if not c.passed]
        if any(c.reason_code == ReasonCode.INSUFFICIENT_TRADES for c in failed_checks):
            return Verdict.INSUFFICIENT_DATA, [ReasonCode.INSUFFICIENT_TRADES], ["Insufficient trades for validation"]
        if any(c.reason_code == ReasonCode.INSUFFICIENT_PAPER_EVIDENCE for c in failed_checks):
            return Verdict.INSUFFICIENT_DATA, [ReasonCode.INSUFFICIENT_PAPER_EVIDENCE], ["Insufficient paper evidence"]

        # Priority 4: Deterministic risk/performance hard failure
        if any(not c.passed for c in self._last_risk_checks):
            rcodes = [c.reason_code for c in failed_checks if c.reason_code]
            return Verdict.INVALID, rcodes, [f"Risk check failed: {', '.join(str(r) for r in rcodes)}"]

        # Priority 5: All gates pass
        return Verdict.VALID, [], []

    def run_validation(
        self,
        strategy_spec: StrategySpec,
        strategy_id: str,
        market: str = "NIFTY50",
        initial_cash: float = 100000.0,
        commission_pct: float = 0.1,
        sizer_percents: float = 95.0,
    ) -> ValidationVerdict:
        """
        Run the complete validation pipeline for a StrategySpec.
        
        This is the main entry point called by the API endpoint.
        """
        # Step 1: Run dual-engine backtest
        try:
            bt_result, bp_result, evidence = self.validate_strategy_spec(
                strategy_spec=strategy_spec,
                market="NIFTY50",  # Could be parameterized
                initial_cash=initial_cash,
                commission_pct=commission_pct,
                sizer_percents=sizer_percents,
            )
        except MarketDataError as e:
            return ValidationVerdict(
                strategy_id=strategy_id,
                spec_version=strategy_spec.version,
                verdict=Verdict.INSUFFICIENT_DATA,
                reason_codes=[ReasonCode.MARKET_DATA_ERROR],
                warnings=[str(e)],
                engine_agreement=AgreementStatus.MAJOR_DISAGREEMENT,
                comparison_evidence=None,
                backtrader_result=None,
                backtesting_py_result=None,
                paper_evidence=PaperEvidenceSummary(status="UNAVAILABLE", error="Market data error"),
                risk_checks=[],
            )
        except Exception as e:
            return ValidationVerdict(
                strategy_id=strategy_id,
                spec_version=strategy_spec.version,
                verdict=Verdict.INSUFFICIENT_DATA,
                reason_codes=[ReasonCode.BACKTRADER_EXECUTION_ERROR],
                warnings=[f"Execution error: {e}"],
                engine_agreement=AgreementStatus.MAJOR_DISAGREEMENT,
                comparison_evidence=None,
                backtrader_result=None,
                backtesting_py_result=None,
                paper_evidence=PaperEvidenceSummary(status="UNAVAILABLE", error=str(e)),
                risk_checks=[],
            )

        # Store evidence for later use
        self._last_comparison = evidence

        # Step 2: Evaluate engine agreement
        engine_agreement = self.evaluate_engine_agreement(evidence)
        self._last_agreement = engine_agreement

        # Step 3: Collect paper evidence (need strategy from DB)
        # For now, we'll pass strategy_id and fetch inside
        # This will be done in the API endpoint which has DB access
        paper_evidence = PaperEvidenceSummary(status="UNAVAILABLE")

        # Step 4: Evaluate risk checks
        risk_checks = self.evaluate_risk_checks(bt_result, bp_result, paper_evidence)
        self._last_risk_checks = risk_checks

        # Step 5: Determine final verdict
        verdict, reason_codes, warnings = self.determine_verdict(
            engine_agreement, risk_checks, paper_evidence
        )

        # Collect all warnings
        all_warnings = warnings + evidence.warnings

        return ValidationVerdict(
            strategy_id=strategy_id,
            spec_version=1,
            verdict=verdict,
            reason_codes=reason_codes,
            warnings=all_warnings,
            engine_agreement=engine_agreement,
            comparison_evidence=evidence,
            backtrader_result=bt_result,
            backtesting_py_result=bp_result,
            paper_evidence=paper_evidence,
            risk_checks=risk_checks,
        )


# Singleton instance
_strategy_validation_service = None

def get_strategy_validation_service() -> StrategyValidationService:
    global _strategy_validation_service
    if _strategy_validation_service is None:
        _strategy_validation_service = StrategyValidationService()
    return _strategy_validation_service
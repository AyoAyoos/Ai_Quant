from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BacktestResult,
    Strategy,
    StrategyStatus,
)
from app.schemas import BacktestRequest, BacktestResultOut, StrategyDetailOut
from app.services.backtest_service import (
    BacktestError,
    BacktestTimeout,
    run_backtest_sandboxed,
)
from app.services.market_data import MarketDataError, ensure_market_data


router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/{strategy_id}", response_model=StrategyDetailOut)
def get_strategy(strategy_id: str, db: Session = Depends(get_db)):
    """Strategy detail for the UI's code viewer — no LLM round-trip needed."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return StrategyDetailOut(
        strategy_id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        market=strategy.market,
        status=strategy.status.value,
        generated_code=strategy.generated_code,
    )


@router.post("/{strategy_id}/backtest", response_model=BacktestResultOut)
def backtest_strategy(
    strategy_id: str,
    params: BacktestRequest,
    db: Session = Depends(get_db),
):
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    if not strategy.generated_code:
        raise HTTPException(
            status_code=422,
            detail="Strategy has no generated code to backtest",
        )

    data_path = params.data_path or _default_market_data_path(strategy.market)

    try:
        metrics = run_backtest_sandboxed(
            code=strategy.generated_code,
            data_path=data_path,
            cash=params.cash,
            commission_pct=params.commission_pct,
            sizer_percents=params.sizer_percents,
        )
    except BacktestTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except BacktestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Backtest failed: {exc}",
        ) from exc

    result = BacktestResult(
        strategy_id=strategy.id,
        total_return_pct=metrics.get("total_return_pct"),
        win_rate_pct=metrics.get("win_rate_pct"),
        max_drawdown_pct=metrics.get("max_drawdown_pct"),
        num_trades=metrics.get("num_trades"),
        start_date=_parse_date(metrics.get("start_date")),
        end_date=_parse_date(metrics.get("end_date")),
        raw_metrics=metrics,
    )
    db.add(result)
    strategy.status = StrategyStatus.backtested
    db.commit()
    db.refresh(result)

    return BacktestResultOut(
        strategy_id=strategy.id,
        status="backtested",
        total_return_pct=result.total_return_pct,
        benchmark_return_pct=_benchmark_of(metrics),
        win_rate_pct=result.win_rate_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        num_trades=result.num_trades,
        sharpe=metrics.get("sharpe"),
        sortino=metrics.get("sortino"),
        cagr_pct=metrics.get("cagr_pct"),
        start_date=_date_str(metrics.get("start_date")),
        end_date=_date_str(metrics.get("end_date")),
        trades=list(metrics.get("trades") or []),
        trades_truncated=int(metrics.get("trades_truncated") or 0),
        equity_curve=list(metrics.get("equity_curve") or []),
        warnings=list(metrics.get("warnings", []) or []),
        raw_metrics=metrics,
    )


def _default_market_data_path(market: str) -> str:
    try:
        return str(ensure_market_data(market))
    except MarketDataError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not load market data for {market!r}: {exc}",
        ) from exc


def _benchmark_of(metrics: dict):
    return metrics.get("benchmark_return_pct")


def _parse_date(raw):
    if not raw:
        return None
    if hasattr(raw, "date") and hasattr(raw, "strftime"):  # datetime/date
        return raw
    import datetime as _dt

    try:
        return _dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def _date_str(raw) -> str | None:
    if not raw:
        return None
    return str(raw)

from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import canonical_uuid_or_404, strategy_not_found
from app.models import (
    BacktestResult,
    DeploymentStatus,
    PaperDeployment,
    Strategy,
    StrategyStatus,
)
from app.schemas import (
    BacktestRequest,
    BacktestResultOut,
    DeployIn,
    DeploymentOut,
    GateOut,
    RejectIn,
    StopIn,
    StrategyDetailOut,
    StrategyBuilderRequest,
    StrategyGenerateResponse,
    StrategySpecOut,
)
from app.services.backtest_service import (
    BacktestError,
    BacktestTimeout,
    run_backtest_sandboxed,
)
from app.services.deployment_gate import (
    active_deployment,
    check_approval,
    check_deploy,
)
from app.services.market_data import MarketDataError, ensure_market_data
from app.services.strategy_builder import (
    generate_structured_strategy,
    validate_indicator_parameters,
    convert_spec_to_output,
)


router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("/builder", response_model=StrategyGenerateResponse)
async def generate_strategy(payload: StrategyBuilderRequest, db: Session = Depends(get_db)):
    """
    Generate a trading strategy from structured specification.
    
    This endpoint accepts a fully structured strategy specification and uses
    the LLM to generate executable Backtrader-compatible Python code.
    
    The generated strategy is saved as a draft and can be backtested,
    approved, and deployed via the existing workflow.
    """
    # Validate indicator parameters
    param_errors = validate_indicator_parameters(payload)
    if param_errors:
        raise HTTPException(status_code=422, detail={"errors": param_errors})
    
    # Get or create a dev conversation (same as chat endpoint)
    conversation = _get_or_create_dev_conversation(db)
    
    try:
        # Generate strategy using LLM
        generated = await generate_structured_strategy(payload)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM service error: {exc}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned invalid JSON: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM response validation failed: {exc}",
        ) from exc
    
    # Extract and clean the generated code
    name = generated.get("name", "Generated Strategy")
    description = generated.get("description", "")
    code = generated.get("code", "")
    
    if not code or "GeneratedStrategy" not in code:
        raise HTTPException(
            status_code=502,
            detail="LLM failed to generate valid strategy code",
        )
    
    # Convert spec to output format
    spec_out = convert_spec_to_output(payload)
    
    # Create strategy record
    strategy = Strategy(
        conversation_id=conversation.id,
        name=name,
        description=description,
        market=payload.market,
        generated_code=code,
        strategy_spec=spec_out.model_dump(),
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    
    return StrategyGenerateResponse(
        strategy_id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        market=strategy.market,
        timeframe=payload.timeframe,
        status=strategy.status.value,
        generated_code=strategy.generated_code,
        strategy_specification=spec_out,
    )


def _get_or_create_dev_conversation(db: Session):
    """Get or create a dev conversation for strategy builder (no chat history needed)."""
    from app.models import Conversation, User
    # Try to find existing dev conversation
    conv = db.query(Conversation).filter(Conversation.title == "Strategy Builder").first()
    if conv:
        return conv
    # Create dev user if needed
    user = db.query(User).filter(User.email == "dev@local").first()
    if not user:
        user = User(email="dev@local")
        db.add(user)
        db.commit()
        db.refresh(user)
    # Create conversation
    conv = Conversation(user_id=user.id, title="Strategy Builder")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/{strategy_id}", response_model=StrategyDetailOut)
def get_strategy(strategy_id: str, db: Session = Depends(get_db)):
    """Strategy detail for the UI's code viewer — no LLM round-trip needed."""
    strategy = _get_strategy_or_404(db, strategy_id)
    return StrategyDetailOut(
        strategy_id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        market=strategy.market,
        status=strategy.status.value,
        status_note=strategy.status_note,
        generated_code=strategy.generated_code,
        strategy_spec=strategy.strategy_spec,
    )


def _get_strategy_or_404(db: Session, strategy_id: str) -> Strategy:
    """Load a strategy by id, 404-ing before the query when the id is malformed.

    Validation comes first on purpose: a non-UUID id cast to `::UUID` by
    Postgres raises a DataError inside the query, which would escape as an
    opaque 500 instead of the 404 below.
    """
    detail = strategy_not_found(strategy_id)
    canonical = canonical_uuid_or_404(strategy_id, detail)
    strategy = db.query(Strategy).filter(Strategy.id == canonical).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail=detail)
    return strategy


def _deployment_out(dep: PaperDeployment) -> DeploymentOut:
    return DeploymentOut(
        id=dep.id,
        strategy_id=dep.strategy_id,
        status=dep.status.value,
        cash=dep.cash,
        commission_pct=dep.commission_pct,
        sizer_percents=dep.sizer_percents,
        deployed_at=dep.deployed_at.isoformat() if dep.deployed_at else None,
        stopped_at=dep.stopped_at.isoformat() if dep.stopped_at else None,
        stop_reason=dep.stop_reason,
    )


@router.post("/{strategy_id}/approve", response_model=GateOut)
def approve_strategy(strategy_id: str, db: Session = Depends(get_db)):
    """backtested -> approved, when the quality gate passes."""
    strategy = _get_strategy_or_404(db, strategy_id)
    reasons = check_approval(strategy)
    if reasons:
        raise HTTPException(status_code=422, detail={"reasons": reasons})
    strategy.status = StrategyStatus.approved
    strategy.status_note = None
    db.commit()
    return GateOut(strategy_id=strategy.id, status=strategy.status.value)


@router.post("/{strategy_id}/reject", response_model=GateOut)
def reject_strategy(strategy_id: str, payload: RejectIn, db: Session = Depends(get_db)):
    """draft/backtested -> rejected, with a mandatory reason."""
    strategy = _get_strategy_or_404(db, strategy_id)
    if strategy.status == StrategyStatus.paper_trading:
        raise HTTPException(
            status_code=422,
            detail={"reasons": ["stop the active deployment before rejecting"]},
        )
    if strategy.status not in (StrategyStatus.draft, StrategyStatus.backtested):
        raise HTTPException(
            status_code=422,
            detail={"reasons": [f"cannot reject from status {strategy.status.value!r}"]},
        )
    strategy.status = StrategyStatus.rejected
    strategy.status_note = payload.reason
    db.commit()
    return GateOut(
        strategy_id=strategy.id,
        status=strategy.status.value,
        status_note=strategy.status_note,
    )


@router.post("/{strategy_id}/deploy", response_model=DeploymentOut)
def deploy_strategy(strategy_id: str, payload: DeployIn, db: Session = Depends(get_db)):
    """approved -> paper_trading, recording the deployment.

    This is the gate, not a live engine: it validates status, re-runs the
    guardrails over the current code, and refuses duplicate active
    deployments. No orders are placed anywhere.
    """
    strategy = _get_strategy_or_404(db, strategy_id)
    reasons = check_deploy(strategy)
    if reasons:
        raise HTTPException(status_code=422, detail={"reasons": reasons})
    dep = PaperDeployment(
        strategy_id=strategy.id,
        status=DeploymentStatus.active,
        cash=payload.cash,
        commission_pct=payload.commission_pct,
        sizer_percents=payload.sizer_percents,
    )
    db.add(dep)
    strategy.status = StrategyStatus.paper_trading
    strategy.status_note = None
    db.commit()
    db.refresh(dep)
    return _deployment_out(dep)


@router.post("/{strategy_id}/stop", response_model=DeploymentOut)
def stop_deployment(strategy_id: str, payload: StopIn, db: Session = Depends(get_db)):
    """Close the active deployment; the strategy returns to approved."""
    strategy = _get_strategy_or_404(db, strategy_id)
    dep = active_deployment(strategy)
    if dep is None:
        raise HTTPException(
            status_code=422,
            detail={"reasons": ["no active deployment to stop"]},
        )
    dep.status = DeploymentStatus.stopped
    dep.stopped_at = datetime.utcnow()
    dep.stop_reason = payload.reason
    strategy.status = StrategyStatus.approved
    db.commit()
    db.refresh(dep)
    return _deployment_out(dep)


@router.get("/{strategy_id}/deployments", response_model=list[DeploymentOut])
def list_deployments(strategy_id: str, db: Session = Depends(get_db)):
    """Deployment history for audit, newest first."""
    strategy = _get_strategy_or_404(db, strategy_id)
    ordered = sorted(
        strategy.deployments, key=lambda d: d.deployed_at or datetime.min, reverse=True
    )
    return [_deployment_out(d) for d in ordered]


@router.post("/{strategy_id}/backtest", response_model=BacktestResultOut)
def backtest_strategy(
    strategy_id: str,
    params: BacktestRequest,
    db: Session = Depends(get_db),
):
    strategy = _get_strategy_or_404(db, strategy_id)

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

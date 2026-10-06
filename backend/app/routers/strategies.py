from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import canonical_uuid_or_404, strategy_not_found
from app.models import (
    BacktestResult,
    DeploymentStatus,
    PaperDeployment,
    PaperOrder,
    PaperPosition,
    PaperTrade,
    Strategy,
    StrategyStatus,
)
from app.schemas import (
    BacktestRequest,
    BacktestResultOut,
    DeployIn,
    DeploymentOut,
    GateOut,
    PaperAccountSnapshot,
    PaperOrderOut,
    PaperPositionOut,
    PaperTickIn,
    PaperTickResult,
    PaperTradeOut,
    RejectIn,
    StopIn,
    StrategyDetailOut,
)
from app.services.backtest_service import (
    BacktestError,
    BacktestTimeout,
    run_backtest_sandboxed,
    run_signal_sandboxed,
)
from app.services.deployment_gate import (
    active_deployment,
    check_approval,
    check_deploy,
)
from app.services.market_data import MarketDataError, ensure_market_data
from app.services.paper_bars import PaperBarDuplicate, PaperBarError, next_bar
from app.services.paper_engine import (
    ORDER_FILLED,
    PaperExecutionError,
    open_account,
    run_tick,
    snapshot,
)


router = APIRouter(prefix="/strategies", tags=["strategies"])


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
    """approved -> paper_trading, recording the deployment and opening its account.

    This is the gate plus the virtual-account foundation: it validates status,
    re-runs the guardrails over the current code, and refuses duplicate active
    deployments, then opens a virtual balance seeded with the configured
    capital. No strategy signal is executed and no order is placed here.
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
    # Open the virtual account from the config snapshot: balance starts equal
    # to the configured cash, with no positions, trades or orders.
    open_account(dep)
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


# --------------------------------------------------------------------------- #
# Paper-trading account (Phase 1: read-only)
#
# Every route below resolves the strategy's ACTIVE deployment first and values
# its virtual account. The collections are legitimately empty straight after a
# deploy — no signal has been executed yet.
# --------------------------------------------------------------------------- #
def _active_deployment_or_422(db: Session, strategy_id: str) -> tuple[Strategy, PaperDeployment]:
    """Resolve the active paper deployment, or 422 with a reason."""
    strategy = _get_strategy_or_404(db, strategy_id)
    dep = active_deployment(strategy)
    if dep is None:
        raise HTTPException(
            status_code=422,
            detail={"reasons": ["no active paper deployment — deploy the strategy first"]},
        )
    return strategy, dep


def _position_out(p: PaperPosition) -> PaperPositionOut:
    return PaperPositionOut(
        id=p.id,
        deployment_id=p.deployment_id,
        symbol=p.symbol,
        quantity=p.quantity,
        avg_entry_price=p.avg_entry_price,
        last_price=p.last_price,
        opened_at=p.opened_at.isoformat() if p.opened_at else None,
        updated_at=p.updated_at.isoformat() if p.updated_at else None,
    )


def _trade_out(t: PaperTrade) -> PaperTradeOut:
    return PaperTradeOut(
        id=t.id,
        deployment_id=t.deployment_id,
        symbol=t.symbol,
        direction=t.direction,
        quantity=t.quantity,
        entry_price=t.entry_price,
        exit_price=t.exit_price,
        entry_date=t.entry_date.isoformat() if t.entry_date else None,
        exit_date=t.exit_date.isoformat() if t.exit_date else None,
        gross_pnl=t.gross_pnl,
        commission=t.commission,
        net_pnl=t.net_pnl,
        won=t.won,
        created_at=t.created_at.isoformat() if t.created_at else None,
    )


def _order_out(o: PaperOrder) -> PaperOrderOut:
    return PaperOrderOut(
        id=o.id,
        deployment_id=o.deployment_id,
        symbol=o.symbol,
        side=o.side,
        quantity=o.quantity,
        order_type=o.order_type,
        status=o.status,
        reason=o.reason,
        created_at=o.created_at.isoformat() if o.created_at else None,
        filled_at=o.filled_at.isoformat() if o.filled_at else None,
        fill_price=o.fill_price,
    )


@router.get("/{strategy_id}/paper-account", response_model=PaperAccountSnapshot)
def get_paper_account(strategy_id: str, db: Session = Depends(get_db)):
    """Point-in-time valuation of the active deployment's virtual account."""
    _, dep = _active_deployment_or_422(db, strategy_id)
    return snapshot(dep)


@router.get("/{strategy_id}/positions", response_model=list[PaperPositionOut])
def list_positions(strategy_id: str, db: Session = Depends(get_db)):
    """Open paper positions for the active deployment, oldest first."""
    _, dep = _active_deployment_or_422(db, strategy_id)
    ordered = sorted(
        dep.positions or [],
        key=lambda p: p.opened_at or datetime.min,
    )
    return [_position_out(p) for p in ordered]


@router.get("/{strategy_id}/trades", response_model=list[PaperTradeOut])
def list_paper_trades(strategy_id: str, db: Session = Depends(get_db)):
    """Closed paper trades for the active deployment, newest exit first."""
    _, dep = _active_deployment_or_422(db, strategy_id)
    ordered = sorted(
        dep.trades or [],
        key=lambda t: t.exit_date or datetime.min,
        reverse=True,
    )
    return [_trade_out(t) for t in ordered]


@router.get("/{strategy_id}/orders", response_model=list[PaperOrderOut])
def list_paper_orders(strategy_id: str, db: Session = Depends(get_db)):
    """Simulated order log for the active deployment, newest first."""
    _, dep = _active_deployment_or_422(db, strategy_id)
    ordered = sorted(
        dep.orders or [],
        key=lambda o: o.created_at or datetime.min,
        reverse=True,
    )
    return [_order_out(o) for o in ordered]


def _duplicate_bar_close(market: str, data_path: str, bar_date) -> float:
    """Best-effort close price of an already-processed bar, for reporting only.

    The account is already correct, so a lookup failure must never turn an
    idempotent retry into an error; it falls back to ``0.0``.
    """
    if not bar_date:
        return 0.0
    try:
        return next_bar(
            market, on=_parse_optional_date(bar_date), path=data_path
        ).close
    except (PaperBarError, ValueError):
        return 0.0


@router.post("/{strategy_id}/paper-tick", response_model=PaperTickResult)
def paper_tick(
    strategy_id: str,
    payload: PaperTickIn | None = None,
    db: Session = Depends(get_db),
):
    """Process exactly one market bar for the active paper deployment.

    One request advances the virtual account by one trading day: pick the next
    unprocessed bar, replay the strategy to learn its decision for that bar,
    simulate the resulting order, re-mark open positions, and return the updated
    snapshot. There is no loop and no scheduler — the caller drives the pace,
    which is what makes the whole thing reproducible.

    The strategy's decision comes from replaying its own generated code in the
    same sandboxed subprocess a backtest uses, so paper trading executes the
    real strategy rather than a second interpretation of it.
    """
    body = payload or PaperTickIn()
    strategy = _get_strategy_or_404(db, strategy_id)

    # Lifecycle: only a live paper_trading deployment with its account open may
    # tick. A stopped or never-deployed strategy is refused here, before any
    # market data or subprocess work happens.
    if strategy.status != StrategyStatus.paper_trading:
        raise HTTPException(
            status_code=422,
            detail={
                "reasons": [
                    f"strategy status is {strategy.status.value!r}, "
                    f"must be 'paper_trading'"
                ]
            },
        )
    dep = active_deployment(strategy)
    if dep is None:
        raise HTTPException(
            status_code=422,
            detail={"reasons": ["no active paper deployment — deploy the strategy first"]},
        )
    if not strategy.generated_code:
        raise HTTPException(
            status_code=422,
            detail={"reasons": ["strategy has no generated code to execute"]},
        )

    # 1. Resolve the data source exactly once and reuse that same file for both
    #    bar selection and the strategy replay. Reading it twice would let a
    #    cache refresh land in between, so the bar chosen here might not exist
    #    in the file the subprocess replays.
    try:
        data_path = str(ensure_market_data(strategy.market))
    except MarketDataError as exc:
        dep.last_error = f"market data unavailable: {exc}"
        db.commit()
        raise HTTPException(
            status_code=503,
            detail=f"Could not load market data for {strategy.market!r}: {exc}",
        ) from exc

    # 2. Choose the bar. A pinned date at or before the watermark is a repeat
    #    of work already done, so it short-circuits to a no-op snapshot.
    try:
        bar = next_bar(
            strategy.market,
            after=dep.last_bar_date,
            on=_parse_optional_date(body.bar_date),
            path=data_path,
        )
    except PaperBarDuplicate as exc:
        # Already consumed: a successful no-op, so a client that retries the same
        # day is always safe and sees an unchanged account. Report the real
        # price of the bar it re-requested rather than a placeholder, so the
        # snapshot is directly comparable with the original response.
        return PaperTickResult(
            strategy_id=strategy.id,
            deployment_id=dep.id,
            symbol=strategy.market.strip().upper(),
            bar_date=str(body.bar_date),
            price=_duplicate_bar_close(strategy.market, data_path, body.bar_date),
            action="HOLD",
            duplicate=True,
            reason=str(exc),
            account=snapshot(dep),
        )
    except PaperBarError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reasons": [f"no usable market bar: {exc}"]},
        ) from exc

    # 3. Ask the strategy what it wants to do on this bar.

    try:
        signal = run_signal_sandboxed(
            code=strategy.generated_code,
            data_path=data_path,
            cash=dep.cash,
            commission_pct=dep.commission_pct,
            sizer_percents=dep.sizer_percents,
            upto_date=bar.date_str,
        )
    except BacktestTimeout as exc:
        dep.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except BacktestError as exc:
        dep.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    action = str(signal.get("action") or "hold").strip().lower()

    # 4. Execute against the virtual account and 5. re-value it.
    try:
        result = run_tick(dep, bar, action, quantity=body.quantity)
    except PaperExecutionError as exc:
        # A bad bar must not corrupt the account: undo this transaction so the
        # watermark never advances past a bar we failed to process.
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={"reasons": [f"could not process bar: {exc}"]},
        ) from exc

    order = result["order"]
    if order is not None:
        db.add(order)
    db.commit()
    db.refresh(dep)

    return PaperTickResult(
        strategy_id=strategy.id,
        deployment_id=dep.id,
        symbol=bar.symbol,
        bar_date=bar.date_str,
        price=bar.close,
        action=result["action"].upper(),
        duplicate=False,
        reason=order.reason if order is not None and order.status != ORDER_FILLED else None,
        order=_order_out(order) if order is not None else None,
        fill_price=order.fill_price if order is not None else None,
        quantity=order.quantity if order is not None else None,
        marked_positions=result["marked_positions"],
        account=snapshot(dep),
    )


def _parse_optional_date(raw: str | None):
    """Parse a caller-supplied ``YYYY-MM-DD`` pin, or ``None``."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).strip())
    except ValueError:
        return raw  # let paper_bars produce the canonical parse error


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

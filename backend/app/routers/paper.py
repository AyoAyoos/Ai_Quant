"""Paper-trading hub endpoints (simulated execution only — no broker).

Aggregates deployment records across strategies so the Paper Trading page
does not depend on browser-local strategy lists.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import AuthenticatedUser, verify_user
from app.models import Conversation, DeploymentStatus, PaperDeployment, PaperPosition, PaperTrade
from app.schemas import PaperDeploymentSummaryOut
from app.services.paper_bars import PaperBarsError, load_bars
from app.services.paper_engine import account_snapshot

router = APIRouter(
    prefix="/paper",
    tags=["paper-trading"],
)


def _snapshot_numbers(db: Session, dep: PaperDeployment) -> dict:
    positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.deployment_id == dep.id)
        .all()
    )
    completed = (
        db.query(PaperTrade).filter(PaperTrade.deployment_id == dep.id).count()
    )
    last_close = None
    if dep.last_bar_date and dep.strategy is not None:
        try:
            bars = load_bars((dep.strategy.market or "NIFTY50"))
            match = next((b for b in bars if b["date"] == dep.last_bar_date), None)
            last_close = float(match["close"]) if match else None
        except PaperBarsError:
            last_close = None
    return account_snapshot(dep, positions, completed, last_close)


@router.get("/deployments", response_model=list[PaperDeploymentSummaryOut])
def list_all_deployments(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """The caller's paper deployments across their strategies, newest first,
    with snapshot numbers. Other users' deployments are never listed."""
    from app.models import Strategy

    rows = (
        db.query(PaperDeployment)
        .join(Strategy, PaperDeployment.strategy_id == Strategy.id)
        .join(Conversation, Strategy.conversation_id == Conversation.id)
        .filter(Conversation.user_id == user.id)
        .order_by(PaperDeployment.deployed_at.desc())
        .all()
    )
    summaries: list[PaperDeploymentSummaryOut] = []
    for dep in rows:
        snap = _snapshot_numbers(db, dep)
        summaries.append(
            PaperDeploymentSummaryOut(
                id=dep.id,
                strategy_id=dep.strategy_id,
                strategy_name=dep.strategy.name if dep.strategy else None,
                market=dep.strategy.market if dep.strategy else None,
                status=dep.status.value,
                starting_cash=float(dep.cash),
                cash_balance=snap["cash_balance"],
                equity=snap["equity"],
                realized_pnl=snap["realized_pnl"],
                total_pnl=snap["total_pnl"],
                return_pct=snap["return_pct"],
                open_positions=snap["open_positions"],
                completed_trades=snap["completed_trades"],
                last_bar_date=dep.last_bar_date,
                deployed_at=dep.deployed_at.isoformat() if dep.deployed_at else None,
                stopped_at=dep.stopped_at.isoformat() if dep.stopped_at else None,
                stop_reason=dep.stop_reason,
            )
        )
    # Active first, then newest first within each group.
    active = [s for s in summaries if s.status == DeploymentStatus.active.value]
    history = [s for s in summaries if s.status != DeploymentStatus.active.value]
    active.sort(key=lambda s: s.deployed_at or "", reverse=True)
    history.sort(key=lambda s: s.deployed_at or "", reverse=True)
    return active + history


@router.get("/deployments/active", response_model=list[PaperDeploymentSummaryOut])
def list_active_deployments(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Only the caller's active paper deployments, newest first."""
    return [s for s in list_all_deployments(db, user) if s.status == "active"]

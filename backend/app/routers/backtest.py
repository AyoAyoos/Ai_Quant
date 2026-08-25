from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.models import Strategy
from app.services.backtest_service import run_backtest


router = APIRouter(
    prefix="/backtest",
    tags=["backtest"],
)


class BacktestRequest(BaseModel):
    strategy_code: str
    initial_cash: float = 100000
    commission: float = 0.0003
    slippage: float = 0.0005


# =========================================================
# TEST ENDPOINT
# POST /backtest
# =========================================================

@router.post("")
async def run_strategy_backtest(
    payload: BacktestRequest,
):
    """
    Run Backtrader using strategy code supplied directly.
    """

    try:

        results = run_backtest(
            strategy_code=payload.strategy_code,
            csv_path="data/nifty50_daily.csv",
            initial_cash=payload.initial_cash,
            commission=payload.commission,
            slippage=payload.slippage,
        )

        return {
            "success": True,
            "results": results,
        }

    except Exception as e:

        print("\n========== BACKTEST API ERROR ==========")
        print(str(e))
        print("========================================\n")

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# =========================================================
# STRATEGY BACKTEST ENDPOINT
# POST /backtest/{strategy_id}
# =========================================================

@router.post("/{strategy_id}")
async def run_saved_strategy_backtest(
    strategy_id: str,
    db: Session = Depends(get_db),
):
    """
    Load a previously generated strategy from the database
    and run its generated Backtrader code.
    """

    # -----------------------------------------------------
    # 1. Find strategy
    # -----------------------------------------------------

    strategy = (
        db.query(Strategy)
        .filter(Strategy.id == strategy_id)
        .first()
    )

    if strategy is None:

        raise HTTPException(
            status_code=404,
            detail="Strategy not found.",
        )

    # -----------------------------------------------------
    # 2. Make sure generated code exists
    # -----------------------------------------------------

    if not strategy.generated_code:

        raise HTTPException(
            status_code=400,
            detail="Strategy does not contain generated code.",
        )

    # -----------------------------------------------------
    # 3. Run backtest
    # -----------------------------------------------------

    try:

        print()
        print("========== SAVED STRATEGY BACKTEST ==========")
        print("Strategy ID:", strategy.id)
        print("Strategy Name:", strategy.name)

        results = run_backtest(
            strategy_code=strategy.generated_code,
            csv_path="data/nifty50_daily.csv",
            initial_cash=100000,
            commission=0.0003,
            slippage=0.0005,
        )

        print("========== BACKTEST COMPLETE ==========")
        print()

        return {
            "success": True,
            "strategy_id": str(strategy.id),
            "strategy_name": strategy.name,
            "results": results,
        }

    except Exception as e:

        print()
        print("========== SAVED STRATEGY BACKTEST ERROR ==========")
        print(str(e))
        print("====================================================")
        print()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
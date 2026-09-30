from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Strategy
from app.services.strategy_validator import validate_strategy_code


router = APIRouter(
    prefix="/strategies",
    tags=["strategies"],
)


@router.post("/{strategy_id}/validate")
def validate_saved_strategy(
    strategy_id: str,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Find strategy
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # 2. Validate generated code
    # ---------------------------------------------------------
    result = validate_strategy_code(
        strategy.generated_code
    )

    # ---------------------------------------------------------
    # 3. Return validation result
    # ---------------------------------------------------------
    
    return {
        "strategy_id": "....",
        "strategy_name": "SMA Crossover",
        "valid": true,
        "errors": [],
        "warnings": []
    }
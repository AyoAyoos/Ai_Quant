from pydantic import BaseModel, Field
from typing import Literal


class IndicatorSpec(BaseModel):
    type: Literal[
        "SMA",
        "EMA",
        "RSI",
        "VolumeSMA",
        "MACD",
        "BollingerBands"
    ]

    period: int | None = Field(default=None, ge=1)


class RiskManagementSpec(BaseModel):
    risk_per_trade: float = Field(ge=0, le=0.01)
    max_positions: int = Field(default=1, ge=1)
    stop_loss_pct: float | None = Field(default=None, ge=0, le=1)
    take_profit_pct: float | None = Field(default=None, ge=0, le=10)


class StrategySpec(BaseModel):
    name: str
    description: str

    market: Literal["NIFTY50"]
    timeframe: Literal["1D"]

    indicators: list[IndicatorSpec]

    entry_conditions: list[str]
    exit_conditions: list[str]

    risk_management: RiskManagementSpec
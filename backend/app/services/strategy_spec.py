"""Engine-neutral strategy specification.

This module defines a small, deterministic representation of a trading
strategy.  It contains no Backtrader or Backtesting.py-specific objects.

Both execution engines will later consume the same validated specification.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SPEC_VERSION = 1

IndicatorType = Literal["sma", "ema", "rsi"]

ConditionOperator = Literal[
    "greater_than",
    "less_than",
    "crosses_above",
    "crosses_below",
]


class IndicatorSpec(BaseModel):
    """Definition of one supported technical indicator."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    type: IndicatorType
    period: int = Field(ge=2, le=500)


class ConditionSpec(BaseModel):
    """One deterministic entry or exit condition."""

    model_config = ConfigDict(extra="forbid")

    left: str = Field(min_length=1, max_length=50)
    operator: ConditionOperator
    right_indicator: str | None = Field(default=None, max_length=50)
    right_value: float | None = None

    @model_validator(mode="after")
    def validate_right_operand(self):
        has_indicator = self.right_indicator is not None
        has_value = self.right_value is not None

        if has_indicator == has_value:
            raise ValueError(
                "condition must specify exactly one of "
                "right_indicator or right_value"
            )

        return self


class StrategySpec(BaseModel):
    """Versioned engine-neutral description of a long-only strategy."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = SPEC_VERSION
    name: str = Field(min_length=1, max_length=100)

    indicators: list[IndicatorSpec] = Field(min_length=1, max_length=10)

    entry: ConditionSpec
    exit: ConditionSpec

    direction: Literal["long"] = "long"

    @model_validator(mode="after")
    def validate_references(self):
        indicator_names = [indicator.name for indicator in self.indicators]

        if len(indicator_names) != len(set(indicator_names)):
            raise ValueError("indicator names must be unique")

        known = set(indicator_names)
        known.add("close")

        for label, condition in (
            ("entry", self.entry),
            ("exit", self.exit),
        ):
            if condition.left not in known:
                raise ValueError(
                    f"{label} condition references unknown left operand: "
                    f"{condition.left}"
                )

            if (
                condition.right_indicator is not None
                and condition.right_indicator not in known
            ):
                raise ValueError(
                    f"{label} condition references unknown right indicator: "
                    f"{condition.right_indicator}"
                )

        return self


def parse_strategy_spec(data: dict) -> StrategySpec:
    """Validate and parse a raw dictionary into StrategySpec."""

    return StrategySpec.model_validate(data)


def strategy_spec_to_dict(spec: StrategySpec) -> dict:
    """Return a JSON-serializable representation."""

    return spec.model_dump(mode="json")
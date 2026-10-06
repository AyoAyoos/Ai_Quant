"""Tests for StrategySpec validation and serialization."""

import pytest

from app.services.strategy_spec import (
    StrategySpec,
    IndicatorSpec,
    ConditionSpec,
    parse_strategy_spec,
    strategy_spec_to_dict,
    SPEC_VERSION,
)


class TestValidSpecs:
    """Valid strategy specifications should parse without error."""

    def test_valid_rsi_mean_reversion(self):
        data = {
            "version": 1,
            "name": "RSI Mean Reversion",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert isinstance(spec, StrategySpec)
        assert spec.name == "RSI Mean Reversion"
        assert len(spec.indicators) == 1
        assert spec.indicators[0].name == "rsi"
        assert spec.indicators[0].type == "rsi"
        assert spec.indicators[0].period == 14
        assert spec.entry.left == "rsi"
        assert spec.entry.operator == "less_than"
        assert spec.entry.right_value == 30
        assert spec.exit.right_value == 70
        assert spec.direction == "long"

    def test_valid_sma_crossover(self):
        data = {
            "version": 1,
            "name": "SMA Crossover",
            "indicators": [
                {"name": "fast", "type": "sma", "period": 10},
                {"name": "slow", "type": "sma", "period": 50},
            ],
            "entry": {
                "left": "fast",
                "operator": "crosses_above",
                "right_indicator": "slow",
            },
            "exit": {
                "left": "fast",
                "operator": "crosses_below",
                "right_indicator": "slow",
            },
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.name == "SMA Crossover"
        assert len(spec.indicators) == 2
        assert spec.entry.operator == "crosses_above"
        assert spec.entry.right_indicator == "slow"
        assert spec.exit.operator == "crosses_below"

    def test_valid_ema_trend(self):
        data = {
            "version": 1,
            "name": "EMA Trend",
            "indicators": [{"name": "ema", "type": "ema", "period": 200}],
            "entry": {"left": "close", "operator": "greater_than", "right_indicator": "ema"},
            "exit": {"left": "close", "operator": "less_than", "right_indicator": "ema"},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.name == "EMA Trend"
        assert spec.entry.left == "close"
        assert spec.entry.right_indicator == "ema"
        assert spec.exit.left == "close"

    def test_indicator_to_indicator_comparison(self):
        data = {
            "version": 1,
            "name": "RSI vs SMA",
            "indicators": [
                {"name": "rsi", "type": "rsi", "period": 14},
                {"name": "sma", "type": "sma", "period": 20},
            ],
            "entry": {
                "left": "rsi",
                "operator": "greater_than",
                "right_indicator": "sma",
            },
            "exit": {
                "left": "rsi",
                "operator": "less_than",
                "right_indicator": "sma",
            },
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.entry.right_indicator == "sma"
        assert spec.exit.right_indicator == "sma"

    def test_crosses_above(self):
        data = {
            "version": 1,
            "name": "Crosses Above",
            "indicators": [
                {"name": "fast", "type": "sma", "period": 5},
                {"name": "slow", "type": "sma", "period": 20},
            ],
            "entry": {"left": "fast", "operator": "crosses_above", "right_indicator": "slow"},
            "exit": {"left": "fast", "operator": "crosses_below", "right_indicator": "slow"},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.entry.operator == "crosses_above"
        assert spec.exit.operator == "crosses_below"

    def test_crosses_below(self):
        data = {
            "version": 1,
            "name": "Crosses Below",
            "indicators": [
                {"name": "fast", "type": "ema", "period": 5},
                {"name": "slow", "type": "ema", "period": 20},
            ],
            "entry": {"left": "fast", "operator": "crosses_below", "right_indicator": "slow"},
            "exit": {"left": "fast", "operator": "crosses_above", "right_indicator": "slow"},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.entry.operator == "crosses_below"
        assert spec.exit.operator == "crosses_above"


class TestInvalidSpecs:
    """Invalid specifications should raise validation errors."""

    def test_unsupported_version(self):
        data = {
            "version": 2,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="version"):
            parse_strategy_spec(data)

    def test_unsupported_indicator(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "macd", "type": "macd", "period": 12}],
            "entry": {"left": "macd", "operator": "greater_than", "right_value": 0},
            "exit": {"left": "macd", "operator": "less_than", "right_value": 0},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="type"):
            parse_strategy_spec(data)

    def test_unsupported_operator(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "equals", "right_value": 50},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="operator"):
            parse_strategy_spec(data)

    def test_period_too_low(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 1}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="period"):
            parse_strategy_spec(data)

    def test_period_too_high(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 501}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="period"):
            parse_strategy_spec(data)

    def test_duplicate_indicator_names(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [
                {"name": "rsi", "type": "rsi", "period": 14},
                {"name": "rsi", "type": "rsi", "period": 28},
            ],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="unique"):
            parse_strategy_spec(data)

    def test_unknown_left_operand(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "unknown", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="unknown left operand"):
            parse_strategy_spec(data)

    def test_unknown_right_indicator(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "greater_than", "right_indicator": "unknown"},
            "exit": {"left": "rsi", "operator": "less_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="unknown right indicator"):
            parse_strategy_spec(data)

    def test_both_right_operands_supplied(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "greater_than", "right_indicator": "sma", "right_value": 50},
            "exit": {"left": "rsi", "operator": "less_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="exactly one"):
            parse_strategy_spec(data)

    def test_neither_right_operand_supplied(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "greater_than"},
            "exit": {"left": "rsi", "operator": "less_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="exactly one"):
            parse_strategy_spec(data)

    def test_extra_strategy_spec_field(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
            "extra_field": "not allowed",
        }
        with pytest.raises(ValueError, match="extra"):
            parse_strategy_spec(data)

    def test_extra_indicator_spec_field(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14, "extra": "not allowed"}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="extra"):
            parse_strategy_spec(data)

    def test_extra_condition_spec_field(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30, "extra": "not allowed"},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="extra"):
            parse_strategy_spec(data)

    def test_non_long_direction(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "short",
        }
        with pytest.raises(ValueError, match="direction"):
            parse_strategy_spec(data)

    def test_invalid_empty_name(self):
        data = {
            "version": 1,
            "name": "",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        with pytest.raises(ValueError, match="name"):
            parse_strategy_spec(data)

    def test_malformed_specification_missing_fields(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
        }
        with pytest.raises(ValueError):
            parse_strategy_spec(data)


class TestSerialization:
    """Serialization and round-trip tests."""

    def test_serialization(self):
        data = {
            "version": 1,
            "name": "RSI Mean Reversion",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 70},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        serialized = strategy_spec_to_dict(spec)
        assert serialized["version"] == 1
        assert serialized["name"] == "RSI Mean Reversion"
        assert len(serialized["indicators"]) == 1
        assert serialized["entry"]["left"] == "rsi"
        assert serialized["entry"]["operator"] == "less_than"
        assert serialized["entry"]["right_value"] == 30
        assert serialized["exit"]["right_value"] == 70
        assert serialized["direction"] == "long"

    def test_parse_serialize_round_trip(self):
        data = {
            "version": 1,
            "name": "SMA Crossover",
            "indicators": [
                {"name": "fast", "type": "sma", "period": 10},
                {"name": "slow", "type": "sma", "period": 50},
            ],
            "entry": {"left": "fast", "operator": "crosses_above", "right_indicator": "slow"},
            "exit": {"left": "fast", "operator": "crosses_below", "right_indicator": "slow"},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        serialized = strategy_spec_to_dict(spec)
        spec2 = parse_strategy_spec(serialized)
        assert spec2.name == spec.name
        assert spec2.version == spec.version
        assert len(spec2.indicators) == len(spec.indicators)
        assert spec2.entry.operator == spec.entry.operator
        assert spec2.exit.operator == spec.exit.operator
        assert spec2.direction == spec.direction


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_period_boundary_min(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "sma", "type": "sma", "period": 2}],
            "entry": {"left": "close", "operator": "greater_than", "right_indicator": "sma"},
            "exit": {"left": "close", "operator": "less_than", "right_indicator": "sma"},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.indicators[0].period == 2

    def test_period_boundary_max(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "sma", "type": "sma", "period": 500}],
            "entry": {"left": "close", "operator": "greater_than", "right_indicator": "sma"},
            "exit": {"left": "close", "operator": "less_than", "right_indicator": "sma"},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.indicators[0].period == 500

    def test_max_indicators(self):
        indicators = [{"name": f"ind{i}", "type": "sma", "period": 10 + i} for i in range(10)]
        data = {
            "version": 1,
            "name": "Test",
            "indicators": indicators,
            "entry": {"left": "ind0", "operator": "greater_than", "right_indicator": "ind1"},
            "exit": {"left": "ind0", "operator": "less_than", "right_indicator": "ind1"},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert len(spec.indicators) == 10

    def test_right_value_float(self):
        data = {
            "version": 1,
            "name": "Test",
            "indicators": [{"name": "rsi", "type": "rsi", "period": 14}],
            "entry": {"left": "rsi", "operator": "less_than", "right_value": 30.5},
            "exit": {"left": "rsi", "operator": "greater_than", "right_value": 69.5},
            "direction": "long",
        }
        spec = parse_strategy_spec(data)
        assert spec.entry.right_value == 30.5
        assert spec.exit.right_value == 69.5
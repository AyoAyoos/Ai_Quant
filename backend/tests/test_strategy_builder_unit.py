"""Unit tests for the strategy_builder service (no LLM required)."""
import sys
import os

# Ensure the backend directory is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.services.strategy_builder import (
    build_strategy_prompt,
    validate_indicator_parameters,
    convert_spec_to_output,
    validate_generated_code,
)
from app.schemas import (
    StrategyBuilderRequest,
    IndicatorSpec,
    RiskManagementSpec,
)


class TestValidateIndicatorParameters:
    def test_valid_ema_parameters(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="EMA", parameters={"fast": 20, "slow": 50}),
            ],
            entry_conditions=["EMA crossover"],
            exit_conditions=["EMA crossunder"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert errors == []

    def test_valid_rsi_parameters(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="RSI", parameters={"period": 14, "oversold": 30, "overbought": 70}),
            ],
            entry_conditions=["RSI oversold"],
            exit_conditions=["RSI overbought"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert errors == []

    def test_valid_macd_parameters(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="MACD", parameters={"fast": 12, "slow": 26, "signal": 9}),
            ],
            entry_conditions=["MACD crossover"],
            exit_conditions=["MACD crossunder"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert errors == []

    def test_valid_bollinger_bands_parameters(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="Bollinger Bands", parameters={"period": 20, "devfactor": 2.0}),
            ],
            entry_conditions=["Price below lower band"],
            exit_conditions=["Price above upper band"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert errors == []

    def test_valid_volume_no_parameters(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="Volume", parameters={}),
            ],
            entry_conditions=["Volume spike"],
            exit_conditions=["Volume drop"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert errors == []

    def test_missing_required_parameter(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="EMA", parameters={"fast": 20}),  # missing slow
            ],
            entry_conditions=["EMA crossover"],
            exit_conditions=["EMA crossunder"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert any("missing required parameter: slow" in e for e in errors)

    def test_invalid_parameter_type(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="EMA", parameters={"fast": "twenty", "slow": 50}),  # string instead of int
            ],
            entry_conditions=["EMA crossover"],
            exit_conditions=["EMA crossunder"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert any("must be int" in e for e in errors)

    def test_parameter_out_of_range(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="EMA", parameters={"fast": 0, "slow": 50}),  # fast must be >= 1
            ],
            entry_conditions=["EMA crossover"],
            exit_conditions=["EMA crossunder"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert any("must be between 1 and 200" in e for e in errors)

    def test_unexpected_parameter(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="EMA", parameters={"fast": 20, "slow": 50, "extra": 10}),
            ],
            entry_conditions=["EMA crossover"],
            exit_conditions=["EMA crossunder"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        assert any("unexpected parameter: extra" in e for e in errors)

    def test_rsi_oversold_overbought_validation(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="RSI", parameters={"period": 14, "oversold": 50, "overbought": 30}),  # oversold > overbought
            ],
            entry_conditions=["RSI oversold"],
            exit_conditions=["RSI overbought"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
            ),
        )
        errors = validate_indicator_parameters(spec)
        # oversold must be <= 50, overbought must be >= 50
        assert any("oversold" in e or "overbought" in e for e in errors)


class TestBuildStrategyPrompt:
    def test_prompt_contains_all_fields(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="EMA", parameters={"fast": 20, "slow": 50}),
                IndicatorSpec(name="RSI", parameters={"period": 14, "oversold": 30, "overbought": 70}),
            ],
            entry_conditions=["EMA 20 crosses above EMA 50", "RSI is below 30"],
            exit_conditions=["EMA 20 crosses below EMA 50"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
                trailing_stop_percent=0.5,
                max_trades_per_day=3,
            ),
        )
        prompt = build_strategy_prompt(spec)
        
        assert "NIFTY50" in prompt
        assert "intraday" in prompt
        assert "15m" in prompt
        assert "EMA" in prompt
        assert "RSI" in prompt
        assert "fast=20" in prompt
        assert "slow=50" in prompt
        assert "period=14" in prompt
        assert "oversold=30" in prompt
        assert "overbought=70" in prompt
        assert "EMA 20 crosses above EMA 50" in prompt
        assert "RSI is below 30" in prompt
        assert "EMA 20 crosses below EMA 50" in prompt
        assert "Stop Loss: 1.0%" in prompt
        assert "Take Profit: 2.0%" in prompt
        assert "Trailing Stop: 0.5%" in prompt
        assert "Max Trades Per Day: 3" in prompt


class TestConvertSpecToOutput:
    def test_conversion_preserves_all_fields(self):
        spec = StrategyBuilderRequest(
            market="NIFTY50",
            trading_style="intraday",
            timeframe="15m",
            indicators=[
                IndicatorSpec(name="EMA", parameters={"fast": 20, "slow": 50}),
            ],
            entry_conditions=["EMA crossover"],
            exit_conditions=["EMA crossunder"],
            risk_management=RiskManagementSpec(
                stop_loss_percent=1,
                take_profit_percent=2,
                trailing_stop_percent=0.5,
                max_trades_per_day=3,
            ),
        )
        output = convert_spec_to_output(spec)
        
        assert output.market == "NIFTY50"
        assert output.trading_style == "intraday"
        assert output.timeframe == "15m"
        assert len(output.indicators) == 1
        assert output.indicators[0].name == "EMA"
        assert output.indicators[0].parameters == {"fast": 20, "slow": 50}
        assert output.entry_conditions == ["EMA crossover"]
        assert output.exit_conditions == ["EMA crossunder"]
        assert output.risk_management.stop_loss_percent == 1
        assert output.risk_management.take_profit_percent == 2
        assert output.risk_management.trailing_stop_percent == 0.5
        assert output.risk_management.max_trades_per_day == 3


class TestValidateGeneratedCode:
    def test_valid_complete_strategy(self):
        code = '''
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    params = (("ema_fast_period", 20),)

    def __init__(self):
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast_period)

    def next(self):
        if not self.position and self.ema_fast[0] > self.ema_fast[-1]:
            self.buy()
        elif self.position:
            self.sell()
'''
        result = validate_generated_code(code)
        assert result["errors"] == []
        # May have warnings but no errors

    def test_missing_import(self):
        code = '''
class GeneratedStrategy(bt.Strategy):
    def next(self):
        self.buy()
'''
        result = validate_generated_code(code)
        assert any("import backtrader" in e for e in result["errors"])

    def test_missing_class(self):
        code = '''
import backtrader as bt

def next(self):
    self.buy()
'''
        result = validate_generated_code(code)
        assert any("GeneratedStrategy" in e for e in result["errors"])

    def test_missing_next_method(self):
        code = '''
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    def __init__(self):
        pass
'''
        result = validate_generated_code(code)
        assert any("next" in e for e in result["errors"])

    def test_no_buy_call(self):
        code = '''
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    def next(self):
        if self.position:
            self.sell()
'''
        result = validate_generated_code(code)
        assert any("buy" in w for w in result["warnings"])

    def test_no_sell_call(self):
        code = '''
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    def next(self):
        if not self.position:
            self.buy()
'''
        result = validate_generated_code(code)
        assert any("sell" in w for w in result["warnings"])

    def test_no_indicators(self):
        code = '''
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    def next(self):
        if not self.position:
            self.buy()
        else:
            self.sell()
'''
        result = validate_generated_code(code)
        assert any("indicators" in w for w in result["warnings"])

    def test_no_position_check(self):
        code = '''
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    def next(self):
        self.buy()
        self.sell()
'''
        result = validate_generated_code(code)
        assert any("position" in w for w in result["warnings"])

    def test_risk_params_without_entry_price(self):
        code = '''
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    params = (("stop_loss_pct", 1.0),)

    def next(self):
        if not self.position:
            self.buy()
        elif self.position:
            self.sell()
'''
        result = validate_generated_code(code)
        # Should warn about missing entry_price tracking when stop_loss_pct is used
        assert any("entry_price" in w for w in result["warnings"])
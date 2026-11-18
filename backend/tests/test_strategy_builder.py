import asyncio
import json

import pytest

from app.schemas import IndicatorSpec, RiskManagementSpec, StrategyBuilderRequest
from app.services import strategy_builder


def _spec(indicators, entry=None, exit=None, style="intraday", timeframe="15m"):
    return StrategyBuilderRequest(
        market="NIFTY50",
        trading_style=style,
        timeframe=timeframe,
        indicators=indicators,
        entry_conditions=entry or ["Entry condition"],
        exit_conditions=exit or ["Exit on opposite signal"],
        risk_management=RiskManagementSpec(stop_loss_percent=1, take_profit_percent=2),
    )


def _mock_llm(monkeypatch, code=None):
    code = code or (
        "import backtrader as bt\n\n"
        "class GeneratedStrategy(bt.Strategy):\n"
        "    def __init__(self):\n"
        "        self.order = None\n"
        "    def notify_order(self, order):\n"
        "        self.order = None\n"
        "    def next(self):\n"
        "        if not self.position:\n"
        "            self.buy()\n"
        "        else:\n"
        "            self.close()\n"
    )
    payload = {"name": "Test", "description": "Desc", "code": code}

    class _Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(strategy_builder, "httpx", type("X", (), {"AsyncClient": _Client}))
    monkeypatch.setattr(strategy_builder.settings, "groq_api_key", "test-key", raising=False)


def test_validate_bollinger_bands_alone_accepts_aliases():
    spec = _spec([IndicatorSpec(name="Bollinger Bands", parameters={"period": 20, "deviation_factor": 2.0})])
    assert strategy_builder.validate_indicator_parameters(spec) == []


def test_validate_volume_alone_optional_params():
    spec = _spec([IndicatorSpec(name="Volume", parameters={})])
    assert strategy_builder.validate_indicator_parameters(spec) == []


def test_validate_ema_bollinger_combo():
    spec = _spec([
        IndicatorSpec(name="EMA", parameters={"fast": 20, "slow": 50}),
        IndicatorSpec(name="Bollinger Bands", parameters={"period": 20, "devfactor": 2.0}),
    ])
    assert strategy_builder.validate_indicator_parameters(spec) == []


def test_validate_ema_sma_bollinger_combo_and_sma_fast_slow():
    spec = _spec([
        IndicatorSpec(name="EMA", parameters={"fast": 20, "slow": 50}),
        IndicatorSpec(name="SMA", parameters={"fast": 10, "slow": 30}),
        IndicatorSpec(name="Bollinger Bands", parameters={"period": 20, "std_dev": 2.0}),
    ])
    assert strategy_builder.validate_indicator_parameters(spec) == []


def test_validate_rsi_macd_volume_combo():
    spec = _spec([
        IndicatorSpec(name="RSI", parameters={"period": 14, "oversold": 30, "overbought": 70}),
        IndicatorSpec(name="MACD", parameters={"fast": 12, "slow": 26, "signal": 9}),
        IndicatorSpec(name="Volume", parameters={"period": 20, "multiplier": 1.5}),
    ])
    assert strategy_builder.validate_indicator_parameters(spec) == []


@pytest.mark.parametrize("name,params", [
    ("EMA", {"fast": 20, "slow": 50}),
    ("SMA", {"period": 20}),
    ("RSI", {"period": 14, "oversold": 30, "overbought": 70}),
    ("MACD", {"fast": 12, "slow": 26, "signal": 9}),
])
def test_existing_single_indicators_still_validate(name, params):
    spec = _spec([IndicatorSpec(name=name, parameters=params)])
    assert strategy_builder.validate_indicator_parameters(spec) == []


def test_prompt_includes_bollinger_and_multi_indicator_params():
    spec = _spec([
        IndicatorSpec(name="EMA", parameters={"fast": 20, "slow": 50}),
        IndicatorSpec(name="Bollinger Bands", parameters={"period": 20, "devfactor": 2.0}),
    ], entry=["Close Price crosses below Lower Band"])
    prompt = strategy_builder.build_strategy_prompt(spec)
    assert "Bollinger Bands" in prompt
    assert "devfactor=2.0" in prompt or "devfactor=2" in prompt
    assert "EMA" in prompt and "fast=20" in prompt


def test_generate_structured_strategy_returns_code(monkeypatch):
    bb_code = (
        "import backtrader as bt\n\n"
        "class GeneratedStrategy(bt.Strategy):\n"
        "    def __init__(self):\n"
        "        self.bb = bt.indicators.BollingerBands(self.data.close, period=20, devfactor=2.0)\n"
        "        self.order = None\n"
        "    def notify_order(self, order):\n"
        "        self.order = None\n"
        "    def next(self):\n"
        "        if not self.position and self.data.close[0] < self.bb.lines.bot[0]:\n"
        "            self.buy()\n"
        "        elif self.position and self.data.close[0] > self.bb.lines.top[0]:\n"
        "            self.close()\n"
    )
    _mock_llm(monkeypatch, bb_code)
    spec = _spec([IndicatorSpec(name="Bollinger Bands", parameters={"period": 20, "devfactor": 2.0})])
    out = asyncio.run(strategy_builder.generate_structured_strategy(spec))
    assert out["code"]
    assert "class GeneratedStrategy" in out["code"]
    assert "BollingerBands" in out["code"]

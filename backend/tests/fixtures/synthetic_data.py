"""
Deterministic synthetic OHLCV fixtures for dual-engine testing.

All fixtures are pure Python - no network, no yfinance, no external data.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _make_index(start: str, periods: int, freq: str = "D") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=periods, freq=freq, tz=None)


def uptrend_data(periods: int = 100, start_price: float = 100.0, drift: float = 0.5) -> pd.DataFrame:
    """Steady uptrend with small noise."""
    idx = _make_index("2023-01-01", periods)
    np.random.seed(42)
    returns = np.random.normal(drift / 100, 0.5 / 100, periods)
    prices = start_price * np.exp(np.cumsum(returns))
    opens = prices * (1 + np.random.normal(0, 0.0005, periods))
    highs = np.maximum(opens, prices) * (1 + np.abs(np.random.normal(0, 0.003, periods)))
    lows = np.minimum(opens, prices) * (1 - np.abs(np.random.normal(0, 0.003, periods)))
    volumes = np.random.randint(100000, 1000000, periods)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def downtrend_data(periods: int = 100, start_price: float = 100.0, drift: float = -0.5) -> pd.DataFrame:
    """Steady downtrend with small noise."""
    idx = _make_index("2023-01-01", periods)
    np.random.seed(43)
    returns = np.random.normal(drift / 100, 0.5 / 100, periods)
    prices = start_price * np.exp(np.cumsum(returns))
    opens = prices * (1 + np.random.normal(0, 0.0005, periods))
    highs = np.maximum(opens, prices) * (1 + np.abs(np.random.normal(0, 0.003, periods)))
    lows = np.minimum(opens, prices) * (1 - np.abs(np.random.normal(0, 0.003, periods)))
    volumes = np.random.randint(100000, 1000000, periods)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def sideways_data(periods: int = 100, center: float = 100.0, amplitude: float = 2.0) -> pd.DataFrame:
    """Sideways oscillating market."""
    idx = _make_index("2023-01-01", periods)
    t = np.arange(periods)
    prices = center + amplitude * np.sin(2 * np.pi * t / 20) + np.random.normal(0, 0.3, periods)
    opens = prices + np.random.normal(0, 0.1, periods)
    highs = np.maximum(opens, prices) + np.abs(np.random.normal(0, 0.3, periods))
    lows = np.minimum(opens, prices) - np.abs(np.random.normal(0, 0.3, periods))
    volumes = np.random.randint(100000, 1000000, periods)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def rsi_oversold_bounce_data() -> pd.DataFrame:
    """Data designed to trigger RSI < 30 then bounce."""
    idx = _make_index("2023-01-01", 60)
    # Create a sharp drop then recovery
    prices = np.concatenate([
        np.linspace(100, 85, 20),  # Drop
        np.linspace(85, 105, 20),  # Recovery
        np.linspace(105, 105, 20),  # Flat
    ])
    np.random.seed(44)
    prices += np.random.normal(0, 0.2, 60)
    opens = prices + np.random.normal(0, 0.05, 60)
    highs = np.maximum(opens, prices) + np.abs(np.random.normal(0, 0.2, 60))
    lows = np.minimum(opens, prices) - np.abs(np.random.normal(0, 0.2, 60))
    volumes = np.random.randint(500000, 2000000, 60)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def sma_crossover_data() -> pd.DataFrame:
    """Data with clear SMA(10) / SMA(30) crossovers."""
    idx = _make_index("2023-01-01", 100)
    np.random.seed(45)
    # Create trend changes that will generate crossovers
    trend = np.concatenate([
        np.linspace(0, 1, 30),    # Up
        np.linspace(1, -1, 40),   # Down
        np.linspace(-1, 0, 30),   # Up
    ])
    prices = 100 + 15 * trend + np.random.normal(0, 0.5, 100)
    opens = prices + np.random.normal(0, 0.1, 100)
    highs = np.maximum(opens, prices) + np.abs(np.random.normal(0, 0.3, 100))
    lows = np.minimum(opens, prices) - np.abs(np.random.normal(0, 0.3, 100))
    volumes = np.random.randint(500000, 2000000, 100)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def ema_trend_data() -> pd.DataFrame:
    """Data for EMA trend following test."""
    idx = _make_index("2023-01-01", 80)
    np.random.seed(46)
    prices = 100 + np.cumsum(np.random.normal(0.2, 0.8, 80))
    opens = prices + np.random.normal(0, 0.1, 80)
    highs = np.maximum(opens, prices) + np.abs(np.random.normal(0, 0.4, 80))
    lows = np.minimum(opens, prices) - np.abs(np.random.normal(0, 0.4, 80))
    volumes = np.random.randint(500000, 2000000, 80)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def no_trade_data() -> pd.DataFrame:
    """Data where no signals should fire (RSI stays in middle range)."""
    idx = _make_index("2023-01-01", 50)
    np.random.seed(47)
    prices = 100 + np.random.normal(0, 0.5, 50).cumsum()
    prices = np.clip(prices, 95, 105)  # Keep RSI in middle
    opens = prices + np.random.normal(0, 0.1, 50)
    highs = np.maximum(opens, prices) + np.abs(np.random.normal(0, 0.2, 50))
    lows = np.minimum(opens, prices) - np.abs(np.random.normal(0, 0.2, 50))
    volumes = np.random.randint(500000, 2000000, 50)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def single_trade_data() -> pd.DataFrame:
    """Data that produces exactly one complete round trip."""
    idx = _make_index("2023-01-01", 40)
    np.random.seed(48)
    # One dip and recovery
    prices = np.concatenate([
        np.linspace(100, 95, 10),
        np.linspace(95, 110, 20),
        np.linspace(110, 110, 10),
    ])
    prices += np.random.normal(0, 0.1, 40)
    opens = prices + np.random.normal(0, 0.05, 40)
    highs = np.maximum(opens, prices) + np.abs(np.random.normal(0, 0.15, 40))
    lows = np.minimum(opens, prices) - np.abs(np.random.normal(0, 0.15, 40))
    volumes = np.random.randint(500000, 2000000, 40)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def multi_trade_data() -> pd.DataFrame:
    """Data that produces multiple trades."""
    idx = _make_index("2023-01-01", 120)
    np.random.seed(49)
    # Multiple oscillations
    t = np.arange(120)
    prices = 100 + 8 * np.sin(2 * np.pi * t / 30) + np.random.normal(0, 0.3, 120)
    opens = prices + np.random.normal(0, 0.1, 120)
    highs = np.maximum(opens, prices) + np.abs(np.random.normal(0, 0.3, 120))
    lows = np.minimum(opens, prices) - np.abs(np.random.normal(0, 0.3, 120))
    volumes = np.random.randint(500000, 2000000, 120)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


def warmup_data() -> pd.DataFrame:
    """Data with exactly 14 bars (minimum for RSI(14) warmup)."""
    return rsi_oversold_bounce_data().iloc[:20]  # Just enough for warmup


def insufficient_bars_data() -> pd.DataFrame:
    """Data with fewer bars than minimum indicator period."""
    idx = _make_index("2023-01-01", 5)
    prices = np.linspace(100, 105, 5)
    opens = prices
    highs = prices + 0.5
    lows = prices - 0.5
    volumes = np.full(5, 1000000)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": volumes}, index=idx)


# Fixtures dictionary for easy access
FIXTURES = {
    "uptrend": uptrend_data,
    "downtrend": downtrend_data,
    "sideways": sideways_data,
    "rsi_oversold_bounce": rsi_oversold_bounce_data,
    "sma_crossover": sma_crossover_data,
    "ema_trend": ema_trend_data,
    "no_trade": no_trade_data,
    "single_trade": single_trade_data,
    "multi_trade": multi_trade_data,
    "warmup": warmup_data,
    "insufficient_bars": insufficient_bars_data,
}
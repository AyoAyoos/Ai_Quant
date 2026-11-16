"""
Input normalisation for QuantCode-Bench evaluation.

Maps AI_Quant strategy objects to QuantCode-Bench task_info format.
No dependencies on QuantCode-Bench internals.
"""

import uuid
from typing import Dict, Any


def _uuid_to_int(s: str) -> int:
    # Deterministic mapping of UUID to int within 31-bit range
    try:
        u = uuid.UUID(s)
        return int(u.int % (2**31 - 1))
    except Exception:
        # Fallback to hash
        return abs(hash(s)) % (2**31 - 1)


def build_task_description(strategy) -> str:
    """
    Build a natural language description for evaluation.

    Preference order:
    1. strategy.description if present
    2. Synthesised from strategy_spec
    3. Fallback generic
    """
    if getattr(strategy, "description", None):
        desc = strategy.description.strip()
        if desc:
            return desc

    spec = getattr(strategy, "strategy_spec", None) or {}
    parts = []

    market = spec.get("market") or getattr(strategy, "market", "NIFTY50")
    style = spec.get("trading_style")
    timeframe = spec.get("timeframe")

    if style and timeframe:
        parts.append(f"{style} {market} strategy on {timeframe} timeframe")
    else:
        parts.append(f"{market} strategy")

    indicators = spec.get("indicators") or []
    if indicators:
        ind_names = [i.get("name") for i in indicators if i.get("name")]
        if ind_names:
            parts.append(f"using indicators {', '.join(ind_names)}")

    entries = spec.get("entry_conditions") or []
    exits = spec.get("exit_conditions") or []
    if entries:
        parts.append(f"enter when {'; '.join(entries)}")
    if exits:
        parts.append(f"exit when {'; '.join(exits)}")

    risk = spec.get("risk_management") or {}
    if risk:
        parts.append(f"risk management with stop loss {risk.get('stop_loss_percent')}%")

    return ". ".join(parts) + "."

    # If nothing built, generic fallback
    return f"Trading strategy for {market}"


def map_strategy_to_qcb(strategy) -> Dict[str, Any]:
    """
    Return QuantCode-Bench task_info dict for a given AI_Quant strategy.

    QuantCode-Bench expects:
    - question: str
    - strategy_id: int
    - yf_symbol: str
    - timeframe: str
    """
    # Symbol mapping
    market = getattr(strategy, "market", "NIFTY50").upper()
    symbol_map = {
        "NIFTY50": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "SENSEX": "^BSESN",
    }
    yf_symbol = symbol_map.get(market, market)

    # Timeframe mapping
    spec = getattr(strategy, "strategy_spec", None) or {}
    timeframe = spec.get("timeframe") or "1d"
    # QuantCode-Bench supports 1d, 1h, 5m etc. Keep as-is.
    if timeframe not in ["1d", "1h", "5m", "15m", "30m"]:
        timeframe = "1d"

    task_description = build_task_description(strategy)

    task_info = {
        "question": task_description,
        "strategy_id": _uuid_to_int(getattr(strategy, "id", "0")),
        "yf_symbol": yf_symbol,
        "timeframe": timeframe,
    }
    return task_info

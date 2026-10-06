"""
Second-stage LLM call: given a conversation that looks like it has reached
a final strategy, force the model to output ONLY structured JSON matching
our StrategySpec schema — no prose, no markdown, no missed formatting.

This is deliberately a separate, narrow-purpose call rather than trying to
make the main chat model follow a strict format on every turn. A model asked
to do ONE thing ("convert this into JSON") is far more reliable than one
asked to juggle "chat naturally AND remember to format your final answer."
"""
import json
import httpx

from app.config import settings
from app.services.strategy_spec import StrategySpec, IndicatorSpec, ConditionSpec

FINALIZE_SYSTEM_PROMPT = """You convert a finished trading-strategy conversation into a JSON StrategySpec.
You will be given the full chat history. Output ONLY a JSON object — no markdown fences,
no commentary, nothing before or after it — matching exactly this shape:

{
  "version": 1,
  "name": "<short strategy name>",
  "indicators": [
    {"name": "<indicator name>", "type": "sma|ema|rsi", "period": <int 2-500>}
  ],
  "entry": {"left": "<operand>", "operator": "greater_than|less_than|crosses_above|crosses_below", "right_indicator": "<indicator name or null>", "right_value": <float or null>},
  "exit": {"left": "<operand>", "operator": "greater_than|less_than|crosses_above|crosses_below", "right_indicator": "<indicator name or null>", "right_value": <float or null>},
  "direction": "long"
}

Rules:
- version MUST be 1
- indicators: 1-10 items, each with unique name, type in [sma, ema, rsi], period 2-500
- entry/exit: left operand is "close" or indicator name; operator in [greater_than, less_than, crosses_above, crosses_below]; exactly one of right_indicator or right_value
- direction MUST be "long"
- No extra fields allowed
"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "finalized_strategy_spec",
        "schema": {
            "type": "object",
            "properties": {
                "version": {"type": "integer", "const": 1},
                "name": {"type": "string", "minLength": 1, "maxLength": 100},
                "indicators": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "minLength": 1, "maxLength": 50},
                            "type": {"type": "string", "enum": ["sma", "ema", "rsi"]},
                            "period": {"type": "integer", "minimum": 2, "maximum": 500}
                        },
                        "required": ["name", "type", "period"],
                        "additionalProperties": False
                    }
                },
                "entry": {
                    "type": "object",
                    "properties": {
                        "left": {"type": "string", "minLength": 1, "maxLength": 50},
                        "operator": {"type": "string", "enum": ["greater_than", "less_than", "crosses_above", "crosses_below"]},
                        "right_indicator": {"type": ["string", "null"], "maxLength": 50},
                        "right_value": {"type": ["number", "null"]}
                    },
                    "required": ["left", "operator"],
                    "additionalProperties": False
                },
                "exit": {
                    "type": "object",
                    "properties": {
                        "left": {"type": "string", "minLength": 1, "maxLength": 50},
                        "operator": {"type": "string", "enum": ["greater_than", "less_than", "crosses_above", "crosses_below"]},
                        "right_indicator": {"type": ["string", "null"], "maxLength": 50},
                        "right_value": {"type": ["number", "null"]}
                    },
                    "required": ["left", "operator"],
                    "additionalProperties": False
                },
                "direction": {"type": "string", "const": "long"}
            },
            "required": ["version", "name", "indicators", "entry", "exit", "direction"],
            "additionalProperties": False
        },
    },
}


async def finalize_strategy_spec(conversation_history: list[dict]) -> dict | None:
    """
    conversation_history: list of {"role": "user"|"assistant", "content": str}
    Returns validated StrategySpec dict or None on failure.
    Never raises — a failed finalize call should not crash the chat endpoint;
    the caller should just treat it as "not finalized yet."
    """
    payload = {
        "model": settings.groq_model,
        "messages": [{"role": "system", "content": FINALIZE_SYSTEM_PROMPT}] + conversation_history,
        "temperature": 0.1,
        "response_format": RESPONSE_SCHEMA,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.groq_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            parsed = json.loads(raw)

        # Validate with Pydantic StrategySpec
        from app.services.strategy_spec import StrategySpec, parse_strategy_spec
        spec = parse_strategy_spec(parsed)
        return spec.model_dump(mode="json")

    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, ValueError):
        # If your model doesn't support json_schema mode, this is where you'd
        # see it fail — check Groq's docs for which models support it, and
        # fall back to "type": "json_object" (valid JSON, no schema enforcement)
        # if needed.
        return None


# Backward compatibility alias for existing chat router
async def finalize_strategy(conversation_history: list[dict]) -> dict | None:
    """Backward compatibility wrapper - calls finalize_strategy_spec."""
    result = await finalize_strategy_spec(conversation_history)
    if result is None:
        return None
    # Convert StrategySpec back to legacy format for backward compatibility
    # The chat router expects {"name": ..., "description": ..., "code": ...}
    # We'll generate a simple Backtrader code representation from the StrategySpec
    indicators_code = []
    for ind in result.get("indicators", []):
        indicators_code.append(f"        self.{ind['name']} = bt.indicators.{ind['type'].upper()}(self.data.close, period={ind['period']})")
    
    entry_desc = f"{result['entry']['left']} {result['entry']['operator']} "
    if result['entry'].get('right_indicator'):
        entry_desc += result['entry']['right_indicator']
    else:
        entry_desc += str(result['entry']['right_value'])
    
    exit_desc = f"{result['exit']['left']} {result['exit']['operator']} "
    if result['exit'].get('right_indicator'):
        exit_desc += result['exit']['right_indicator']
    else:
        exit_desc += str(result['exit']['right_value'])
    
    # Build params tuple string separately to avoid f-string backslash issues
    params_list = [f'{ind["name"]}_period' for ind in result.get("indicators", [])]
    params_tuple = "(" + ", ".join(params_list) + ",)" if params_list else "()"
    
    code_lines = [
        "import backtrader as bt",
        "",
        "class GeneratedStrategy(bt.Strategy):",
        f"    params = {params_tuple}",
        "    def __init__(self):",
    ] + [f"        {line}" for line in indicators_code] + [
        "    def next(self):",
        f"        if not self.position and {entry_desc}:",
        "            self.buy()",
        f"        elif self.position and {exit_desc}:",
        "            self.sell()",
    ]
    code = "\n".join(code_lines)
    
    return {
        "name": result.get("name", "Untitled Strategy"),
        "description": f"Entry: {entry_desc}. Exit: {exit_desc}.",
        "code": code,
    }
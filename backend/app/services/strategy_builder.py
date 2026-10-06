"""
Structured Strategy Builder Service.

This service handles the structured strategy generation workflow:
1. Validates the strategy specification
2. Constructs a controlled prompt for the LLM
3. Calls the LLM to generate Backtrader-compatible Python code
4. Extracts and validates the generated code
5. Returns structured result for persistence
"""
import json
import httpx

from app.config import settings
from app.services.finalize_service import finalize_strategy
from app.services.strategy_extractor import extract_strategy, clean_reply_for_display
from app.schemas import (
    StrategyBuilderRequest,
    StrategySpecOut,
    IndicatorSpec,
    RiskManagementSpec,
)


# System prompt for structured strategy generation
STRATEGY_BUILDER_SYSTEM_PROMPT = """You are a quantitative trading strategy generator for the AI_Quant platform.

Your task: Generate a complete, executable Backtrader strategy based on the user's structured specification.

INPUT: You will receive a JSON specification with:
- market: Trading instrument (e.g., NIFTY50)
- trading_style: scalping | intraday | swing | positional
- timeframe: Chart timeframe (e.g., 15m, 1h, 1d)
- indicators: List of technical indicators with parameters
- entry_conditions: List of entry rule descriptions
- exit_conditions: List of exit rule descriptions
- risk_management: Stop loss, take profit, trailing stop, max trades per day

STRICT RULES:
1. Use ONLY the indicators specified. Do NOT add any other indicators.
2. Implement ONLY the entry conditions specified. Do NOT invent additional entry rules.
3. Implement ONLY the exit conditions specified. Do NOT invent additional exit rules.
4. Use EXACTLY the risk management parameters specified. Do NOT change them.
5. The strategy class MUST be named exactly `GeneratedStrategy`.
6. Include `import backtrader as bt` as the only import.
7. Do NOT include: if __name__ blocks, cerebro.run(), cerebro.plot(), CSV loading, print statements.
8. Generate deterministic, executable Backtrader-compatible Python code.
9. Use the indicator parameters exactly as specified.
10. For risk management: implement stop loss, take profit, and trailing stop as percentage-based exits.
11. For max_trades_per_day: implement a daily trade counter that prevents new entries after the limit.

INDICATOR MAPPING (use these exact Backtrader indicator classes):
- EMA -> bt.indicators.EMA
- SMA -> bt.indicators.SMA
- RSI -> bt.indicators.RSI
- MACD -> bt.indicators.MACD
- Bollinger Bands -> bt.indicators.BollingerBands
- Volume -> self.data.volume (no indicator needed, use directly)

OUTPUT FORMAT:
Return ONLY a JSON object with this exact structure:
{
  "name": "<short strategy name>",
  "description": "<one or two plain-English sentences describing the logic>",
  "code": "<complete Python code as a single string with \\n for newlines>"
}

The code field must contain:
- "import backtrader as bt"
- class GeneratedStrategy(bt.Strategy): with full implementation
- Properly escaped as JSON string (newlines as \\n, quotes as \\")
"""


# JSON schema for structured output
STRATEGY_BUILDER_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "generated_strategy",
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "code": {"type": "string"},
            },
            "required": ["name", "description", "code"],
            "additionalProperties": False,
        },
    },
}


def build_strategy_prompt(spec: StrategyBuilderRequest) -> str:
    """Build a detailed prompt from the structured specification."""
    
    # Format indicators
    indicator_lines = []
    for ind in spec.indicators:
        params_str = ", ".join(f"{k}={v}" for k, v in ind.parameters.items())
        indicator_lines.append(f"- {ind.name}({params_str})")
    indicators_text = "\n".join(indicator_lines)
    
    # Format conditions
    entry_text = "\n".join(f"- {c}" for c in spec.entry_conditions)
    exit_text = "\n".join(f"- {c}" for c in spec.exit_conditions)
    
    # Format risk management
    rm = spec.risk_management
    risk_text = (
        f"- Stop Loss: {rm.stop_loss_percent}%\n"
        f"- Take Profit: {rm.take_profit_percent}%\n"
    )
    if rm.trailing_stop_percent is not None:
        risk_text += f"- Trailing Stop: {rm.trailing_stop_percent}%\n"
    if rm.max_trades_per_day is not None:
        risk_text += f"- Max Trades Per Day: {rm.max_trades_per_day}\n"
    
    prompt = f"""Generate a Backtrader strategy for the following specification:

MARKET: {spec.market}
TRADING STYLE: {spec.trading_style}
TIMEFRAME: {spec.timeframe}

INDICATORS:
{indicators_text}

ENTRY CONDITIONS:
{entry_text}

EXIT CONDITIONS:
{exit_text}

RISK MANAGEMENT:
{risk_text}

Generate the complete strategy code following all the rules in the system prompt."""
    
    return prompt


async def generate_structured_strategy(spec: StrategyBuilderRequest) -> dict:
    """
    Generate a strategy from structured specification using the LLM.
    
    Returns dict with: name, description, code
    Raises on failure.
    """
    prompt = build_strategy_prompt(spec)
    
    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": STRATEGY_BUILDER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "response_format": STRATEGY_BUILDER_RESPONSE_SCHEMA,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.groq_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        parsed = json.loads(raw)
    
    if not all(k in parsed for k in ("name", "description", "code")):
        raise ValueError("LLM response missing required fields")
    
    return parsed


def validate_indicator_parameters(spec: StrategyBuilderRequest) -> list[str]:
    """Validate indicator parameters against expected schemas. Returns list of errors."""
    errors = []
    
    # Expected parameter schemas per indicator
    param_schemas = {
        "EMA": {"fast": (int, 1, 200), "slow": (int, 1, 200)},
        "SMA": {"period": (int, 1, 200)},
        "RSI": {"period": (int, 1, 100), "oversold": (int, 1, 50), "overbought": (int, 50, 100)},
        "MACD": {"fast": (int, 1, 50), "slow": (int, 1, 100), "signal": (int, 1, 50)},
        "Bollinger Bands": {"period": (int, 1, 100), "devfactor": (float, 0.1, 5.0)},
        "Volume": {},  # No parameters
    }
    
    for ind in spec.indicators:
        schema = param_schemas.get(ind.name, {})
        for param_name, (param_type, min_val, max_val) in schema.items():
            if param_name not in ind.parameters:
                errors.append(f"Indicator {ind.name} missing required parameter: {param_name}")
            else:
                value = ind.parameters[param_name]
                if not isinstance(value, param_type):
                    errors.append(f"Indicator {ind.name} parameter {param_name} must be {param_type.__name__}")
                elif not (min_val <= value <= max_val):
                    errors.append(f"Indicator {ind.name} parameter {param_name} must be between {min_val} and {max_val}")
        
        # Check for unexpected parameters
        for param_name in ind.parameters:
            if param_name not in schema:
                errors.append(f"Indicator {ind.name} has unexpected parameter: {param_name}")
    
    return errors


def convert_spec_to_output(spec: StrategyBuilderRequest) -> StrategySpecOut:
    """Convert validated request to output schema."""
    return StrategySpecOut(
        market=spec.market,
        trading_style=spec.trading_style,
        timeframe=spec.timeframe,
        indicators=spec.indicators,
        entry_conditions=spec.entry_conditions,
        exit_conditions=spec.exit_conditions,
        risk_management=spec.risk_management,
    )
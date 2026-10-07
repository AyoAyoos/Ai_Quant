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
import re
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
- indicators: List of technical indicators with parameters
- entry_conditions: List of entry rule descriptions
- exit_conditions: List of exit rule descriptions
- risk_management: Stop loss, take profit, trailing stop, max trades per day

IMPORTANT: Backtests always run on the NIFTY 50 daily bars dataset (2-year history, ~500 bars). 
All indicators are calculated on daily data regardless of the timeframe label chosen. 
Design your entry/exit logic so it will actually trigger on ~500 daily bars — 
avoid near-impossible multi-condition AND conjunctions (e.g., "EMA cross-up AND RSI < 30" rarely coincide on daily bars);
prefer conditions that can realistically coincide or use OR logic for exits.

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

IMPLEMENTATION REQUIREMENTS (CRITICAL - your code MUST follow these patterns):

A. INDICATOR INITIALIZATION (in __init__):
   - Create ALL indicators specified using the exact Backtrader classes from the mapping below
   - Use indicator parameters EXACTLY as specified
   - Store indicators as self.indicator_name (e.g., self.ema_fast, self.rsi)
   - For multiple EMAs/SMAs, use descriptive names like ema_fast, ema_slow

B. CROSSOVER DETECTION (in next()):
   - Bullish crossover (fast crosses above slow): indicator_fast[0] > indicator_slow[0] and indicator_fast[-1] <= indicator_slow[-1]
   - Bearish crossover (fast crosses below slow): indicator_fast[0] < indicator_slow[0] and indicator_fast[-1] >= indicator_slow[-1]
   - Use [0] for current bar, [-1] for previous bar - NEVER use [1] (lookahead)

C. THRESHOLD CONDITIONS (in next()):
   - "RSI is below 30" -> self.rsi[0] < 30
   - "RSI is above 70" -> self.rsi[0] > 70
   - "Price above upper band" -> self.data.close[0] > self.bb.top[0]
   - "Price below lower band" -> self.data.close[0] < self.bb.bot[0]
   - "Volume spike" -> self.data.volume[0] > self.data.volume[-1] * 1.5 (or similar)

D. ENTRY LOGIC (in next()):
   - Check ALL entry conditions must be met (AND logic)
   - Only enter if not self.position
   - Increment trade counter on entry
   - Store entry_price = self.data.close[0] for risk management

E. EXIT LOGIC (in next()):
   - Check exit conditions OR risk management exits (OR logic)
   - Only exit if self.position
   - User-specified exits (e.g., "Exit on opposite signal" = bearish crossover OR RSI overbought)
   - Risk management exits (stop loss, take profit, trailing stop) - ALWAYS implement these
   - For stop loss: (entry_price - current_price) / entry_price * 100 >= stop_loss_pct
   - For take profit: (current_price - entry_price) / entry_price * 100 >= take_profit_pct
   - For trailing stop: track highest_price_since_entry, exit if (highest - current) / highest * 100 >= trailing_pct

F. MAX TRADES PER DAY:
   - Track self.trade_count and self.last_trade_date
   - Reset counter when date changes
   - Skip new entries if trade_count >= max_trades_per_day

INDICATOR MAPPING (use these EXACT Backtrader indicator classes):
- EMA -> bt.indicators.EMA
- SMA -> bt.indicators.SMA
- RSI -> bt.indicators.RSI
- MACD -> bt.indicators.MACD
- Bollinger Bands -> bt.indicators.BollingerBands
- Volume -> self.data.volume (no indicator needed, use directly)

COMPLETE WORKING EXAMPLE (daily-appropriate):
For spec: EMA(20,50), RSI(14,30,70), entry="EMA 20 crosses above EMA 50", exit="Exit on opposite signal", SL=1%, TP=2%, trailing=0.5%, max_trades=3

```python
import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    params = (
        ("ema_fast_period", 20),
        ("ema_slow_period", 50),
        ("rsi_period", 14),
        ("rsi_oversold", 30),
        ("rsi_overbought", 70),
        ("stop_loss_pct", 1.0),
        ("take_profit_pct", 2.0),
        ("trailing_stop_pct", 0.5),
        ("max_trades_per_day", 3),
    )

    def __init__(self):
        # Indicators - use EXACT parameters from spec
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast_period)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.p.ema_slow_period)
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        
        # Trade tracking
        self.trade_count = 0
        self.last_trade_date = None
        self.entry_price = None
        self.highest_price = None

    def next(self):
        # Max trades per day check
        current_date = self.data.datetime.date(0)
        if self.last_trade_date != current_date:
            self.trade_count = 0
            self.last_trade_date = current_date
        
        if self.trade_count >= self.p.max_trades_per_day:
            return
        
        # Entry conditions (ALL must be true - AND logic)
        ema_cross_up = self.ema_fast[0] > self.ema_slow[0] and self.ema_fast[-1] <= self.ema_slow[-1]
        
        if not self.position and ema_cross_up:
            self.buy()
            self.trade_count += 1
            self.entry_price = self.data.close[0]
            self.highest_price = self.data.close[0]
            return
        
        # Exit conditions (ANY can trigger - OR logic)
        if self.position:
            # User-specified exit: opposite signal
            ema_cross_down = self.ema_fast[0] < self.ema_slow[0] and self.ema_fast[-1] >= self.ema_slow[-1]
            rsi_overbought = self.rsi[0] > self.p.rsi_overbought
            exit_opposite = ema_cross_down or rsi_overbought
            
            # Risk management exits
            current_price = self.data.close[0]
            self.highest_price = max(self.highest_price, current_price)
            
            stop_loss_hit = (self.entry_price - current_price) / self.entry_price * 100 >= self.p.stop_loss_pct
            take_profit_hit = (current_price - self.entry_price) / self.entry_price * 100 >= self.p.take_profit_pct
            trailing_stop_hit = (self.highest_price - current_price) / self.highest_price * 100 >= self.p.trailing_stop_pct
            
            if exit_opposite or stop_loss_hit or take_profit_hit or trailing_stop_hit:
                self.sell()
                self.entry_price = None
                self.highest_price = None
```

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

INDICATORS:
{indicators_text}

ENTRY CONDITIONS:
{entry_text}

EXIT CONDITIONS:
{exit_text}

RISK MANAGEMENT:
{risk_text}

Generate the complete strategy code following all the rules in the system prompt. Pay special attention to the IMPLEMENTATION REQUIREMENTS section which shows exact code patterns for crossover detection, threshold conditions, entry/exit logic, and risk management."""
    
    return prompt


def validate_generated_code(code: str) -> list[str]:
    """
    Validate that the generated code has basic trading logic.
    Returns list of warnings (non-blocking) and errors (blocking).
    """
    warnings = []
    errors = []
    
    # Check for required imports
    if "import backtrader as bt" not in code:
        errors.append("Missing 'import backtrader as bt'")
    
    # Check for GeneratedStrategy class
    if "class GeneratedStrategy" not in code:
        errors.append("Missing 'class GeneratedStrategy' definition")
    
    # Check for __init__ method
    if "def __init__" not in code:
        warnings.append("No __init__ method found - indicators may not be initialized")
    
    # Check for next method
    if "def next" not in code:
        errors.append("Missing 'def next' method - strategy will not execute any logic")
    
    # Check for buy/sell calls
    if "self.buy()" not in code and "self.buy(" not in code:
        warnings.append("No buy() call found - strategy may not enter positions")
    
    if "self.sell()" not in code and "self.sell(" not in code and "self.close()" not in code:
        warnings.append("No sell()/close() call found - strategy may not exit positions")
    
    # Check for indicator initialization (bt.indicators)
    if "bt.indicators" not in code:
        warnings.append("No bt.indicators initialization found - strategy may not use any indicators")
    
    # Check for position check
    if "self.position" not in code:
        warnings.append("No self.position check found - strategy may not handle position state correctly")
    
    # Check for entry_price tracking (needed for stop loss/take profit)
    # Look for any risk management parameter usage
    has_risk_params = any(param in code for param in [
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
        "self.p.stop_loss", "self.p.take_profit", "self.p.trailing_stop"
    ])
    if "entry_price" not in code and has_risk_params:
        warnings.append("Risk management parameters used but entry_price not tracked - stop loss/take profit may not work")
    
    return {"warnings": warnings, "errors": errors}


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
    
    # Validate generated code
    validation = validate_generated_code(parsed["code"])
    if validation["errors"]:
        raise ValueError(f"Generated code validation failed: {'; '.join(validation['errors'])}")
    
    # Log warnings but don't fail
    if validation["warnings"]:
        import logging
        logger = logging.getLogger(__name__)
        for w in validation["warnings"]:
            logger.warning(f"Generated code warning: {w}")
    
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
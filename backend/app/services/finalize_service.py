"""
Second-stage LLM call.

This service takes a finished trading-strategy conversation and converts it
into a structured Strategy Specification.

Important:
- The LLM does NOT generate Python/Backtrader code here.
- The output is structured JSON.
- The structured specification will later be validated by our Python
  StrategySpec model and then converted into Backtrader code by our own
  system.
"""

import json
import httpx

from app.config import settings


FINALIZE_SYSTEM_PROMPT = """
You convert a finished trading-strategy conversation into a structured
trading strategy specification.

You will be given the full chat history.

Your job is ONLY to extract the strategy requirements into the required
JSON structure.

DO NOT:
- Generate Python code.
- Generate Backtrader code.
- Invent historical performance.
- Invent strategy requirements.
- Add fields that are not in the schema.
- Add explanations outside the JSON object.

The output must contain:

{
  "name": "short strategy name",
  "description": "one or two plain-English sentences describing the strategy",
  "market": "NIFTY50",
  "timeframe": "1D",
  "indicators": [
    {
      "type": "SMA",
      "period": 10
    }
  ],
  "entry_conditions": [
    "condition 1"
  ],
  "exit_conditions": [
    "condition 1"
  ],
  "risk_management": {
    "risk_per_trade": 0.01,
    "max_positions": 1,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.05
  }
}

Rules:

1. market must be "NIFTY50".
2. timeframe must be "1D".
3. risk_per_trade must never exceed 0.01.
4. max_positions should normally be 1 unless the user explicitly requests
   otherwise.
5. Only include indicators actually required by the user's strategy.
6. Preserve the user's numerical parameters exactly.
7. Do not invent missing strategy requirements.
8. If an important requirement is missing, the main chat should have asked
   the user for clarification before finalization.
9. Output ONLY the JSON object.
"""


RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "strategy_specification",
        "schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string"
                },
                "description": {
                    "type": "string"
                },
                "market": {
                    "type": "string",
                    "enum": ["NIFTY50"]
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["1D"]
                },
                "indicators": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "SMA",
                                    "EMA",
                                    "RSI",
                                    "VolumeSMA",
                                    "MACD",
                                    "BollingerBands"
                                ]
                            },
                            "period": {
                                "type": ["integer", "null"]
                            }
                        },
                        "required": [
                            "type",
                            "period"
                        ],
                        "additionalProperties": False
                    }
                },
                "entry_conditions": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                },
                "exit_conditions": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                },
                "risk_management": {
                    "type": "object",
                    "properties": {
                        "risk_per_trade": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 0.01
                        },
                        "max_positions": {
                            "type": "integer",
                            "minimum": 1
                        },
                        "stop_loss_pct": {
                            "type": ["number", "null"],
                            "minimum": 0,
                            "maximum": 1
                        },
                        "take_profit_pct": {
                            "type": ["number", "null"],
                            "minimum": 0,
                            "maximum": 10
                        }
                    },
                    "required": [
                        "risk_per_trade",
                        "max_positions",
                        "stop_loss_pct",
                        "take_profit_pct"
                    ],
                    "additionalProperties": False
                }
            },
            "required": [
                "name",
                "description",
                "market",
                "timeframe",
                "indicators",
                "entry_conditions",
                "exit_conditions",
                "risk_management"
            ],
            "additionalProperties": False
        }
    }
}


async def finalize_strategy(
    conversation_history: list[dict],
) -> dict | None:
    """
    Convert a finished trading-strategy conversation into a structured
    strategy specification.

    conversation_history:
        List of dictionaries containing:
        {"role": "user"|"assistant", "content": str}

    Returns:
        A structured strategy specification dictionary, or None if the
        finalization call fails.
    """

    payload = {
        "model": settings.groq_model,
        "messages": [
            {
                "role": "system",
                "content": FINALIZE_SYSTEM_PROMPT,
            }
        ] + conversation_history,
        "temperature": 0.1,
        "response_format": RESPONSE_SCHEMA,
    }

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.groq_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

            response.raise_for_status()

            data = response.json()

            raw_content = data["choices"][0]["message"]["content"]

            parsed = json.loads(raw_content)

        required_fields = (
            "name",
            "description",
            "market",
            "timeframe",
            "indicators",
            "entry_conditions",
            "exit_conditions",
            "risk_management",
        )

        if not all(field in parsed for field in required_fields):
            return None

        return parsed

    except (
        httpx.HTTPError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ):
        return None
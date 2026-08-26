"""
Second-stage LLM call: given a conversation that looks like it has reached
a final strategy, force the model to output ONLY structured JSON matching
our schema — no prose, no markdown, no missed formatting.

This is deliberately a separate, narrow-purpose call rather than trying to
make the main chat model follow a strict format on every turn. A model asked
to do ONE thing ("convert this into JSON") is far more reliable than one
asked to juggle "chat naturally AND remember to format your final answer."
"""
import json
import httpx

from app.config import settings 

FINALIZE_SYSTEM_PROMPT = """You convert a finished trading-strategy conversation into JSON.
You will be given the full chat history. Output ONLY a JSON object — no markdown fences,
no commentary, nothing before or after it — matching exactly this shape:

{
  "name": "<short strategy name>",
  "description": "<one or two plain-English sentences describing the logic>",
  "code": "<complete Python code as a single string, with \\n for newlines>"
}

Rules for the "code" field:
- Must contain: "import backtrader as bt" followed by a class named exactly GeneratedStrategy
  that subclasses bt.Strategy, fully implementing the strategy discussed in the conversation.
- Do NOT include: if __name__ blocks, cerebro.run(), cerebro.plot(), CSV loading code,
  print statements, or any "how to run this" text — ONLY the import and the class.
- Escape the code properly as a JSON string (newlines as \\n, quotes as \\").
"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "finalized_strategy",
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


async def finalize_strategy(conversation_history: list[dict]) -> dict | None:
    """
    conversation_history: list of {"role": "user"|"assistant", "content": str}
    Returns {"name": ..., "description": ..., "code": ...} or None on failure.
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

        if not all(k in parsed for k in ("name", "description", "code")):
            return None
        return parsed

    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError):
        # If your model doesn't support json_schema mode, this is where you'd
        # see it fail — check Groq's docs for which models support it, and
        # fall back to "type": "json_object" (valid JSON, no schema enforcement)
        # if needed.
        return None
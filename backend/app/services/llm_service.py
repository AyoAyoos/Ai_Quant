"""
LLM service — talks to Groq's OpenAI-compatible API.

Why Groq: free developer tier, very fast inference, and hosts open-source
models (Llama 3.1, Qwen2.5, Mixtral) so it satisfies the "keep the AI free /
open-source model" requirement from the project brief. Swappable later for
a local Ollama server by changing base_url + model in config.py.
"""
import httpx

from app.config import settings

SYSTEM_PROMPT = """You are a quantitative trading strategy assistant embedded in an app.
Your job:
1. Ask clarifying follow-up questions if the user's request is vague (risk level,
   holding period, instruments, market: default is NIFTY50).
2. Once you have enough detail, respond with a short strategy description AND
   a Python function implementing the strategy logic using Backtrader's
   Strategy class conventions.
3. Never claim guaranteed returns. Always note this is for paper trading /
   educational purposes only, not financial advice.
4. Keep responses concise and beginner-friendly — the user may not know finance jargon.
"""


async def chat_completion(messages: list[dict]) -> str:
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    Returns the assistant's reply text.
    """
    payload = {
        "model": settings.groq_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.groq_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

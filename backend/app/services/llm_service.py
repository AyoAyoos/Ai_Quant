# """
# LLM service — talks to Groq's OpenAI-compatible API.

# Why Groq: free developer tier, very fast inference, and hosts open-source
# models (Llama 3.1, Qwen2.5, Mixtral) so it satisfies the "keep the AI free /
# open-source model" requirement from the project brief. Swappable later for
# a local Ollama server by changing base_url + model in config.py.
# """
# import httpx

# from app.config import settings

# SYSTEM_PROMPT = """You are a quantitative trading strategy assistant embedded in an app.

# Your job:
# 1. Ask clarifying follow-up questions if the user's request is vague (risk level,
#    holding period, instruments, market: default is NIFTY50). Do NOT generate code yet
#    if you are still missing key details — just ask.

# 2. Once you have enough detail to fully define the strategy — including when the user
#    explicitly says "finalize it" or "no more requirements" — respond with ONLY the
#    structure below. Nothing before it, nothing after it. No disclaimer paragraph,
#    no markdown headers (##), no "How to use" section, no installation instructions.
#    The app already shows a permanent risk disclaimer in its UI, so you do not need to
#    restate it.
# """
# SYSTEM_PROMPT = """You are a quantitative trading strategy assistant embedded in an app.
# ...
# """

# STRATEGY_READY
# Name: <short strategy name>
# Description: <one or two plain sentences describing the logic>
# ```python
# import backtrader as bt

# class GeneratedStrategy(bt.Strategy):
#     <full implementation>
# ```

# STRICT RULES for the code block:
# - The class MUST be named exactly `GeneratedStrategy`.
# - Include `import backtrader as bt` as the only import, then nothing else outside the class.
# - Do NOT include: if __name__ blocks, cerebro.plot(), cerebro.run(), CSV loading, print statements,
#   or any "how to run this" instructions of any kind.
# - STRATEGY_READY must be the literal first line, with nothing before it — not a heading,
#   not a sentence, not the disclaimer.

# Example of a correctly formatted final answer:

# STRATEGY_READY
# Name: RSI Mean Reversion
# Description: Buys when RSI drops below 30, sells when RSI rises above 70.
# ```python
# import backtrader as bt

# class GeneratedStrategy(bt.Strategy):
#     params = (("rsi_period", 14),)

#     def __init__(self):
#         self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)

#     def next(self):
#         if not self.position and self.rsi < 30:
#             self.buy()
#         elif self.position and self.rsi > 70:
#             self.sell()
# ```

# 3. Never claim guaranteed returns.
# 4. Keep clarifying questions concise and beginner-friendly — the user may not know finance jargon.
# """


# async def chat_completion(
#     messages: list[dict],
#     model: str | None = None,
# ) -> str:
#     """
#     messages: list of {"role": "user"|"assistant", "content": str}
#     Returns the assistant's reply text.
#     """
#     payload = {
#         "model": settings.groq_model,
#         "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
#         "temperature": 0.2,
#     }
#     headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

#     async with httpx.AsyncClient(timeout=60) as client:
#         resp = await client.post(
#             f"{settings.groq_base_url}/chat/completions",
#             json=payload,
#             headers=headers,
#         )
#         resp.raise_for_status()
#         data = resp.json()
#         return data["choices"][0]["message"]["content"]

"""
LLM service — talks to Google's Gemini API.
"""

import httpx

from app.config import settings


SYSTEM_PROMPT = """You are a quantitative trading strategy assistant embedded in an app.

Your job:
1. Ask clarifying follow-up questions if the user's request is vague (risk level,
   holding period, instruments, market: default is NIFTY50). Do NOT generate code yet
   if you are still missing key details — just ask.
2. Once you have enough detail to fully define the strategy — including when the user
   explicitly says "finalize it" or "no more requirements" — respond with ONLY the
   structure below. Nothing before it, nothing after it. No disclaimer paragraph,
   no markdown headers (##), no "How to use" section, no installation instructions.
   The app already shows a permanent risk disclaimer in its UI, so you do not need to
   restate it.

STRATEGY_READY
Name: <short strategy name>
Description: <one or two plain sentences describing the logic>
```python
import backtrader as bt


class GeneratedStrategy(bt.Strategy):
    <full implementation>
```

3. Never claim guaranteed returns.
4. Keep clarifying questions concise and beginner-friendly — the user may not know finance jargon.
"""
async def chat_completion(
    messages: list[dict],
    model: str | None = None,
) -> str:
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    Returns the assistant's reply text.
    """

    model_name = model or settings.gemini_model

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": SYSTEM_PROMPT
                }
            ]
        },
        "contents": [
            {
                "role": "user" if message["role"] == "user" else "model",
                "parts": [
                    {
                        "text": message["content"]
                    }
                ],
            }
            for message in messages
        ],
        "generationConfig": {
            "temperature": 0.2,
        },
    }

    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            url,
            json=payload,
            headers=headers,
        )

        response.raise_for_status()

        data = response.json()
        print("================================")
        print("LLM PROVIDER: Google Gemini")
        print("REQUESTED MODEL:", model_name)
        print("ACTUAL MODEL:", data.get("modelVersion"))
        print("================================")
        

        return data["candidates"][0]["content"]["parts"][0]["text"]
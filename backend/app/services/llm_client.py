"""Shared Gemini client for every LLM call in the app.

Gemini exposes an OpenAI-compatible chat endpoint, so the rest of the app keeps
using ``choices[0].message.content``. This module owns the provider-specific
parts: credential validation, the primary/fallback model chain, and rate-limit
handling. Keeping it in one place means chat, structured builder and finalize
all get the same failover behaviour.

The API key is only ever used in the Authorization header. It is never included
in exceptions or log messages.
"""

import asyncio
import logging

import httpx

from app.config import settings
from app.services.llm_errors import LLMNotConfiguredError, LLMRateLimitError

logger = logging.getLogger(__name__)

# Short delay before retrying the same model once; if it is still throttled we
# move on to the next model in the chain instead of waiting it out.
_RETRY_DELAYS = (1, 2)


class _UnsupportedFormatError(Exception):
    """The provider rejected a ``response_format`` value with HTTP 400."""


def require_api_key() -> str:
    """Return a usable key or fail before any HTTP request is attempted."""
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise LLMNotConfiguredError(
            "LLM API key is not configured. Set GEMINI_API_KEY in backend/.env "
            "and restart the backend."
        )
    return key


def model_chain() -> list[str]:
    """Primary model plus configured fallbacks (de-duplicated)."""
    return settings.llm_model_chain()


def _content_from_response(resp) -> str:
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def _call_chain(messages, temperature, response_format, timeout, client) -> str:
    """Try every configured model in order until one answers successfully."""
    api_key = require_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    last_error: Exception | None = None

    for model in model_chain():
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        for attempt, delay in enumerate((None, *_RETRY_DELAYS)):
            if delay is not None:
                await asyncio.sleep(delay)
            try:
                resp = await client.post(
                    f"{settings.gemini_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 0:
                    continue
                logger.warning("LLM request failed for model %s: %s", model, type(exc).__name__)
                break

            status = getattr(resp, "status_code", None) or 200

            if status == 200:
                return _content_from_response(resp)

            if status == 400 and response_format is not None:
                # Not all models accept every response_format. Tell the caller
                # to retry with a weaker format rather than burning the chain.
                raise _UnsupportedFormatError(f"model {model} rejected response_format")

            if status == 429:
                last_error = LLMRateLimitError(
                    "AI rate limit reached - please wait a few seconds and click Try Again"
                )
                if attempt == 0:
                    continue
                logger.warning("LLM model %s rate-limited; trying next model", model)
                break

            if status >= 500:
                last_error = httpx.HTTPStatusError(
                    f"LLM provider error {status}", request=httpx.Request("POST", "llm"),
                    response=httpx.Response(status),
                )
                if attempt == 0:
                    continue
                logger.warning("LLM model %s returned %s; trying next model", model, status)
                break

            # Other 4xx errors are not fixed by switching models.
            resp.raise_for_status()

    raise last_error or LLMRateLimitError(
        "AI rate limit reached - please wait a few seconds and click Try Again"
    )


async def chat_completion_raw(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    response_format: dict | None = None,
    timeout: float = 60,
) -> str:
    """Return the assistant reply text, failing over across models as needed.

    ``response_format`` is optional. If a model rejects it, we retry the whole
    chain with progressively looser formats; the app's JSON parsers already
    cope with unenforced JSON.
    """
    require_api_key()  # fail fast, before creating any HTTP client

    formats: list[dict | None]
    if response_format is None:
        formats = [None]
    else:
        formats = [response_format, {"type": "json_object"}, None]

    async with httpx.AsyncClient(timeout=timeout) as client:
        for index, fmt in enumerate(formats):
            try:
                return await _call_chain(messages, temperature, fmt, timeout, client)
            except _UnsupportedFormatError:
                if index == len(formats) - 1:
                    raise ValueError("LLM provider rejected all response formats")
                logger.warning("LLM rejected response_format; retrying with a looser format")

    raise LLMRateLimitError("AI rate limit reached - please wait a few seconds and click Try Again")

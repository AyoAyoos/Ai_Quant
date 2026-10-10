"""Errors raised when the LLM is called without usable credentials.

Kept separate from the service modules so routers can map "the operator has
not configured a key" to a distinct, actionable response (503) instead of the
generic 502 they use for upstream/validation failures — and so the missing
credential is never mistaken for a malformed LLM response.
"""


class LLMNotConfiguredError(ValueError):
    """The LLM was called but no API key is configured for the provider.

    Subclasses ``ValueError`` so callers that already catch ``ValueError``
    keep working, while dedicated handlers can surface the setup problem.
    """

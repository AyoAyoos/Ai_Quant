"""
Parses an LLM reply for a finalized strategy.

Two paths, in order:
1. Strict path: reply starts with STRATEGY_READY and matches the expected
   Name/Description/code format exactly. Preferred — this is what the system
   prompt asks for.
2. Fallback path: the model ignored the format (common with smaller open
   models) but still produced a real Backtrader strategy — i.e. a ```python
   code block containing a `bt.Strategy` subclass. We still extract it,
   because rejecting a perfectly usable strategy just because the model
   skipped a formatting marker is worse than cleaning it up ourselves.
   Both paths normalize the code: force the class name to GeneratedStrategy
   and strip any __main__ / cerebro.run() / plotting boilerplate the model
   added despite being told not to.
"""
import re
from dataclasses import dataclass

READY_MARKER = "STRATEGY_READY"

_STRICT_PATTERN = re.compile(
    r"Name:\s*(?P<name>.+?)\s*\n"
    r"Description:\s*(?P<description>.+?)\s*\n"
    r"```python\s*\n(?P<code>.*?)```",
    re.DOTALL,
)

# Fallback: just grab the first ```python fenced block containing a bt.Strategy class
_CODE_BLOCK_PATTERN = re.compile(r"```python\s*\n(?P<code>.*?)```", re.DOTALL)
_HAS_STRATEGY_CLASS = re.compile(r"class\s+\w+\(bt\.Strategy\)")
_CLASS_NAME_PATTERN = re.compile(r"class\s+\w+\(bt\.Strategy\)")


@dataclass
class ExtractedStrategy:
    name: str
    description: str
    code: str
    used_fallback: bool = False


def _clean_code(code: str) -> str:
    """Force class name to GeneratedStrategy and strip runnable-script boilerplate."""
    code = _CLASS_NAME_PATTERN.sub("class GeneratedStrategy(bt.Strategy)", code, count=1)
    # Cut anything from a stray __main__ guard onward (plotting, cerebro.run(), CSV loading, etc.)
    code = re.split(r"\nif __name__", code)[0]
    return code.strip()


def _guess_name_from_reply(reply: str) -> str:
    """Best-effort strategy name when the model skipped the Name: field."""
    header = re.search(r"^#{1,3}\s*(.+)$", reply, re.MULTILINE)
    if header:
        return header.group(1).strip().strip("*")
    return "Untitled Strategy"


def extract_strategy(llm_reply: str) -> ExtractedStrategy | None:
    """
    Returns an ExtractedStrategy if a finished strategy can be found in this
    reply (strict format or fallback), else None if this looks like an
    ordinary clarifying question / non-final reply.
    """
    stripped = llm_reply.strip()

    # --- Strict path ---
    if stripped.startswith(READY_MARKER):
        match = _STRICT_PATTERN.search(stripped)
        if match:
            return ExtractedStrategy(
                name=match.group("name").strip(),
                description=match.group("description").strip(),
                code=_clean_code(match.group("code")),
            )
        # Started with the marker but didn't match the rest of the shape —
        # fall through to the fallback path rather than giving up entirely.

    # --- Fallback path ---
    code_match = _CODE_BLOCK_PATTERN.search(stripped)
    if code_match and _HAS_STRATEGY_CLASS.search(code_match.group("code")):
        return ExtractedStrategy(
            name=_guess_name_from_reply(stripped),
            description=(
                "Auto-extracted — the model did not follow the expected reply "
                "format, so no description was provided."
            ),
            code=_clean_code(code_match.group("code")),
            used_fallback=True,
        )

    return None
    
def looks_like_final_strategy(llm_reply: str) -> bool:
    """
    Cheap heuristic to decide whether this reply is worth sending to the
    finalize_service for structured extraction. Deliberately permissive —
    false positives just cost one extra API call, false negatives mean a
    finished strategy silently never gets saved, which is worse.
    """
    stripped = llm_reply.strip()
    if stripped.startswith(READY_MARKER):
        return True
    if "```python" in stripped and _HAS_STRATEGY_CLASS.search(stripped):
        return True
    return False
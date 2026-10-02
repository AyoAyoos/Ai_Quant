"""UUID validation shared by every endpoint that takes an id.

All primary and foreign keys are Postgres `UUID` columns. Handing Postgres
`'abc123'::UUID` raises a DataError *inside* the query — before the caller's
"not found" check can run — so a malformed id escapes as an unhandled 500
instead of the 404 the route intends. Validating first keeps the bad value
out of the database entirely.
"""
import uuid

from fastapi import HTTPException

MAX_ECHOED_ID = 64


def canonical_uuid(value: str) -> str | None:
    """Lowercase hyphenated form of `value`, or None when it is not a UUID.

    Every textual form `uuid.UUID` accepts (uppercase, unhyphenated, brace-
    or urn-wrapped) canonicalises to the same string, so they all resolve to
    the stored row rather than failing.
    """
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


def canonical_uuid_or_404(value: str, detail: str) -> str:
    """`value` as a canonical UUID string, or a 404 carrying `detail`."""
    canonical = canonical_uuid(value)
    if canonical is None:
        raise HTTPException(status_code=404, detail=detail) from None
    return canonical


def strategy_not_found(value: str) -> str:
    """404 detail shared by every strategy route, echoing a length-capped id."""
    return f"Strategy {value[:MAX_ECHOED_ID]} not found"
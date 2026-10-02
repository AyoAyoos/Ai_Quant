"""Cross-cutting HTTP middleware.

Starlette wraps middleware in reverse order of addition, so the LAST one added
is the OUTERMOST.
"""
import logging

from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Single source of truth for browser origins allowed to call this API.
CORS_ALLOW_ORIGINS = [
    "http://localhost:5173",  # React dev server
    "http://localhost:3000",  # dockerized nginx frontend
]


class JsonErrorMiddleware(BaseHTTPMiddleware):
    """Turn an unhandled exception into a JSON 500 the browser can read.

    Starlette's ServerErrorMiddleware is the outermost middleware, so it sits
    OUTSIDE CORSMiddleware. A 500 it generates therefore carries no
    Access-Control-Allow-Origin: the browser blocks the response, fetch
    rejects, and the frontend reports the API as offline even though it is up.

    Registering this middleware INSIDE CORSMiddleware builds the JSON 500 here,
    so the CORS layer decorates it on the way out. HTTPException and request
    validation errors are already converted to responses by
    ExceptionMiddleware, which runs further in, so 404/422 behaviour — and the
    two 422 body shapes — are untouched.
    """

    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "Unhandled error serving %s %s", request.method, request.url.path
            )
            return JSONResponse(
                status_code=500, content={"detail": "Internal server error"}
            )
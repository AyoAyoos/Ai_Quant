from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware import CORS_ALLOW_ORIGINS, JsonErrorMiddleware
from app.routers import chat
from app.routers import market
from app.routers import paper
from app.routers import strategies

from pathlib import Path


import time
import logging
import asyncio

logger = logging.getLogger(__name__)

def _run_migrations_sync() -> None:
    """Apply pending Alembic migrations. The schema is owned by migrations;
    nothing here creates tables directly."""
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    # Retry a few times to allow the database to become ready
    max_attempts = 10
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            command.upgrade(cfg, "head")
            logger.info("Alembic migrations applied successfully")
            return
        except Exception as exc:
            if attempt == max_attempts:
                logger.exception("Alembic migrations failed after %d attempts", max_attempts)
                raise
            logger.warning("Alembic migration attempt %d/%d failed: %s – retrying in %.1fs", attempt, max_attempts, exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 10.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(_run_migrations_sync)
    yield


app = FastAPI(
    title="AI Conversational Quant Trading App",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# Middleware runs outside-in in reverse order of addition: the last one added is
# the outermost. CORS is therefore added last, so that it wraps JsonErrorMiddleware
# and decorates the JSON 500 it builds for an unhandled exception with
# Access-Control-Allow-Origin. Adding them the other way round leaves the 500
# outside CORS and the browser reports the API as offline.
app.add_middleware(JsonErrorMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(market.router)
app.include_router(paper.router)
app.include_router(strategies.router)


@app.get("/health")
def health():
    return {"status": "ok"}

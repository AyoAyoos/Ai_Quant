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


def _run_migrations() -> None:
    """Apply pending Alembic migrations. The schema is owned by migrations;
    nothing here creates tables directly."""
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
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

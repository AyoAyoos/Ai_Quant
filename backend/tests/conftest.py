from sqlalchemy import text

from app.database import engine


def db_reachable() -> bool:
    """True when the configured Postgres (docker compose up -d db) accepts connections."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
import os

import pytest
from sqlalchemy import text

# Disable background news ingestion for the suite: tests call the refresh
# endpoint explicitly, and a timed worker would hit live feeds mid-run.
os.environ.setdefault("NEWS_AUTO_REFRESH", "false")

from app.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _single_user():
    """Auth was removed: every request runs as the single local dev user.

    Keep the override as a no-op anchor so tests seed rows under the same
    identity the app uses (TEST_USER_ID == DEV_USER_ID).
    """
    from app import auth as auth_module
    from app.main import app

    app.dependency_overrides[auth_module.verify_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.pop(auth_module.verify_user, None)


#: Local dev user id (matches app.auth.DEV_USER_ID). Valid-UUID-shaped so it
#: fits the Postgres UUID primary key on users.id.
TEST_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _test_user():
    from app.auth import AuthenticatedUser

    return AuthenticatedUser(id=TEST_USER_ID, email="dev@local")


TEST_USER = _test_user()


def db_reachable() -> bool:
    """True when the configured Postgres (docker compose up -d db) accepts connections."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _snapshot() -> dict[str, set[tuple]]:
    """Primary keys already present in each table, keyed by table name."""
    existing: dict[str, set[tuple]] = {}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            pk = [col.name for col in table.primary_key.columns]
            if not pk:
                continue
            rows = conn.execute(text(f"SELECT {', '.join(pk)} FROM {table.name}")).fetchall()
            existing[table.name] = {tuple(row) for row in rows}
    return existing


def _delete_rows_added_by_the_test(existing: dict[str, set[tuple]]) -> None:
    """Delete rows the test created, children first, leaving pre-existing data alone."""
    with engine.begin() as conn:
        # Break the strategies <-> backtest_results cycle by nullifying approved_backtest_id first
        try:
            keep_strats = existing.get("strategies", set())
            rows_strats = conn.execute(text("SELECT id FROM strategies")).fetchall()
            to_null = [r[0] for r in rows_strats if tuple(r) not in keep_strats]
            if to_null:
                conn.execute(text("UPDATE strategies SET approved_backtest_id = NULL WHERE id = ANY(:ids)"), {"ids": to_null})
        except Exception:
            pass

        # Define deletion order that respects FKs despite SQLAlchemy cycle warnings
        order = [
            "news_articles",
            "paper_orders",
            "paper_positions",
            "paper_trades",
            "paper_equity_snapshots",
            "paper_deployments",
            "messages",
            "backtest_results",
            "strategies",
            "conversations",
            "users",
        ]
        for table_name in order:
            table = Base.metadata.tables.get(table_name)
            if table is None:
                continue
            pk = [col.name for col in table.primary_key.columns]
            if not pk:
                continue
            keep = existing.get(table_name, set())
            rows = conn.execute(text(f"SELECT {', '.join(pk)} FROM {table_name}")).fetchall()
            for row in rows:
                if tuple(row) in keep:
                    continue
                where = " AND ".join(f"{name} = :{name}" for name in pk)
                conn.execute(
                    text(f"DELETE FROM {table_name} WHERE {where}"),
                    {name: row[idx] for idx, name in enumerate(pk)},
                )


@pytest.fixture()
def db():
    """Ensure the schema exists, then clean up only what the test inserted.

    Tearing down by truncating every table also deleted whatever dev data
    shared the database — that is how the dev strategy got wiped. Rows that
    already existed are kept; anything added during the test goes away.
    """
    if not db_reachable():
        pytest.skip("Postgres not reachable — run `docker compose up -d db` first")
    Base.metadata.create_all(bind=engine)
    before = _snapshot()
    yield
    _delete_rows_added_by_the_test(before)

import pytest
from sqlalchemy import text

from app.database import Base, engine


@pytest.fixture(autouse=True)
def _bypass_supabase_auth():
    """Existing API tests exercise business logic, not auth: stub the
    router-level verify_user dependency so they run without Supabase JWTs.
    Auth itself is covered in test_auth.py against an un-overridden app.

    The stub identity owns every seeded row: seed helpers must create their
    User with id=TEST_USER_ID, otherwise ownership checks 404.
    """
    from app import auth as auth_module
    from app.main import app

    app.dependency_overrides[auth_module.verify_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.pop(auth_module.verify_user, None)


#: Supabase UUID impersonated by the auth stub above. Valid-UUID-shaped so it
#: fits the Postgres UUID primary key on users.id. The hex contains letters
#: on purpose: the SQLite-backed tests store ids through the Postgres UUID
#: type, and an all-digit hex would be coerced to REAL by SQLite affinity.
TEST_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _test_user():
    from app.auth import AuthenticatedUser

    return AuthenticatedUser(id=TEST_USER_ID, email="test@example.com")


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
        for table in reversed(Base.metadata.sorted_tables):
            pk = [col.name for col in table.primary_key.columns]
            if not pk:
                continue
            keep = existing.get(table.name, set())
            rows = conn.execute(text(f"SELECT {', '.join(pk)} FROM {table.name}")).fetchall()
            for row in rows:
                if tuple(row) in keep:
                    continue
                where = " AND ".join(f"{name} = :{name}" for name in pk)
                conn.execute(
                    text(f"DELETE FROM {table.name} WHERE {where}"),
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

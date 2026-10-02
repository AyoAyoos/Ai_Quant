"""Malformed ids must 404 instead of reaching Postgres.

The malformed-id cases 404 before any query runs, and creating a SQLAlchemy
session does not connect, so the first half of this module runs without a
reachable database. The second half needs real rows and self-skips.
"""
import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.ids import MAX_ECHOED_ID
from app.main import app
from app.models import Conversation, Message, Strategy, User
from conftest import db_reachable

# Every endpoint that takes a strategy id, with a minimal valid body where one
# is required.
STRATEGY_ROUTES = [
    ("GET", "/strategies/{sid}", None),
    ("GET", "/strategies/{sid}/deployments", None),
    ("POST", "/strategies/{sid}/approve", None),
    ("POST", "/strategies/{sid}/reject", {"reason": "no edge in the sample"}),
    ("POST", "/strategies/{sid}/deploy", {}),
    ("POST", "/strategies/{sid}/stop", {}),
    ("POST", "/strategies/{sid}/backtest", {}),
]

# Ids that are not UUIDs. An empty string is absent here because a URL path
# segment cannot be empty — Starlette simply fails to match the route — so it is
# covered on POST /chat, where the id travels in the body instead.
MALFORMED_IDS = [
    "abc123",
    "not-a-uuid",
    "x" * 300,  # longer than any UUID
    "'; DROP TABLE strategies; --",
    "7690452c-df31-4879-9326-2674bcf87c52-0",  # valid uuid plus a character
    "7690452cdf31487993262674bcf87c52a",  # unhyphenated, one digit too many
]


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.mark.parametrize("method,template,body", STRATEGY_ROUTES)
@pytest.mark.parametrize("malformed_id", MALFORMED_IDS)
def test_malformed_strategy_id_returns_404(client, method, template, body, malformed_id):
    url = template.format(sid=malformed_id)
    resp = client.request(method, url, json=body)

    assert resp.status_code == 404
    assert resp.json() == {"detail": f"Strategy {malformed_id[:MAX_ECHOED_ID]} not found"}


def test_malformed_id_detail_is_truncated(client):
    resp = client.get(f"/strategies/{'x' * 300}")

    assert resp.status_code == 404
    assert resp.json() == {"detail": f"Strategy {'x' * MAX_ECHOED_ID} not found"}


def test_empty_path_segment_is_404_not_500(client):
    """A URL cannot carry an empty id, but it must still never 500."""
    resp = client.get("/strategies//deployments")

    assert resp.status_code == 404


@pytest.mark.parametrize("malformed_id", MALFORMED_IDS + [""])
def test_chat_malformed_conversation_id_returns_404(client, malformed_id, monkeypatch):
    """A bad conversation_id 404s before the LLM is ever reached."""

    def _never_called(*args, **kwargs):
        raise AssertionError("chat_completion must not run for a malformed id")

    monkeypatch.setattr("app.routers.chat.chat_completion", _never_called)

    resp = client.post(
        "/chat",
        json={"conversation_id": malformed_id, "content": "hello"},
    )

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Conversation not found"}


@pytest.mark.skipif(
    not db_reachable(),
    reason="Postgres not reachable — run `docker compose up -d db` first",
)
class TestAgainstPostgres:
    """Cases that need stored rows to be meaningful."""

    @pytest.fixture()
    def db(self):
        Base.metadata.create_all(bind=engine)
        yield
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())

    def _seed_strategy(self) -> str:
        with SessionLocal() as session:
            user = User(email="test@local")
            session.add(user)
            session.commit()
            session.refresh(user)
            conv = Conversation(user_id=user.id, title="Id validation test")
            session.add(conv)
            session.commit()
            session.refresh(conv)
            strat = Strategy(
                conversation_id=conv.id,
                name="Buy & Hold",
                description="Fixture strategy",
                generated_code="class GeneratedStrategy: pass",
            )
            session.add(strat)
            session.commit()
            session.refresh(strat)
            return strat.id

    def test_valid_but_unknown_uuid_still_returns_404(self, client, db):
        resp = client.get("/strategies/00000000-0000-0000-0000-000000000000")

        assert resp.status_code == 404
        assert resp.json() == {
            "detail": "Strategy 00000000-0000-0000-0000-000000000000 not found"
        }

    @pytest.mark.parametrize(
        "transform",
        [
            str.upper,  # uppercase
            lambda v: v.replace("-", ""),  # unhyphenated
            lambda v: "{%s}" % v,  # brace-wrapped
        ],
        ids=["uppercase", "no-hyphens", "braced"],
    )
    def test_other_uuid_textual_forms_resolve_to_same_strategy(self, client, db, transform):
        strategy_id = self._seed_strategy()

        resp = client.get(f"/strategies/{transform(strategy_id)}")

        assert resp.status_code == 200
        assert resp.json()["strategy_id"] == strategy_id

    def test_chat_malformed_id_creates_no_rows(self, client, db):
        with SessionLocal() as session:
            before = (
                session.query(Conversation).count(),
                session.query(Message).count(),
                session.query(User).count(),
            )

        resp = client.post(
            "/chat",
            json={"conversation_id": "abc123", "content": "hello"},
        )

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Conversation not found"}
        with SessionLocal() as session:
            after = (
                session.query(Conversation).count(),
                session.query(Message).count(),
                session.query(User).count(),
            )
        assert after == before
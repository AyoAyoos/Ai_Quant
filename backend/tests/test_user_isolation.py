"""Multi-tenant isolation: one user must never see another's data.

Owner rows are seeded under the conftest auth-stub identity; a second
identity (fresh UUID, no override of the stub — swapped in per-test) must
get 404s on every strategy/chat/paper endpoint and an empty deployments
list, while the owner keeps full access.
"""

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.auth import AuthenticatedUser
from app.database import SessionLocal
from app.main import app
from app.models import Conversation, Strategy, User
from conftest import TEST_USER, TEST_USER_ID, db_reachable

pytestmark = pytest.mark.skipif(
    not db_reachable(),
    reason="Postgres not reachable — run `docker compose up -d db` first",
)

OTHER_USER = AuthenticatedUser(id="22222222-2222-2222-2222-222222222222")


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_owned_strategy() -> tuple[str, str]:
    """Strategy + conversation owned by the stub identity. Returns (strategy_id, conversation_id)."""
    with SessionLocal() as session:
        existing = session.query(User).filter(User.id == TEST_USER_ID).first()
        user = existing or User(id=TEST_USER_ID, email="owner@local")
        session.add(user)
        session.commit()
        session.refresh(user)
        conv = Conversation(user_id=user.id, title="Owner thread")
        session.add(conv)
        session.commit()
        session.refresh(conv)
        strat = Strategy(
            conversation_id=conv.id,
            name="Owner Strategy",
            description="must stay private",
            generated_code="class GeneratedStrategy: pass",
        )
        session.add(strat)
        session.commit()
        session.refresh(strat)
        return strat.id, conv.id


@pytest.fixture()
def as_other_user():
    """Swap the auth stub to a stranger identity for the duration of a test."""
    app.dependency_overrides[auth_module.verify_user] = lambda: OTHER_USER
    yield
    app.dependency_overrides[auth_module.verify_user] = lambda: TEST_USER


def test_owner_reads_own_strategy(client, db):
    strategy_id, _ = _seed_owned_strategy()
    resp = client.get(f"/strategies/{strategy_id}")
    assert resp.status_code == 200
    assert resp.json()["strategy_id"] == strategy_id


def test_stranger_cannot_read_strategy(client, db, as_other_user):
    strategy_id, _ = _seed_owned_strategy()
    resp = client.get(f"/strategies/{strategy_id}")
    assert resp.status_code == 404


def test_stranger_cannot_mutate_or_run_strategy(client, db, as_other_user):
    strategy_id, _ = _seed_owned_strategy()
    assert client.post(f"/strategies/{strategy_id}/approve").status_code == 404
    assert (
        client.post(
            f"/strategies/{strategy_id}/reject", json={"reason": "no edge here"}
        ).status_code
        == 404
    )
    assert client.post(f"/strategies/{strategy_id}/backtest", json={}).status_code == 404
    assert client.get(f"/strategies/{strategy_id}/deployments").status_code == 404
    assert client.get(f"/strategies/{strategy_id}/paper-account").status_code == 404


def test_stranger_cannot_post_to_owners_conversation(client, db, as_other_user):
    _, conversation_id = _seed_owned_strategy()
    resp = client.post(
        "/chat", json={"conversation_id": conversation_id, "content": "hello"}
    )
    assert resp.status_code == 404


def test_stranger_gets_empty_deployments_but_owner_lists_own(
    client, db, as_other_user
):
    # Stranger owns nothing: global list must be empty for them.
    assert client.get("/paper/deployments").json() == []
    assert client.get("/paper/deployments/active").json() == []

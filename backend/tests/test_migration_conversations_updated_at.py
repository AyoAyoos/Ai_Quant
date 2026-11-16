"""Regression tests for the conversations.updated_at schema migration.

The model has always exposed ``Conversation.updated_at``; the missing piece was
the Alembic column.  These tests exercise both the schema and the persistence
path that previously raised ``UndefinedColumn``.
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.auth import get_or_create_user
from app.database import SessionLocal, engine
from app.main import app
from app.models import Conversation


@pytest.fixture()
def client():
    return TestClient(app)


def test_conversations_table_has_nullable_updated_at_column(db):
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("conversations")}

    assert "updated_at" in columns
    # The SQLAlchemy model does not mark the column NOT NULL.
    assert columns["updated_at"]["nullable"] is True


def test_existing_conversations_are_accessible_and_backfilled(db):
    with engine.connect() as conn:
        before = conn.execute(
            text("SELECT id, updated_at FROM conversations")
        ).mappings().all()

    # The migration must leave every pre-existing conversation readable and
    # give it a concrete timestamp.
    assert all(row["updated_at"] is not None for row in before)
    before_ids = {str(row["id"]) for row in before}

    with SessionLocal() as session:
        user = get_or_create_user(session)
        conversation = Conversation(user_id=user.id, title="Migration regression")
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        conversation_id = str(conversation.id)
        first_updated_at = conversation.updated_at

    assert conversation_id
    assert first_updated_at is not None

    with engine.connect() as conn:
        after = conn.execute(text("SELECT id FROM conversations")).mappings().all()
    after_ids = {str(row["id"]) for row in after}

    assert before_ids.issubset(after_ids)
    assert conversation_id in after_ids


def test_conversation_updated_at_is_populated_and_updates_persist(db):
    with SessionLocal() as session:
        user = get_or_create_user(session)
        conversation = Conversation(user_id=user.id, title="updated_at persistence")
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        conversation_id = str(conversation.id)
        created_updated_at = conversation.updated_at

    assert created_updated_at is not None

    time.sleep(0.02)
    with SessionLocal() as session:
        persisted = session.query(Conversation).filter(Conversation.id == conversation_id).one()
        persisted.title = "updated_at persistence changed"
        session.commit()
        session.refresh(persisted)
        changed_updated_at = persisted.updated_at

    # Re-open a fresh session to prove the row and timestamp were persisted.
    with SessionLocal() as session:
        reloaded = session.query(Conversation).filter(Conversation.id == conversation_id).one()
        assert reloaded.title == "updated_at persistence changed"
        assert reloaded.updated_at is not None
        assert changed_updated_at is not None
        assert reloaded.updated_at >= created_updated_at
        assert reloaded.updated_at >= changed_updated_at


def test_conversation_api_create_and_read_returns_updated_at(client, db):
    created = client.post(
        "/conversations",
        json={"title": "API updated_at regression"},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["id"]
    assert payload["updated_at"]

    fetched = client.get(f"/conversations/{payload['id']}")
    assert fetched.status_code == 200
    detail = fetched.json()
    assert detail["conversation"]["id"] == payload["id"]
    assert detail["conversation"]["updated_at"] == payload["updated_at"]

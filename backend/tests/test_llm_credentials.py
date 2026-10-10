"""Credential handling, identity resolution, and strategy/deployment retrieval.

Covers the two production bugs directly:

* the LLM must never build an ``Authorization: Bearer`` header from an empty
  key — a missing/blank key is a configuration problem (503), not an upstream
  failure (502), and the key value must never appear in any response;
* the single local user must resolve to the owner of the existing rows, so a
  saved strategy (and its deployments) is reachable instead of 404-ing purely
  because auth removal changed the hard-coded user id.

DB-backed tests use the shared ``db`` fixture in ``conftest.py``, which only
removes rows a test inserted and leaves pre-existing data untouched.
"""

import asyncio
import json
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import DEV_USER_ID
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.schemas import StrategyBuilderRequest
from app.services.llm_errors import LLMNotConfiguredError
from app.services.llm_service import chat_completion
from app.services.strategy_builder import generate_structured_strategy

VALID_CODE = '''import backtrader as bt


class GeneratedStrategy(bt.Strategy):
    params = (("rsi_period", 14), ("rsi_oversold", 30), ("rsi_overbought", 70))

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)

    def next(self):
        if not self.position and self.rsi[0] < self.p.rsi_oversold:
            self.buy()
        elif self.position and self.rsi[0] > self.p.rsi_overbought:
            self.sell()
'''


@pytest.fixture()
def client():
    return TestClient(app)


def _spec_dict() -> dict:
    return {
        "market": "NIFTY50",
        "trading_style": "intraday",
        "timeframe": "15m",
        "indicators": [
            {"name": "EMA", "parameters": {"fast": 20, "slow": 50}},
            {"name": "RSI", "parameters": {"period": 14, "oversold": 30, "overbought": 70}},
        ],
        "entry_conditions": ["EMA 20 crosses above EMA 50", "RSI is below 30"],
        "exit_conditions": ["Exit on opposite signal"],
        "risk_management": {
            "stop_loss_percent": 1,
            "take_profit_percent": 2,
            "trailing_stop_percent": 0.5,
            "max_trades_per_day": 3,
        },
    }


def _spec() -> StrategyBuilderRequest:
    return StrategyBuilderRequest(**_spec_dict())


def _mock_post_returning(content: str, capture: dict | None = None):
    """Patch target for ``httpx.AsyncClient.post`` that returns `content`."""

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if capture is not None:
            capture["url"] = url
            capture["headers"] = headers
            capture["payload"] = json

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        return _Resp()

    return fake_post


def _mock_post_raising(exc: Exception):
    async def fake_post(self, *args, **kwargs):
        raise exc

    return fake_post


class TestMissingKeyNeverReachesHTTP:
    @pytest.mark.parametrize("value", ["", "   ", "\t\n ", None])
    def test_builder_blank_key_raises_config_error(self, monkeypatch, value):
        monkeypatch.setattr(settings, "groq_api_key", value)
        calls = {"n": 0}

        async def boom(*args, **kwargs):
            calls["n"] += 1
            raise AssertionError("HTTP must not be attempted without a key")

        monkeypatch.setattr(
            "app.services.strategy_builder.httpx.AsyncClient.post", boom
        )

        with pytest.raises(LLMNotConfiguredError) as excinfo:
            asyncio.run(generate_structured_strategy(_spec()))

        assert "GROQ_API_KEY" in str(excinfo.value)
        assert calls["n"] == 0

    def test_chat_blank_key_raises_config_error(self, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "   ")
        calls = {"n": 0}

        async def boom(*args, **kwargs):
            calls["n"] += 1
            raise AssertionError("HTTP must not be attempted without a key")

        monkeypatch.setattr("app.services.llm_service.httpx.AsyncClient.post", boom)

        with pytest.raises(LLMNotConfiguredError):
            asyncio.run(chat_completion([{"role": "user", "content": "hi"}]))

        assert calls["n"] == 0


class TestHeaderConstruction:
    def test_builder_sends_nonempty_bearer(self, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "test-key-123")
        capture: dict = {}
        body = json.dumps({"name": "N", "description": "D", "code": VALID_CODE})
        monkeypatch.setattr(
            "app.services.strategy_builder.httpx.AsyncClient.post",
            _mock_post_returning(body, capture),
        )

        result = asyncio.run(generate_structured_strategy(_spec()))

        header = capture["headers"]["Authorization"]
        assert header == "Bearer test-key-123"
        # The exact bug: a trailing-space/empty bearer must never be sent.
        assert header.strip() != "Bearer"
        assert result["code"] == VALID_CODE

    def test_whitespace_around_key_is_trimmed(self, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "  test-key-123\n")
        capture: dict = {}
        body = json.dumps({"name": "N", "description": "D", "code": VALID_CODE})
        monkeypatch.setattr(
            "app.services.strategy_builder.httpx.AsyncClient.post",
            _mock_post_returning(body, capture),
        )

        asyncio.run(generate_structured_strategy(_spec()))
        assert capture["headers"]["Authorization"] == "Bearer test-key-123"

    def test_chat_sends_nonempty_bearer(self, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "test-key-123")
        capture: dict = {}
        monkeypatch.setattr(
            "app.services.llm_service.httpx.AsyncClient.post",
            _mock_post_returning("hello", capture),
        )

        reply = asyncio.run(chat_completion([{"role": "user", "content": "hi"}]))

        assert reply == "hello"
        assert capture["headers"]["Authorization"] == "Bearer test-key-123"


class TestNoSecretLeakage:
    def test_service_error_does_not_contain_key(self, monkeypatch):
        secret = "gsk_leak_probe_do_not_log_000"
        monkeypatch.setattr(settings, "groq_api_key", secret)
        monkeypatch.setattr(
            "app.services.strategy_builder.httpx.AsyncClient.post",
            _mock_post_raising(httpx.ConnectError("connection refused")),
        )

        with pytest.raises(httpx.HTTPError) as excinfo:
            asyncio.run(generate_structured_strategy(_spec()))

        assert secret not in str(excinfo.value)

    def test_endpoint_error_does_not_contain_key(self, client, db, monkeypatch):
        secret = "gsk_leak_probe_do_not_log_000"
        monkeypatch.setattr(settings, "groq_api_key", secret)
        monkeypatch.setattr(
            "app.services.strategy_builder.httpx.AsyncClient.post",
            _mock_post_raising(httpx.ConnectError("connection refused")),
        )

        resp = client.post("/strategies/builder", json=_spec_dict())

        assert resp.status_code == 502
        assert secret not in resp.text
        assert "Bearer" not in resp.text

    def test_openapi_schema_does_not_contain_key(self, client, monkeypatch):
        secret = "gsk_leak_probe_do_not_log_000"
        monkeypatch.setattr(settings, "groq_api_key", secret)
        assert secret not in client.get("/openapi.json").text


class TestBuilderEndpointConfigError:
    def test_missing_key_returns_503_actionable(self, client, db, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "")

        resp = client.post("/strategies/builder", json=_spec_dict())

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "GROQ_API_KEY" in detail
        assert "backend/.env" in detail

    def test_mocked_success_still_generates(self, client, db, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "test-dummy-key")
        body = json.dumps({"name": "EMA RSI", "description": "D", "code": VALID_CODE})
        monkeypatch.setattr(
            "app.services.strategy_builder.httpx.AsyncClient.post",
            _mock_post_returning(body),
        )

        resp = client.post("/strategies/builder", json=_spec_dict())

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_id"]
        assert data["name"] == "EMA RSI"
        assert "GeneratedStrategy" in data["generated_code"]


class TestChatEndpointConfigError:
    def test_missing_key_returns_503(self, client, db, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "")
        resp = client.post("/chat", json={"content": "build me a strategy"})
        assert resp.status_code == 503
        assert "GROQ_API_KEY" in resp.json()["detail"]


def _seed_strategy(session, user_id: str, name: str = "Seeded") -> str:
    from app.models import Conversation, Strategy, User

    user = session.query(User).filter(User.id == user_id).first()
    if user is None:
        user = User(id=user_id, email=f"{user_id}@local")
        session.add(user)
        session.commit()

    conversation = Conversation(user_id=user_id, title="seed")
    session.add(conversation)
    session.commit()

    strategy = Strategy(
        conversation_id=conversation.id,
        name=name,
        description="seeded for retrieval tests",
        generated_code=VALID_CODE,
    )
    session.add(strategy)
    session.commit()
    return strategy.id


class TestStrategyRetrieval:
    def test_valid_id_returns_detail(self, client, db):
        session = SessionLocal()
        try:
            strategy_id = _seed_strategy(session, DEV_USER_ID)
        finally:
            session.close()

        resp = client.get(f"/strategies/{strategy_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["strategy_id"] == strategy_id

    def test_unknown_uuid_is_404(self, client, db):
        resp = client.get("/strategies/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_malformed_id_is_404_not_500(self, client, db):
        resp = client.get("/strategies/not-a-uuid")
        assert resp.status_code == 404

    def test_valid_deployments_returns_list(self, client, db):
        session = SessionLocal()
        try:
            strategy_id = _seed_strategy(session, DEV_USER_ID)
        finally:
            session.close()

        resp = client.get(f"/strategies/{strategy_id}/deployments")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_unknown_id_deployments_is_404(self, client, db):
        resp = client.get(
            "/strategies/00000000-0000-0000-0000-000000000000/deployments"
        )
        assert resp.status_code == 404

    def test_other_users_strategy_stays_hidden(self, client, db):
        """Ownership scoping must survive the identity reconciliation."""
        session = SessionLocal()
        try:
            other_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            strategy_id = _seed_strategy(session, other_id)
        finally:
            session.close()

        assert client.get(f"/strategies/{strategy_id}").status_code == 404
        assert (
            client.get(f"/strategies/{strategy_id}/deployments").status_code == 404
        )


class TestLocalUserResolution:
    def test_adopts_existing_user(self, db):
        from app import auth
        from app.models import User

        session = SessionLocal()
        try:
            adopted_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            session.add(
                User(
                    id=adopted_id,
                    email=f"{adopted_id}@local",
                    created_at=datetime(2000, 1, 1),
                )
            )
            session.commit()

            resolved = auth.resolve_local_user(session)
            assert resolved.id == adopted_id
        finally:
            session.close()

    def test_falls_back_on_empty_database(self):
        """With no user rows at all, resolution returns the fixed local id.

        A stub is used so the branch is exercised deterministically regardless
        of what other tests left in the shared database.
        """
        from app import auth

        class _EmptyQuery:
            def order_by(self, *args, **kwargs):
                return self

            def first(self):
                return None

        class _EmptyDB:
            def query(self, *args, **kwargs):
                return _EmptyQuery()

        assert auth.resolve_local_user(_EmptyDB()).id == auth.DEV_USER_ID

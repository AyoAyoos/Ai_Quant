"""Unit tests for app/auth.py — no database required.

Covers the Supabase JWT dependency directly (valid / expired / forged /
unconfigured / missing-sub tokens) and at the HTTP layer through a minimal
FastAPI app carrying the same router-level Depends(verify_user).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app import auth
from app.auth import verify_user
from app.config import settings

SECRET = "test-jwt-secret"


def _token(**overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": "user-uuid-123", "iat": now, "exp": now + timedelta(hours=1)}
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    return SECRET


def test_valid_token_returns_sub(configured):
    assert verify_user(_creds(_token())) == "user-uuid-123"


def test_expired_token_rejected(configured):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(_token(exp=datetime.now(timezone.utc) - timedelta(seconds=1))))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has expired"


def test_wrong_secret_rejected(configured):
    from fastapi import HTTPException

    bad = jwt.encode({"sub": "x"}, "another-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(bad))
    assert exc.value.status_code == 401


def test_missing_sub_rejected(configured):
    from fastapi import HTTPException

    nosub = jwt.encode({"role": "authenticated"}, SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(nosub))
    assert exc.value.status_code == 401


def test_unconfigured_secret_returns_503(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(_token()))
    assert exc.value.status_code == 503


def _mini_app() -> TestClient:
    mini = FastAPI()

    @mini.get("/locked", dependencies=[Depends(verify_user)])
    def locked():
        return {"ok": True}

    return TestClient(mini, raise_server_exceptions=False)


def test_http_no_header_is_rejected(configured):
    # HTTPBearer(auto_error=True): no Authorization header -> 403.
    res = _mini_app().get("/locked")
    assert res.status_code == 403


def test_http_bad_token_is_401(configured):
    res = _mini_app().get("/locked", headers={"Authorization": "Bearer junk"})
    assert res.status_code == 401


def test_http_valid_token_passes(configured):
    res = _mini_app().get("/locked", headers={"Authorization": f"Bearer {_token()}"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}

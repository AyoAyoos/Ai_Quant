"""Unit tests for app/auth.py — no database required.

Covers the Supabase JWT dependency directly (valid / expired / forged /
unconfigured / missing-sub tokens) and at the HTTP layer through a minimal
FastAPI app carrying the same router-level Depends(verify_user).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.auth import verify_user

# Test key pair for HS256 (simulating what JWKS would return)
TEST_SECRET = "test-jwt-secret"


def _token(**overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-uuid-123",
        "email": "user@example.com",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, TEST_SECRET, algorithm="HS256")


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture()
def mock_jwks_client(monkeypatch):
    """Mock the JWKS client to use our test secret."""
    from app import auth
    
    # Create a mock signing key that uses our test secret
    mock_key = MagicMock()
    mock_key.key = TEST_SECRET
    
    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.return_value = mock_key
    
    monkeypatch.setattr(auth, "jwks_client", mock_jwks)
    monkeypatch.setattr(auth, "jwks_url", "https://test.supabase.co/auth/v1/.well-known/jwks.json")
    return mock_jwks


def test_valid_token_returns_identity(mock_jwks_client):
    user = verify_user(_creds(_token()))
    assert user.id == "user-uuid-123"
    assert user.email == "user@example.com"


def test_expired_token_rejected(mock_jwks_client):
    from fastapi import HTTPException

    # Expired well beyond the 10s clock-skew leeway.
    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(_token(exp=datetime.now(timezone.utc) - timedelta(seconds=60))))
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_wrong_secret_rejected(mock_jwks_client):
    from fastapi import HTTPException

    # The mock always returns our test secret, so a token signed with a different
    # secret will fail verification
    bad = jwt.encode({"sub": "x"}, "another-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(bad))
    assert exc.value.status_code == 401


def test_missing_sub_rejected(mock_jwks_client):
    from fastapi import HTTPException

    nosub = jwt.encode({"role": "authenticated"}, TEST_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(nosub))
    assert exc.value.status_code == 401


def test_unconfigured_jwks_returns_503(monkeypatch):
    from fastapi import HTTPException
    from app import auth

    monkeypatch.setattr(auth, "jwks_client", None)
    monkeypatch.setattr(auth, "jwks_url", None)
    
    with pytest.raises(HTTPException) as exc:
        verify_user(_creds(_token()))
    assert exc.value.status_code == 503


def _mini_app() -> TestClient:
    mini = FastAPI()

    @mini.get("/locked", dependencies=[Depends(verify_user)])
    def locked():
        return {"ok": True}

    return TestClient(mini, raise_server_exceptions=False)


def test_http_no_header_is_rejected(mock_jwks_client):
    # Missing Authorization header -> 401 (consistent with invalid tokens).
    res = _mini_app().get("/locked")
    assert res.status_code == 401
    assert res.json()["detail"] == "Missing authentication token"


def test_http_bad_token_is_401(mock_jwks_client):
    res = _mini_app().get("/locked", headers={"Authorization": "Bearer junk"})
    assert res.status_code == 401


def test_http_valid_token_passes(mock_jwks_client):
    res = _mini_app().get("/locked", headers={"Authorization": f"Bearer {_token()}"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}
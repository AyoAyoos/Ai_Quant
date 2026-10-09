"""Supabase JWT verification for protected routes.

The frontend attaches its session token as `Authorization: Bearer <jwt>`
(see frontend/src/lib/api.js); this dependency decodes it using Supabase's
public JWKS (ES256) and returns the caller's identity. Missing, expired, or
forged tokens are rejected with a 401 before the handler runs.

Multi-tenant rule: every router MUST scope its database reads/writes to
`user.id` (via get_or_create_user). No endpoint may fall back to a shared
dev user or return rows owned by another user.
"""

import logging
import os
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# auto_error=False so a missing header becomes our own 401 (consistent with
# invalid/expired tokens) instead of Starlette's default 403 shape.
security = HTTPBearer(auto_error=False)

# Supabase JWKS endpoint for ES256 public keys
SUPABASE_URL = os.getenv("SUPABASE_URL") or getattr(settings, "supabase_url", None)
jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None
jwks_client = PyJWKClient(jwks_url) if jwks_url else None


@dataclass(frozen=True)
class AuthenticatedUser:
    """Identity extracted from a verified Supabase access token."""

    id: str
    email: str | None = None


def verify_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthenticatedUser:
    """Decode a Supabase access token, returning the caller's identity.

    Raises:
        HTTPException(503): auth is not configured (no SUPABASE_URL).
        HTTPException(401): token missing, expired, or invalid.
    """
    if not jwks_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the server (missing SUPABASE_URL)",
        )
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    token = credentials.credentials
    try:
        # Dynamically grab the public key that matches the token's signature
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode using the public key and ES256 algorithm
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        logger.info("auth rejected: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from None
    except jwt.PyJWTError as exc:
        logger.warning("auth rejected: invalid token (%s): %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(exc)}",
        ) from None
    user_id = payload.get("sub")
    if not user_id:
        logger.warning("auth rejected: token missing sub claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )
    return AuthenticatedUser(id=user_id, email=payload.get("email"))


def get_or_create_user(db: Session, user: AuthenticatedUser):
    """Row for this Supabase identity, creating it on first sight.

    The Supabase UUID is reused as the primary key so ownership checks are a
    straight equality match — no mapping table, no shared dev user.
    """
    from app.models import User

    row = db.query(User).filter(User.id == user.id).first()
    if row is not None:
        return row
    row = User(id=user.id, email=user.email or f"{user.id}@supabase.local")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

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
from fastapi import Depends, HTTPException, status, Security
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
    credentials: HTTPAuthorizationCredentials = Security(security),
):
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
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
        
    try:
        # Dynamically grab the public key that matches the token's signature
        signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials)
        
        # Decode using the public key and ES256 algorithm
        payload = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["ES256", "HS256"], # Accepts both new and old tokens
            options={"verify_aud": False} 
        )
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("auth rejected: token missing sub claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
        return AuthenticatedUser(id=user_id, email=payload.get("email"))
        
    except jwt.ExpiredSignatureError:
        logger.info("auth rejected: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
        ) from None
    except Exception as e:
        logger.warning("auth rejected: invalid token (%s): %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        ) from None


def get_or_create_user(db: Session, user: AuthenticatedUser | dict):
    """Row for this Supabase identity, creating it on first sight.

    The Supabase UUID is reused as the primary key so ownership checks are a
    straight equality match — no mapping table, no shared dev user.
    """
    from app.models import User

    if isinstance(user, AuthenticatedUser):
        user_id = user.id
        email = user.email
    else:
        user_id = user.get("sub")
        if not user_id:
            raise ValueError("Token missing 'sub' claim")
        email = user.get("email")
    
    row = db.query(User).filter(User.id == user_id).first()
    if row is not None:
        return row
    row = User(id=user_id, email=email or f"{user_id}@supabase.local")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

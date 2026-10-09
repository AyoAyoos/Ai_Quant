"""Supabase JWT verification for protected routes.

The frontend attaches its session token as `Authorization: Bearer <jwt>`
(see frontend/src/lib/api.js); this dependency decodes it with the project's
JWT secret and returns the caller's identity. Missing, expired, or forged
tokens are rejected with a 401 before the handler runs.

Multi-tenant rule: every router MUST scope its database reads/writes to
`user.id` (via get_or_create_user). No endpoint may fall back to a shared
dev user or return rows owned by another user.
"""

import logging
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# auto_error=False so a missing header becomes our own 401 (consistent with
# invalid/expired tokens) instead of Starlette's default 403 shape.
security = HTTPBearer(auto_error=False)


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
        HTTPException(503): auth is not configured (no SUPABASE_JWT_SECRET).
        HTTPException(401): token missing, expired, or invalid.
    """
    secret = settings.supabase_jwt_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the server",
        )
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    token = credentials.credentials
    try:
        # Supabase signs JWTs with HS256; `aud` varies by token type, so it
        # is not verified here (same as the Supabase docs' backend examples).
        # leeway absorbs small clock skew between Supabase and this host.
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
            leeway=10,
        )
    except jwt.ExpiredSignatureError:
        logger.info("auth rejected: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from None
    except jwt.InvalidTokenError as exc:
        logger.warning("auth rejected: invalid token (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
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

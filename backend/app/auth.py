"""Supabase JWT verification for protected routes.

The frontend attaches its session token as `Authorization: Bearer <jwt>`
(see frontend/src/lib/api.js); this dependency decodes it with the project's
JWT secret and returns the user's Supabase UUID (`sub`). Missing, expired,
or forged tokens are rejected with a 401 before the handler runs.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

security = HTTPBearer(auto_error=True)


def verify_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Decode a Supabase access token, returning the user's UUID.

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
    token = credentials.credentials
    try:
        # Supabase signs JWTs with HS256; `aud` varies by token type, so it
        # is not verified here (same as the Supabase docs' backend examples).
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from None
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )
    return user_id

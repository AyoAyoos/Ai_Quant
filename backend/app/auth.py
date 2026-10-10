"""Single-user identity for protected routes (auth removed).

The app no longer has login providers, JWTs, or per-user isolation.
Every request runs as the same local dev user so all routers keep working
without an Authorization header.
"""

from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db

DEV_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEV_EMAIL = "dev@local"


@dataclass(frozen=True)
class AuthenticatedUser:
    """Fixed local identity (kept as a type so router signatures stay valid)."""

    id: str = DEV_USER_ID
    email: str | None = DEV_EMAIL


DEV_USER = AuthenticatedUser(id=DEV_USER_ID, email=DEV_EMAIL)


def resolve_local_user(db: Session) -> AuthenticatedUser:
    """The single local identity every request runs as.

    Auth was removed, so no token identifies the caller. Rows may already
    exist from before removal — created under a former login identity — and
    they are owned by *that* id, not by ``DEV_USER_ID``. Reusing the existing
    row keeps saved strategies, deployments, and conversations reachable
    instead of 404-ing on data the local user actually owns. Only when no user
    exists yet (a fresh database) does it fall back to ``DEV_USER_ID``, which
    ``get_or_create_user`` then creates.
    """
    from app.models import User

    existing = (
        db.query(User)
        .order_by(User.created_at.asc(), User.id.asc())
        .first()
    )
    if existing is not None:
        return AuthenticatedUser(id=str(existing.id), email=existing.email)
    return DEV_USER


def verify_user(db: Session = Depends(get_db)) -> AuthenticatedUser:
    """Dependency returning the single local user — never raises."""
    return resolve_local_user(db)


def get_or_create_user(db: Session, user: AuthenticatedUser | dict | None = None):
    """Row for the single local user, creating it on first sight."""
    from app.models import User

    if isinstance(user, AuthenticatedUser):
        user_id = user.id
        email = user.email
    elif isinstance(user, dict):
        user_id = user.get("sub") or user.get("id") or DEV_USER_ID
        email = user.get("email") or DEV_EMAIL
    else:
        user_id = DEV_USER_ID
        email = DEV_EMAIL

    row = db.query(User).filter(User.id == user_id).first()
    if row is not None:
        return row
    row = User(id=user_id, email=email or f"{user_id}@local")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

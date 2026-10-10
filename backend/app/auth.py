"""Single-user identity for protected routes (auth removed).

The app no longer has login providers, JWTs, or per-user isolation.
Every request runs as the same local dev user so all routers keep working
without an Authorization header.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

DEV_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEV_EMAIL = "dev@local"


@dataclass(frozen=True)
class AuthenticatedUser:
    """Fixed local identity (kept as a type so router signatures stay valid)."""

    id: str = DEV_USER_ID
    email: str | None = DEV_EMAIL


DEV_USER = AuthenticatedUser(id=DEV_USER_ID, email=DEV_EMAIL)


def verify_user() -> AuthenticatedUser:
    """Dependency returning the single local user — never raises."""
    return DEV_USER


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

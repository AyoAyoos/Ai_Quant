"""Auth-adjacent endpoints: passive notifications for signed-in users."""

import smtplib

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import AuthenticatedUser, verify_user
from app.services.welcome_email import MailerNotConfigured, send_welcome_email

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(verify_user)],
)


class WelcomeEmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(default="", max_length=120)


class WelcomeEmailOut(BaseModel):
    sent: bool
    email: str


@router.post("/welcome-email", response_model=WelcomeEmailOut)
def welcome_email(payload: WelcomeEmailIn, user: AuthenticatedUser = Depends(verify_user)):
    """Send the new-account greeting. Fire-and-forget from the client's
    perspective: SMTP failures surface as 502 (mailer reachable but failed),
    never as auth errors. 503 while SMTP credentials are unconfigured."""
    address = payload.email.strip()
    if "@" not in address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid email address.",
        )
    try:
        send_welcome_email(address, payload.name)
    except MailerNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Welcome email could not be delivered: {exc}",
        ) from exc
    return WelcomeEmailOut(sent=True, email=address)

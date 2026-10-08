"""Passive welcome email sent right after Supabase sign-up.

No confirmation links, no tracking pixels — a single styled greeting.
Delivery is plain stdlib smtplib against Gmail SMTP + an App Password
(see Settings smtp_*); nothing to pip-install.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

SUBJECT = "Welcome to QuantNiti"


def render_welcome_email(name: str) -> str:
    """Branded HTML greeting. `name` is user-supplied — escape it."""
    import html as _html

    safe_name = _html.escape((name or "").strip() or "Trader")
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f9f8fc;font-family:'Segoe UI',Arial,sans-serif;">
  <div style="max-width:560px;margin:0 auto;padding:32px 24px;">
    <div style="background:linear-gradient(135deg,#403d88 0%,#8b639b 55%,#f8b2b2 100%);border-radius:16px 16px 0 0;padding:36px 32px;text-align:center;">
      <div style="font-size:28px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">QuantNiti</div>
      <div style="margin-top:6px;font-size:13px;letter-spacing:2px;text-transform:uppercase;color:#f8b2b2;">AI Strategy Engine</div>
    </div>
    <div style="background:#ffffff;border-radius:0 0 16px 16px;padding:32px;box-shadow:0 4px 24px rgba(64,61,136,0.10);">
      <h1 style="margin:0 0 8px;font-size:22px;color:#1e1636;">Welcome, {safe_name}!</h1>
      <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#4a4560;">
        You are now part of the QuantNiti system. Turn your trading ideas into
        data-driven strategies with the power of AI — backtest, analyse,
        and paper trade, all in one place.
      </p>
      <div style="margin:24px 0;padding:16px 20px;background:#f9f8fc;border-left:4px solid #8b639b;border-radius:0 8px 8px 0;">
        <div style="font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#8b639b;font-weight:700;">What you can do next</div>
        <ul style="margin:8px 0 0;padding-left:20px;font-size:14px;line-height:1.8;color:#1e1636;">
          <li>Describe a strategy in plain English in the Studio</li>
          <li>Backtest it on two years of real NIFTY 50 data</li>
          <li>Pass the approval gate into paper trading</li>
        </ul>
      </div>
      <p style="margin:0;font-size:14px;line-height:1.6;color:#4a4560;">
        Happy researching,<br>
        <strong style="color:#403d88;">The QuantNiti Team</strong>
      </p>
    </div>
    <p style="margin:16px 0 0;text-align:center;font-size:12px;color:#8b639b;">
      Educational prototype · Paper trading only · No guaranteed returns
    </p>
  </div>
</body>
</html>"""


class MailerNotConfigured(RuntimeError):
    """SMTP credentials are missing — mailing is disabled."""


def send_welcome_email(to_email: str, name: str = "") -> None:
    """Send the welcome greeting. Raises MailerNotConfigured when SMTP
    credentials are absent; smtplib errors propagate to the caller."""
    if not settings.smtp_user or not settings.smtp_password:
        raise MailerNotConfigured(
            "Outbound mail is not configured (SMTP_USER / SMTP_PASSWORD)"
        )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(render_welcome_email(name), "html", "utf-8"))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)

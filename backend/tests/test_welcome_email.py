"""Tests for the passive welcome email — no database, no network.

smtplib.SMTP is stubbed; the endpoint is exercised over HTTP through the
real router with verify_user overridden (same pattern as conftest).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.config import settings
from app.routers.auth import router
from app.services import welcome_email as mailer


class FakeSMTP:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


@pytest.fixture()
def smtp_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "bot@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", "app-password")
    monkeypatch.setattr(settings, "smtp_from", "QuantNiti <bot@gmail.com>")
    FakeSMTP.instances.clear()
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)


def _client() -> TestClient:
    mini = FastAPI()
    mini.dependency_overrides[auth_module.verify_user] = lambda: "user-uuid-1"
    mini.include_router(router)
    return TestClient(mini, raise_server_exceptions=False)


def test_template_greets_by_name_and_has_no_links():
    html = mailer.render_welcome_email("Aarav")
    assert "Welcome, Aarav!" in html
    assert "QuantNiti" in html
    assert "<a " not in html
    assert "confirm" not in html.lower()


def test_template_escapes_user_input():
    html = mailer.render_welcome_email('<script>alert("x")</script>')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_send_uses_configured_smtp(smtp_configured):
    mailer.send_welcome_email("new@example.com", "Aarav")
    server = FakeSMTP.instances[-1]
    assert server.login_args == ("bot@gmail.com", "app-password")
    (msg,) = server.sent
    assert msg["To"] == "new@example.com"
    assert msg["From"] == "QuantNiti <bot@gmail.com>"
    assert msg["Subject"] == mailer.SUBJECT


def test_send_without_credentials_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    with pytest.raises(mailer.MailerNotConfigured):
        mailer.send_welcome_email("new@example.com")


def test_endpoint_sends_email(smtp_configured):
    res = _client().post(
        "/auth/welcome-email",
        json={"email": "new@example.com", "name": "Aarav"},
    )
    assert res.status_code == 200
    assert res.json() == {"sent": True, "email": "new@example.com"}
    assert len(FakeSMTP.instances) == 1


def test_endpoint_rejects_bad_email(smtp_configured):
    res = _client().post("/auth/welcome-email", json={"email": "not-an-email"})
    assert res.status_code == 422


def test_endpoint_503_when_mailer_disabled(monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    res = _client().post("/auth/welcome-email", json={"email": "new@example.com"})
    assert res.status_code == 503


def test_endpoint_502_on_smtp_failure(smtp_configured, monkeypatch):
    import smtplib as _smtplib

    class BoomSMTP(FakeSMTP):
        def send_message(self, msg):
            raise _smtplib.SMTPException("relay refused")

    monkeypatch.setattr(mailer.smtplib, "SMTP", BoomSMTP)
    res = _client().post("/auth/welcome-email", json={"email": "new@example.com"})
    assert res.status_code == 502


def test_endpoint_requires_auth():
    mini = FastAPI()
    mini.include_router(router)
    res = TestClient(mini, raise_server_exceptions=False).post(
        "/auth/welcome-email", json={"email": "new@example.com"}
    )
    assert res.status_code == 401

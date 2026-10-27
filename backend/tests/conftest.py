import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def open_signup(monkeypatch):
    """Most tests create accounts directly; tests of invitation-only sign-up switch this off."""
    monkeypatch.setattr(settings, "open_signup", True)


@pytest.fixture(autouse=True)
def admin_emails(monkeypatch):
    """Emails to site admins, as (to, subject, body); tests that check them read this list."""
    from app import notify
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


@pytest.fixture(autouse=True)
def polls_on(monkeypatch):
    """Polls run on the development site only; tests of that switch turn it off."""
    monkeypatch.setattr(settings, "polls_enabled", True)

import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def open_signup(monkeypatch):
    """Most tests create accounts directly; tests of invitation-only sign-up switch this off."""
    monkeypatch.setattr(settings, "open_signup", True)

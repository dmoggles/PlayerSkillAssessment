"""Invitations, the way in while sign-up is closed.

A team invitation (purpose "invite") lets one email address join one team as a coach. A site invitation (purpose
"signup") lets a new club's first coach create an account, then their own team; only site admins send those. Both
are AuthToken rows, so links are stored as hashes and expire like every other emailed link.
"""
import logging
from datetime import timedelta
from collections.abc import Callable
from sqlalchemy.orm import Session as DbSession
from .auth import digest, fresh_token
from .models import AuthToken, utcnow

log = logging.getLogger(__name__)

KINDS = ("invite", "signup")
TEAM_INVITE_DAYS = 7
SITE_INVITE_DAYS = 14


def issue(db: DbSession, email: str, kind: str, days: int, team_id: int | None = None) -> tuple[str, AuthToken]:
    token = fresh_token()
    row = AuthToken(email=email, purpose=kind, team_id=team_id, token_hash=digest(token), expires_at=utcnow() + timedelta(days=days))
    db.add(row)
    db.flush()
    return token, row


def find(db: DbSession, token: str) -> AuthToken | None:
    """The unexpired invitation this link carries, or None."""
    return db.query(AuthToken).filter(AuthToken.token_hash == digest(token), AuthToken.purpose.in_(KINDS),
                                      AuthToken.expires_at > utcnow()).first()


def pending_for(db: DbSession, email: str) -> bool:
    return db.query(AuthToken).filter(AuthToken.email == email, AuthToken.purpose.in_(KINDS), AuthToken.expires_at > utcnow()).first() is not None


def deliver(send: Callable[[str, str, str], None], to: str, subject: str, body: str) -> bool:
    """Email an invitation. A failure doesn't cancel it: the person inviting gets the link to send themselves."""
    try:
        send(to, subject, body)
        return True
    except Exception:
        log.exception("Invitation email to %s could not be sent", to)
        return False


def outcome(email: str, emailed: bool) -> str:
    if emailed:
        return f"Invitation emailed to {email}. You can also copy the link and send it yourself."
    return f"The email to {email} couldn't be sent, but the invitation is ready: copy the link and send it yourself."

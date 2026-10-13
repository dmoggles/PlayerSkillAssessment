"""Periodic cleanup of expired authentication data, abandoned sign-ups and the activity logs of deleted teams.

Runs inside the API process (see main.py) and can be run by hand with `python -m app.maintenance`.
Self-assessment links are kept after expiry so the squad board can show them as expired.
"""
import asyncio
import logging
from datetime import timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession
from .config import settings
from .database import SessionLocal
from .models import AuditEvent, AuthToken, LoginAttempt, Membership, Session, Team, User, utcnow

UNVERIFIED_ACCOUNT_DAYS = 30
DELETED_TEAM_LOG_DAYS = 90

log = logging.getLogger(__name__)


def purge_expired(db: DbSession) -> dict[str, int]:
    now = utcnow()
    counts = {
        "sessions": db.query(Session).filter(Session.expires_at <= now).delete(synchronize_session=False),
        "auth_tokens": db.query(AuthToken).filter(AuthToken.expires_at <= now).delete(synchronize_session=False),
        # Throttle windows last 15 minutes; a day-old row no longer affects anything.
        "login_attempts": db.query(LoginAttempt).filter(LoginAttempt.window_started <= now - timedelta(days=1)).delete(synchronize_session=False),
    }
    # Sign-ups never verified: the link expired long ago, and the account was never used.
    abandoned = db.query(User.id).filter(User.verified_at.is_(None), User.created_at <= now - timedelta(days=UNVERIFIED_ACCOUNT_DAYS),
                                         ~User.id.in_(db.query(Membership.user_id)))
    db.query(AuthToken).filter(AuthToken.user_id.in_(abandoned)).delete(synchronize_session=False)
    counts["unverified_accounts"] = db.query(User).filter(User.id.in_(abandoned)).delete(synchronize_session=False)
    # A deleted team's activity log (it names coaches) is kept for a while after the deletion, then removed.
    stale_teams = (db.query(AuditEvent.team_id).filter(~AuditEvent.team_id.in_(db.query(Team.id)))
                   .group_by(AuditEvent.team_id).having(func.max(AuditEvent.created_at) <= now - timedelta(days=DELETED_TEAM_LOG_DAYS)))
    counts["deleted_team_log_events"] = db.query(AuditEvent).filter(AuditEvent.team_id.in_(stale_teams)).delete(synchronize_session=False)
    db.commit()
    return counts


def run_cleanup() -> dict[str, int]:
    with SessionLocal() as db:
        return purge_expired(db)


async def cleanup_loop():
    while True:
        try:
            counts = await asyncio.to_thread(run_cleanup)
            log.info("Removed expired records: %s", counts)
        except Exception:
            log.exception("Cleanup of expired records failed")
        await asyncio.sleep(settings.cleanup_interval_hours * 3600)


if __name__ == "__main__":
    print(run_cleanup())

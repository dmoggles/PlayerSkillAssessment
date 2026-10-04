"""Periodic cleanup of expired authentication data.

Runs inside the API process (see main.py) and can be run by hand with `python -m app.maintenance`.
Self-assessment links are kept after expiry so the squad board can show them as expired.
"""
import asyncio
import logging
from datetime import timedelta
from sqlalchemy.orm import Session as DbSession
from .config import settings
from .database import SessionLocal
from .models import AuthToken, LoginAttempt, Session, utcnow

log = logging.getLogger(__name__)


def purge_expired(db: DbSession) -> dict[str, int]:
    now = utcnow()
    counts = {
        "sessions": db.query(Session).filter(Session.expires_at <= now).delete(synchronize_session=False),
        "auth_tokens": db.query(AuthToken).filter(AuthToken.expires_at <= now).delete(synchronize_session=False),
        # Throttle windows last 15 minutes; a day-old row no longer affects anything.
        "login_attempts": db.query(LoginAttempt).filter(LoginAttempt.window_started <= now - timedelta(days=1)).delete(synchronize_session=False),
    }
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

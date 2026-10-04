from sqlalchemy.orm import Session as DbSession
from .models import AuditEvent, User


def record(db: DbSession, team_id: int, actor: User, action: str, target_email: str | None = None, **details):
    """Add an audit event to the current transaction; it is saved with the change it describes."""
    db.add(AuditEvent(team_id=team_id, actor_email=actor.email, action=action,
                      target_email=target_email, details=details or None))

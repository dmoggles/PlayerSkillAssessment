"""Emails telling site admins that something needs them, or that something they approved has happened."""
import logging
from sqlalchemy.orm import Session as DbSession
from .auth import send_email
from .config import settings
from .models import AccessRequest, AuthToken, Membership, User, utcnow

log = logging.getLogger(__name__)


def notify_admins(db: DbSession, subject: str, body: str):
    """Best effort: what the email is about is saved either way, and admins see it in Settings."""
    for admin in db.query(User).filter_by(is_admin=True):
        try:
            send_email(admin.email, subject, f"{body}\n\nSite admin, in Settings:\n{settings.public_base_url}/app/settings")
        except Exception:
            log.exception("Couldn't email %s: %s", admin.email, subject)


def access_requested(db: DbSession, request: AccessRequest):
    lines = [f"{request.name} ({request.email}) asked for access to {settings.app_name} for {request.club}."]
    if request.teams:
        lines.append(f"Teams: {request.teams}")
    if request.message:
        lines.append(f"Their message:\n{request.message}")
    notify_admins(db, f"Access request from {request.club}", "\n\n".join(lines))


def joined_by_team_invite(db: DbSession, user: User) -> bool:
    """A coach a team invited: their team's owner let them in, not a site admin."""
    if db.query(Membership).filter_by(user_id=user.id).first():
        return True
    return db.query(AuthToken).filter(AuthToken.email == user.email, AuthToken.purpose == "invite",
                                      AuthToken.expires_at > utcnow()).first() is not None


def signed_up(db: DbSession, user: User):
    """A new account is ready to use, from a site invitation or open sign-up."""
    request = (db.query(AccessRequest).filter_by(email=user.email).order_by(AccessRequest.created_at.desc()).first())
    who = f"{request.name} ({user.email}) from {request.club}" if request else user.email
    notify_admins(db, f"New {settings.app_name} account: {user.email}",
                  f"{who} has created their {settings.app_name} account. They can now set up their team.")


def video_suggested(db: DbSession, suggestion, drill, user: User):
    lines = [f"{user.email} suggested a video for {drill.title}: {suggestion.title or suggestion.url}", suggestion.url]
    if suggestion.note:
        lines.append(f"Their note:\n{suggestion.note}")
    notify_admins(db, f"Video to review for {drill.title}", "\n\n".join(lines))


def drill_submitted(db: DbSession, submission, drill, team, user: User):
    lines = [f"{user.email} from {team.name} submitted their drill {drill.title} to the shared library."]
    if submission.note:
        lines.append(f"Their note:\n{submission.note}")
    notify_admins(db, f"Drill to review: {drill.title}", "\n\n".join(lines))

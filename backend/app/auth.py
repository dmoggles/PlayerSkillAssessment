import hashlib
import secrets
import smtplib
from datetime import timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from fastapi import Depends, HTTPException, Request
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy.orm import Session as DbSession
from .config import settings
from .database import get_db
from .models import AuthToken, Membership, Session, User, utcnow


hasher = PasswordHasher()
COOKIE_NAME = "assessment_session"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def fresh_token() -> str:
    return secrets.token_urlsafe(32)


def send_email(to: str, subject: str, body: str):
    message = EmailMessage()
    message["From"] = formataddr((settings.app_name, settings.smtp_from))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(f"{body}\n\n{settings.app_name}: individual development plans for grassroots football\n"
                        "If you weren't expecting this email, you can ignore it.")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_username:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def issue_auth_token(db: DbSession, email: str, purpose: str, user_id: int | None = None, team_id: int | None = None):
    token = fresh_token()
    row = AuthToken(email=email, purpose=purpose, user_id=user_id, team_id=team_id,
                    token_hash=digest(token), expires_at=utcnow() + timedelta(hours=24))
    db.add(row)
    return token


def consume_auth_token(db: DbSession, token: str, purpose: str) -> AuthToken:
    row = db.query(AuthToken).filter_by(token_hash=digest(token), purpose=purpose).with_for_update().first()
    if not row or row.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(400, "Invalid or expired link")
    db.delete(row)
    return row


def get_session(request: Request, db: DbSession = Depends(get_db)) -> tuple[User, Session]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Sign in required")
    session = db.query(Session).filter_by(token_hash=digest(raw)).first()
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(401, "Session expired")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-csrf-token") != session.csrf_token:
        raise HTTPException(403, "Invalid CSRF token")
    user = db.get(User, session.user_id)
    if not user or not user.verified_at:
        raise HTTPException(401, "Verified account required")
    return user, session


def current_user(identity: tuple[User, Session] = Depends(get_session)) -> User:
    return identity[0]


def require_member(team_id: int, db: DbSession, user: User, owner: bool = False) -> Membership:
    member = db.query(Membership).filter_by(team_id=team_id, user_id=user.id).first()
    if not member or (owner and member.role != "owner"):
        raise HTTPException(404, "Team not found")
    return member


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False

"""Site admin: invitations for a new club's first coach (who then creates their own team)."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session as DbSession
from .. import invites
from ..auth import current_user, send_email
from ..config import settings
from ..database import get_db
from ..models import AuthToken, User, utcnow
from .accounts import delivery_message

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Only site admins can do this")
    return user


class SiteInviteBody(BaseModel):
    email: EmailStr


class SiteInvite(BaseModel):
    id: int
    email: str
    expires_at: datetime


def site_invite_email(token: str) -> tuple[str, str]:
    return (f"You're invited to {settings.app_name}",
            f"You've been invited to {settings.app_name}, for assessing your players and building their individual development plans.\n\n"
            f"Create your account with this link, then set up your team:\n{settings.public_base_url}/invite/{token}\n\n"
            f"The link works for {invites.SITE_INVITE_DAYS} days.")


@router.get("/invites", response_model=list[SiteInvite])
def list_site_invites(db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    return db.query(AuthToken).filter(AuthToken.purpose == "signup", AuthToken.expires_at > utcnow()).order_by(AuthToken.expires_at.desc()).all()


@router.post("/invites")
def send_site_invite(body: SiteInviteBody, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    email = body.email.strip().casefold()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "That email address already has an account")
    db.query(AuthToken).filter_by(email=email, purpose="signup").delete(synchronize_session=False)
    token, row = invites.issue(db, email, "signup", invites.SITE_INVITE_DAYS)
    try:
        send_email(email, *site_invite_email(token))
    except Exception:
        db.rollback()
        raise HTTPException(503, "Email delivery unavailable")
    db.commit()
    return {"id": row.id, "email": email, "expires_at": row.expires_at, "message": delivery_message(f"Invitation sent to {email}.")}


@router.delete("/invites/{invite_id}")
def cancel_site_invite(invite_id: int, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    row = db.get(AuthToken, invite_id)
    if not row or row.purpose != "signup":
        raise HTTPException(404, "Invitation not found")
    db.delete(row)
    db.commit()
    return {"message": f"Invitation for {row.email} cancelled."}

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as DbSession
from .. import invites
from ..audit import record
from ..auth import COOKIE_NAME, consume_auth_token, current_user, digest, fresh_token, get_session, hasher, issue_auth_token, send_email, verify_password
from ..config import settings
from ..database import get_db
from ..models import AuthToken, LoginAttempt, Membership, Session, Team, User, utcnow


router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)


class Registration(Credentials):
    # The invitation link the account is created from, if any.
    invite: str | None = None


class EmailOnly(BaseModel):
    email: EmailStr


class TokenOnly(BaseModel):
    token: str


class ResetBody(TokenOnly):
    password: str = Field(min_length=12, max_length=200)


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


def normalized(email: str) -> str:
    return email.strip().casefold()


def delivery_message(action: str) -> str:
    if settings.smtp_host == "mailpit":
        return f"{action} In local development, open the test inbox at http://localhost:8025 on the app host. It is not sent to your personal inbox."
    return action


def throttle(db: DbSession, request: Request, action: str, key: str, limit: int):
    address = request.client.host if request.client else "unknown"
    hashed = digest(f"{action}:{address}:{key}")
    row = db.get(LoginAttempt, hashed)
    now = utcnow()
    if not row:
        row = LoginAttempt(key=hashed, failures=0, window_started=now)
        db.add(row)
    elif now - row.window_started.replace(tzinfo=now.tzinfo) > timedelta(minutes=15):
        row.failures = 0
        row.window_started = now
    if row.failures >= limit:
        raise HTTPException(429, "Try again later")
    row.failures += 1
    db.commit()
    return row


@router.post("/register", status_code=201)
def register(body: Registration, request: Request, db: DbSession = Depends(get_db)):
    email = normalized(body.email)
    throttle(db, request, "register", email, 5)
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "Account already exists")
    invite = invites.find(db, body.invite) if body.invite else None
    if body.invite and (not invite or invite.email != email):
        raise HTTPException(400, "This invitation is invalid, has expired, or is for another email address.")
    if not invite and not settings.open_signup and not invites.pending_for(db, email):
        raise HTTPException(403, f"{settings.app_name} is invitation-only for now. Ask a coach at your club to invite you.")
    # Opening the invitation link proves the address, so an account made from it needs no separate verification.
    user = User(email=email, password_hash=hasher.hash(body.password), verified_at=utcnow() if invite else None)
    db.add(user)
    db.flush()
    db.query(AuthToken).filter_by(email=email, purpose="signup").delete(synchronize_session=False)
    if invite:
        if invite.purpose == "invite":
            team_id = invite.team_id
            db.delete(invite)
            if db.get(Team, team_id):
                db.add(Membership(team_id=team_id, user_id=user.id, role="coach"))
                record(db, team_id, user, "invite_accepted")
        db.commit()
        return {"message": "Account created.", "verified": True}
    token = issue_auth_token(db, email, "verify", user.id)
    try:
        send_email(email, f"Verify your {settings.app_name} account", f"Open this link to verify your {settings.app_name} account:\n{settings.public_base_url}/verify/{token}")
    except Exception:
        db.rollback()
        raise HTTPException(503, "Email delivery unavailable")
    db.commit()
    return {"message": delivery_message("Check your email to verify your account.")}


@router.post("/resend-verification")
def resend_verification(body: EmailOnly, request: Request, db: DbSession = Depends(get_db)):
    email = normalized(body.email)
    throttle(db, request, "verify", email, 5)
    user = db.query(User).filter_by(email=email).first()
    if user and not user.verified_at:
        db.query(AuthToken).filter_by(user_id=user.id, purpose="verify").delete(synchronize_session=False)
        token = issue_auth_token(db, email, "verify", user.id)
        try:
            send_email(email, f"Verify your {settings.app_name} account", f"Open this link to verify your {settings.app_name} account:\n{settings.public_base_url}/verify/{token}")
        except Exception:
            db.rollback()
            raise HTTPException(503, "Email delivery unavailable")
        db.commit()
    return {"message": delivery_message("If the account needs verification, a new link has been sent.")}


@router.post("/verify")
def verify(body: TokenOnly, db: DbSession = Depends(get_db)):
    token = consume_auth_token(db, body.token, "verify")
    user = db.get(User, token.user_id)
    if not user:
        raise HTTPException(400, "Invalid link")
    user.verified_at = utcnow()
    db.commit()
    return {"message": "Account verified"}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: DbSession = Depends(get_db)):
    email = normalized(body.email)
    attempt = throttle(db, request, "login", email, 10)
    user = db.query(User).filter_by(email=email).first()
    if not user or not verify_password(body.password, user.password_hash) or not user.verified_at:
        raise HTTPException(401, "Invalid credentials or unverified account")
    attempt.failures = 0
    raw = fresh_token()
    session = Session(user_id=user.id, token_hash=digest(raw), csrf_token=fresh_token(),
                      expires_at=utcnow() + timedelta(days=settings.session_days))
    db.add(session)
    db.commit()
    response.set_cookie(COOKIE_NAME, raw, httponly=True, secure=settings.secure_cookies,
                        samesite="lax", max_age=settings.session_days * 86400, path="/")
    return {"email": user.email, "csrf_token": session.csrf_token, "is_admin": user.is_admin}


@router.get("/me")
def me(identity: tuple[User, Session] = Depends(get_session)):
    user, session = identity
    return {"email": user.email, "csrf_token": session.csrf_token, "is_admin": user.is_admin}


@router.post("/logout")
def logout(response: Response, identity: tuple[User, Session] = Depends(get_session), db: DbSession = Depends(get_db)):
    db.delete(identity[1])
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"message": "Signed out"}


@router.post("/change-password")
def change_password(body: ChangePasswordBody, identity: tuple[User, Session] = Depends(get_session), db: DbSession = Depends(get_db)):
    user, current_session = identity
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(400, "Choose a different password")
    user.password_hash = hasher.hash(body.new_password)
    db.query(Session).filter(Session.user_id == user.id, Session.id != current_session.id).delete(synchronize_session=False)
    db.query(AuthToken).filter_by(user_id=user.id, purpose="reset").delete(synchronize_session=False)
    db.commit()
    return {"message": "Password changed. Other sessions have been signed out."}


@router.post("/forgot-password")
def forgot_password(body: EmailOnly, request: Request, db: DbSession = Depends(get_db)):
    email = normalized(body.email)
    throttle(db, request, "reset", email, 5)
    user = db.query(User).filter_by(email=email).first()
    if user and user.verified_at:
        token = issue_auth_token(db, email, "reset", user.id)
        try:
            send_email(email, f"Reset your {settings.app_name} password", f"Open this link to reset your {settings.app_name} password:\n{settings.public_base_url}/reset/{token}")
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(503, "Email delivery unavailable")
    return {"message": delivery_message("If an account exists, a reset link has been sent.")}


@router.post("/reset-password")
def reset_password(body: ResetBody, db: DbSession = Depends(get_db)):
    token = consume_auth_token(db, body.token, "reset")
    user = db.get(User, token.user_id)
    if not user:
        raise HTTPException(400, "Invalid link")
    user.password_hash = hasher.hash(body.password)
    db.flush()
    db.query(AuthToken).filter_by(user_id=user.id, purpose="reset").delete(synchronize_session=False)
    db.query(Session).filter_by(user_id=user.id).delete()
    db.commit()
    return {"message": "Password reset; please sign in"}

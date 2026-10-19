"""Requests for access from the public site. Anyone may ask; site admins invite the club's coach or decline."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as DbSession
from .. import notify
from ..config import settings
from ..database import get_db
from ..models import AccessRequest, User, utcnow
from .accounts import throttle
from .admin import issue_site_invite, require_admin

router = APIRouter(tags=["access requests"])

THANKS = "Thanks: we've got your request and will reply by email."


class AccessRequestIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    club: str = Field(min_length=1, max_length=120)
    teams: int | None = Field(default=None, ge=1, le=99)
    message: str = Field(default="", max_length=1000)
    # Hidden on the form: people never fill it in, form-filling bots usually do.
    website: str = ""


class AccessRequestOut(BaseModel):
    id: int
    name: str
    email: str
    club: str
    teams: int | None
    message: str
    status: str
    has_account: bool
    created_at: datetime
    handled_at: datetime | None


@router.post("/access-requests", status_code=201)
def request_access(body: AccessRequestIn, request: Request, db: DbSession = Depends(get_db)):
    """Always gives the same answer, so the form doesn't reveal who already has an account or has asked before."""
    email = str(body.email).strip().casefold()
    throttle(db, request, "access", "", 5)
    if body.website:
        return {"message": THANKS}
    existing = db.query(AccessRequest).filter_by(email=email, status="pending").first()
    if existing:
        existing.name, existing.club, existing.teams = body.name.strip(), body.club.strip(), body.teams
        existing.message = body.message.strip() or existing.message
        db.commit()
        return {"message": THANKS}
    row = AccessRequest(name=body.name.strip(), email=email, club=body.club.strip(), teams=body.teams,
                        message=body.message.strip(), status="pending", created_at=utcnow())
    db.add(row)
    db.commit()
    notify.access_requested(db, row)
    return {"message": THANKS}


def request_out(db: DbSession, row: AccessRequest) -> dict:
    return {"id": row.id, "name": row.name, "email": row.email, "club": row.club, "teams": row.teams, "message": row.message,
            "status": row.status, "has_account": db.query(User).filter_by(email=row.email).first() is not None,
            "created_at": row.created_at, "handled_at": row.handled_at}


def _pending(db: DbSession, request_id: int) -> AccessRequest:
    row = db.get(AccessRequest, request_id)
    if not row:
        raise HTTPException(404, "Request not found")
    if row.status != "pending":
        raise HTTPException(409, "This request has already been dealt with")
    return row


@router.get("/admin/access-requests", response_model=list[AccessRequestOut])
def list_access_requests(status: Literal["pending", "invited", "declined"] = "pending", db: DbSession = Depends(get_db),
                         admin: User = Depends(require_admin)):
    rows = db.query(AccessRequest).filter_by(status=status).order_by(AccessRequest.created_at, AccessRequest.id).limit(200)
    return [request_out(db, r) for r in rows]


@router.post("/admin/access-requests/{request_id}/invite")
def invite_from_request(request_id: int, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Send the site invitation a request asks for. The answer is the invitation, with its link to copy."""
    row = _pending(db, request_id)
    invite = issue_site_invite(db, row.email)
    row.status, row.handled_by, row.handled_at = "invited", admin.id, utcnow()
    db.commit()
    return invite


@router.post("/admin/access-requests/{request_id}/decline")
def decline_request(request_id: int, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Mark a request as declined. Nothing is emailed: reply yourself if you want to explain."""
    row = _pending(db, request_id)
    row.status, row.handled_by, row.handled_at = "declined", admin.id, utcnow()
    db.commit()
    return {"message": f"Declined the request from {row.club}."}

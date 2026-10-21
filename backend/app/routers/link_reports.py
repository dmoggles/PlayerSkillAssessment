"""Coaches reporting a library drill's video or link that doesn't work or shouldn't be there. A site admin hides
it from the drill, or keeps it. Hiding works by URL, so it lasts when the loader rewrites the drill's media."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from .. import notify
from ..auth import current_user
from ..database import get_db
from ..models import Drill, DrillLinkReport, DrillMedia, DrillVideoSuggestion, User, utcnow
from .admin import require_admin
from .drills import drill_for, hidden_urls

router = APIRouter(tags=["link reports"])

MAX_OPEN_PER_COACH = 20
Reason = Literal["dead", "inappropriate", "other"]


class ReportIn(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    reason: Reason
    note: str = Field(default="", max_length=500)


def _link(db: DbSession, drill: Drill, url: str) -> tuple[dict, DrillVideoSuggestion | None] | None:
    """The drill's own video or link with this URL, or an approved coach's suggestion; None if neither is shown."""
    media = db.query(DrillMedia).filter(DrillMedia.drill_id == drill.id, DrillMedia.url == url, DrillMedia.kind.in_(("video", "link"))).first()
    if media:
        return {"kind": media.kind, "caption": media.caption}, None
    suggestion = db.query(DrillVideoSuggestion).filter_by(drill_id=drill.id, url=url, status="approved").first()
    if suggestion:
        return {"kind": "video", "caption": suggestion.caption or suggestion.title}, suggestion
    return None


@router.post("/drills/{slug}/link-reports", status_code=201)
def report_link(slug: str, body: ReportIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    drill = drill_for(db, slug, user)
    if drill.team_id:
        raise HTTPException(422, "This is your team's own drill: edit it to change its video")
    url = body.url.strip()
    found = _link(db, drill, url) if url not in hidden_urls(db, drill.id) else None
    if not found:
        raise HTTPException(404, "That link isn't on this drill")
    _, suggestion = found
    open_reports = db.query(DrillLinkReport).filter_by(drill_id=drill.id, url=url, status="open")
    if open_reports.filter_by(reported_by=user.id).first():
        raise HTTPException(409, "You've already reported this link. A site admin will check it.")
    if db.query(DrillLinkReport).filter_by(reported_by=user.id, status="open").count() >= MAX_OPEN_PER_COACH:
        raise HTTPException(429, f"You have {MAX_OPEN_PER_COACH} reports waiting for a site admin. Please wait until some have been checked.")
    first = open_reports.first() is None
    report = DrillLinkReport(drill_id=drill.id, url=url, suggestion_id=suggestion.id if suggestion else None,
                             reason=body.reason, note=body.note.strip(), reported_by=user.id, status="open", created_at=utcnow())
    db.add(report)
    if suggestion:
        suggestion.reports += 1
    db.commit()
    # One email per link: further reports of the same link join the one already waiting.
    if first:
        notify.link_reported(db, report, drill, user)
    return {"message": "Thanks. A site admin will check the link."}


# Site admins: one item per reported link, with every report of it.
class ReportOut(BaseModel):
    reason: str
    note: str
    reported_by: str | None
    created_at: datetime


class QueueItem(BaseModel):
    id: int
    drill_slug: str
    drill_title: str
    url: str
    kind: str | None
    caption: str | None
    suggested: bool
    status: str
    reports: list[ReportOut]
    handled_at: datetime | None


def _queue_item(db: DbSession, rows: list[DrillLinkReport]) -> dict:
    first, drill = rows[0], db.get(Drill, rows[0].drill_id)
    found = _link(db, drill, first.url)
    if not found and first.suggestion_id:
        s = db.get(DrillVideoSuggestion, first.suggestion_id)
        found = ({"kind": "video", "caption": s.caption or s.title}, s) if s else None
    users = {u.id: u.email for u in db.query(User).filter(User.id.in_([r.reported_by for r in rows if r.reported_by]))}
    return {"id": first.id, "drill_slug": drill.slug, "drill_title": drill.title, "url": first.url,
            # No kind or caption: the link has gone from the drill since it was reported.
            "kind": found[0]["kind"] if found else None, "caption": found[0]["caption"] if found else None,
            "suggested": first.suggestion_id is not None, "status": first.status,
            "reports": [{"reason": r.reason, "note": r.note, "reported_by": users.get(r.reported_by), "created_at": r.created_at} for r in rows],
            "handled_at": max((r.handled_at for r in rows if r.handled_at), default=None)}


@router.get("/admin/link-reports", response_model=list[QueueItem])
def link_report_queue(status: Literal["open", "hidden"] = "open", db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Reported links oldest report first; hidden ones most recently hidden first."""
    groups: dict[tuple[int, str], list[DrillLinkReport]] = {}
    for r in db.query(DrillLinkReport).filter_by(status=status).order_by(DrillLinkReport.created_at, DrillLinkReport.id):
        groups.setdefault((r.drill_id, r.url), []).append(r)
    items = [_queue_item(db, rows) for rows in groups.values()]
    if status == "hidden":
        items.sort(key=lambda i: i["handled_at"], reverse=True)
    return items[:200]


def _group(db: DbSession, report_id: int, status: str) -> list[DrillLinkReport]:
    report = db.get(DrillLinkReport, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    rows = db.query(DrillLinkReport).filter_by(drill_id=report.drill_id, url=report.url, status=status).all()
    if not rows:
        raise HTTPException(409, "This link has already been dealt with")
    return rows


def _handle(db: DbSession, rows: list[DrillLinkReport], status: str, admin: User, suggestion_status: str | None) -> dict:
    now = utcnow()
    for r in rows:
        r.status, r.handled_by, r.handled_at = status, admin.id, now
    suggestion_ids = {r.suggestion_id for r in rows if r.suggestion_id}
    if suggestion_status and suggestion_ids:
        for s in db.query(DrillVideoSuggestion).filter(DrillVideoSuggestion.id.in_(suggestion_ids)):
            s.status, s.reviewed_by, s.reviewed_at, s.updated_at = suggestion_status, admin.id, now, now
    db.commit()
    return _queue_item(db, rows)


@router.post("/admin/link-reports/{report_id}/hide", response_model=QueueItem)
def hide_link(report_id: int, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Take the link off its drill for everyone. A coach's suggested video is marked no longer available."""
    return _handle(db, _group(db, report_id, "open"), "hidden", admin, "hidden")


@router.post("/admin/link-reports/{report_id}/keep", response_model=QueueItem)
def keep_link(report_id: int, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """The link is fine: close its reports and leave it on the drill."""
    return _handle(db, _group(db, report_id, "open"), "dismissed", admin, None)


@router.post("/admin/link-reports/{report_id}/restore", response_model=QueueItem)
def restore_link(report_id: int, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Put a hidden link back on its drill."""
    return _handle(db, _group(db, report_id, "hidden"), "dismissed", admin, "approved")

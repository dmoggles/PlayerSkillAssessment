"""Videos coaches suggest for drills. Nothing is shown to other coaches until a site admin approves it."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from .. import notify, video_links
from ..auth import current_user
from ..database import get_db
from ..models import Drill, DrillMedia, DrillVariation, DrillVideoSuggestion, User, utcnow
from .admin import require_admin

router = APIRouter(tags=["video suggestions"])

MAX_PENDING_PER_COACH = 10
ALREADY = {"pending": "This video has already been suggested for this drill and is waiting for review.",
           "approved": "This video is already on this drill.",
           "rejected": "This video has already been suggested for this drill and wasn't added.",
           "hidden": "This video was on this drill but is no longer available."}


class SuggestionIn(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    variation_id: int | None = None
    start_seconds: int | None = Field(default=None, ge=0, le=36000)
    note: str = Field(default="", max_length=500)


class MySuggestion(BaseModel):
    id: int
    drill_slug: str
    drill_title: str
    variation_title: str | None
    url: str
    title: str
    channel: str
    status: str
    reject_reason: str | None
    reject_note: str | None
    created_at: datetime
    reviewed_at: datetime | None


def mine_out(suggestion: DrillVideoSuggestion, drill: Drill, variation: DrillVariation | None) -> dict:
    return {"id": suggestion.id, "drill_slug": drill.slug, "drill_title": drill.title,
            "variation_title": variation.title if variation else None, "url": suggestion.url, "title": suggestion.title,
            "channel": suggestion.channel, "status": suggestion.status, "reject_reason": suggestion.reject_reason,
            "reject_note": suggestion.reject_note, "created_at": suggestion.created_at, "reviewed_at": suggestion.reviewed_at}


@router.post("/drills/{slug}/video-suggestions", response_model=MySuggestion, status_code=201)
def suggest_video(slug: str, body: SuggestionIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    # Library drills only: a team adds a video to its own drill by editing it.
    drill = db.query(Drill).filter_by(slug=slug, status="published", team_id=None).first()
    if not drill:
        raise HTTPException(404, "Drill not found")
    variation = None
    if body.variation_id is not None:
        variation = db.query(DrillVariation).filter_by(id=body.variation_id, drill_id=drill.id).first()
        if not variation:
            raise HTTPException(422, "That variation isn't part of this drill")
    link = video_links.parse(body.url)
    if not link:
        raise HTTPException(422, "Use a link to a YouTube or Vimeo video")
    curated = (video_links.parse(m.url or "") for m in db.query(DrillMedia).filter_by(drill_id=drill.id, kind="video"))
    if any(c and (c.host, c.video_id) == (link.host, link.video_id) for c in curated):
        raise HTTPException(409, ALREADY["approved"])
    existing = db.query(DrillVideoSuggestion).filter_by(drill_id=drill.id, host=link.host, video_id=link.video_id).first()
    if existing:
        raise HTTPException(409, ALREADY[existing.status])
    if db.query(DrillVideoSuggestion).filter_by(suggested_by=user.id, status="pending").count() >= MAX_PENDING_PER_COACH:
        raise HTTPException(429, f"You have {MAX_PENDING_PER_COACH} suggestions waiting for review. Please wait until some have been reviewed.")
    try:
        details = video_links.lookup(link)
    except video_links.VideoUnavailable:
        raise HTTPException(422, "That video isn't public, or its owner doesn't allow it to be shown on other sites")
    except video_links.LookupFailed:
        raise HTTPException(503, "Couldn't check the video just now. Please try again in a minute.")
    now = utcnow()
    suggestion = DrillVideoSuggestion(
        drill_id=drill.id, variation_id=variation.id if variation else None, url=link.url, host=link.host,
        video_id=link.video_id, start_seconds=body.start_seconds if body.start_seconds is not None else link.start_seconds,
        title=details.title, channel=details.channel, duration_seconds=details.duration_seconds, note=body.note.strip(),
        suggested_by=user.id, status="pending", created_at=now, updated_at=now)
    db.add(suggestion)
    db.commit()
    notify.video_suggested(db, suggestion, drill, user)
    return mine_out(suggestion, drill, variation)


@router.get("/me/video-suggestions", response_model=list[MySuggestion])
def my_video_suggestions(db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    rows = (db.query(DrillVideoSuggestion, Drill, DrillVariation)
            .join(Drill, Drill.id == DrillVideoSuggestion.drill_id)
            .outerjoin(DrillVariation, DrillVariation.id == DrillVideoSuggestion.variation_id)
            .filter(DrillVideoSuggestion.suggested_by == user.id)
            .order_by(DrillVideoSuggestion.created_at.desc(), DrillVideoSuggestion.id.desc()))
    return [mine_out(s, d, v) for s, d, v in rows]


def approved_videos(db: DbSession, drill_id: int) -> list[dict]:
    """Approved suggestions, shown after a drill's own videos. Who suggested them is never included."""
    rows = db.query(DrillVideoSuggestion).filter_by(drill_id=drill_id, status="approved").order_by(DrillVideoSuggestion.reviewed_at, DrillVideoSuggestion.id)
    return [{"id": f"suggested-{s.id}", "suggestion_id": s.id, "kind": "video", "caption": s.caption or s.title, "url": s.url,
             "start_seconds": s.start_seconds, "variation_id": s.variation_id} for s in rows]


# Site admins review suggestions. Approval puts a video in front of every coach, and of players through shared reports.
RejectReason = Literal["not_a_demo", "mismatch", "quality", "shared_privately", "safeguarding", "other"]
Status = Literal["pending", "approved", "rejected", "hidden"]


class ReviewVariation(BaseModel):
    id: int
    kind: str
    title: str


class QueueItem(BaseModel):
    id: int
    drill_slug: str
    drill_title: str
    variations: list[ReviewVariation]
    variation_id: int | None
    url: str
    start_seconds: int | None
    title: str
    channel: str
    duration_seconds: int | None
    note: str
    suggested_by: str | None
    status: str
    caption: str | None
    reject_reason: str | None
    reject_note: str | None
    reports: int
    created_at: datetime
    reviewed_at: datetime | None


class ApproveBody(BaseModel):
    caption: str = Field(min_length=1, max_length=200)
    variation_id: int | None = None


class RejectBody(BaseModel):
    reason: RejectReason
    note: str = Field(default="", max_length=300)


def queue_out(db: DbSession, suggestion: DrillVideoSuggestion) -> dict:
    drill = db.get(Drill, suggestion.drill_id)
    suggester = db.get(User, suggestion.suggested_by) if suggestion.suggested_by else None
    variations = db.query(DrillVariation).filter_by(drill_id=drill.id).order_by(DrillVariation.position)
    return {"id": suggestion.id, "drill_slug": drill.slug, "drill_title": drill.title,
            "variations": [{"id": v.id, "kind": v.kind, "title": v.title} for v in variations],
            "variation_id": suggestion.variation_id, "url": suggestion.url, "start_seconds": suggestion.start_seconds,
            "title": suggestion.title, "channel": suggestion.channel, "duration_seconds": suggestion.duration_seconds,
            "note": suggestion.note, "suggested_by": suggester.email if suggester else None, "status": suggestion.status,
            "caption": suggestion.caption, "reject_reason": suggestion.reject_reason, "reject_note": suggestion.reject_note,
            "reports": suggestion.reports, "created_at": suggestion.created_at, "reviewed_at": suggestion.reviewed_at}


def _suggestion(db: DbSession, suggestion_id: int) -> DrillVideoSuggestion:
    suggestion = db.get(DrillVideoSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(404, "Suggestion not found")
    return suggestion


@router.get("/admin/video-suggestions", response_model=list[QueueItem])
def review_queue(status: Status = "pending", db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Pending suggestions oldest first, so none waits forever; the other lists newest decision first."""
    query = db.query(DrillVideoSuggestion).filter_by(status=status)
    order = (DrillVideoSuggestion.created_at, DrillVideoSuggestion.id) if status == "pending" else (DrillVideoSuggestion.reviewed_at.desc(), DrillVideoSuggestion.id.desc())
    return [queue_out(db, s) for s in query.order_by(*order).limit(200)]


@router.post("/admin/video-suggestions/{suggestion_id}/approve", response_model=QueueItem)
def approve_suggestion(suggestion_id: int, body: ApproveBody, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    suggestion = _suggestion(db, suggestion_id)
    if suggestion.status not in ("pending", "rejected"):
        raise HTTPException(409, "Only suggestions waiting for review, or turned down, can be approved")
    if body.variation_id is not None and not db.query(DrillVariation).filter_by(id=body.variation_id, drill_id=suggestion.drill_id).first():
        raise HTTPException(422, "That variation isn't part of this drill")
    now = utcnow()
    suggestion.status, suggestion.caption, suggestion.variation_id = "approved", body.caption.strip(), body.variation_id
    suggestion.reject_reason = suggestion.reject_note = None
    suggestion.reviewed_by, suggestion.reviewed_at, suggestion.updated_at = admin.id, now, now
    db.commit()
    return queue_out(db, suggestion)


@router.post("/admin/video-suggestions/{suggestion_id}/reject", response_model=QueueItem)
def reject_suggestion(suggestion_id: int, body: RejectBody, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Turn a suggestion down, or take an approved video off its drill."""
    suggestion = _suggestion(db, suggestion_id)
    if suggestion.status not in ("pending", "approved"):
        raise HTTPException(409, "This suggestion has already been turned down or removed")
    now = utcnow()
    suggestion.status, suggestion.reject_reason, suggestion.reject_note = "rejected", body.reason, body.note.strip() or None
    suggestion.reviewed_by, suggestion.reviewed_at, suggestion.updated_at = admin.id, now, now
    db.commit()
    return queue_out(db, suggestion)

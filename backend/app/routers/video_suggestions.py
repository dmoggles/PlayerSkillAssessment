"""Videos coaches suggest for drills. Nothing is shown to other coaches until a site admin approves it."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from .. import video_links
from ..auth import current_user
from ..database import get_db
from ..models import Drill, DrillMedia, DrillVariation, DrillVideoSuggestion, User, utcnow

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
    drill = db.query(Drill).filter_by(slug=slug, status="published").first()
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
    return mine_out(suggestion, drill, variation)


@router.get("/me/video-suggestions", response_model=list[MySuggestion])
def my_video_suggestions(db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    rows = (db.query(DrillVideoSuggestion, Drill, DrillVariation)
            .join(Drill, Drill.id == DrillVideoSuggestion.drill_id)
            .outerjoin(DrillVariation, DrillVariation.id == DrillVideoSuggestion.variation_id)
            .filter(DrillVideoSuggestion.suggested_by == user.id)
            .order_by(DrillVideoSuggestion.created_at.desc(), DrillVideoSuggestion.id.desc()))
    return [mine_out(s, d, v) for s, d, v in rows]

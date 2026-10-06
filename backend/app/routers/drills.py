"""The shared drill library, read by any signed-in coach."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession
from ..auth import current_user
from ..database import get_db
from ..models import utcnow, Drill, DrillLink, DrillMedia, DrillTag, DrillVariation, DrillVote, SkillTag, User

router = APIRouter(tags=["drills"])


def _tags(db: DbSession, drill_ids: list[int]) -> dict[int, list[dict]]:
    out = {}
    rows = db.query(DrillTag, SkillTag).join(SkillTag, SkillTag.id == DrillTag.tag_id).filter(DrillTag.drill_id.in_(drill_ids))
    for link, tag in rows.order_by(DrillTag.weight.desc(), SkillTag.label):
        out.setdefault(link.drill_id, []).append({"id": tag.id, "label": tag.label, "area": tag.area, "weight": link.weight})
    return out


def _votes(db: DbSession, drill_ids: list[int], user: User) -> dict[int, dict]:
    totals = {drill_id: {"likes": 0, "dislikes": 0, "mine": 0, "reason": None} for drill_id in drill_ids}
    for drill_id, vote, count in db.query(DrillVote.drill_id, DrillVote.vote, func.count()).filter(
            DrillVote.drill_id.in_(drill_ids)).group_by(DrillVote.drill_id, DrillVote.vote):
        totals[drill_id]["likes" if vote > 0 else "dislikes"] = count
    for vote in db.query(DrillVote).filter(DrillVote.drill_id.in_(drill_ids), DrillVote.user_id == user.id):
        totals[vote.drill_id].update(mine=vote.vote, reason=vote.reason)
    return totals


def summary(drill: Drill, tags: list[dict], levels: tuple[int, int], votes: dict) -> dict:
    return {"slug": drill.slug, "title": drill.title, "summary": drill.summary, "format": drill.format,
            "players": [drill.players_min, drill.players_ideal, drill.players_max], "ages": [drill.age_min, drill.age_max],
            "duration": [drill.duration_min, drill.duration_typical], "session_phase": drill.session_phase,
            "intensity": drill.intensity, "home_friendly": drill.home_friendly, "tags": tags,
            "equipment_items": sorted({e["item"] for e in drill.equipment}),
            "levels": list(levels), "votes": votes}


@router.get("/drills")
def list_drills(db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    drills = db.query(Drill).filter_by(status="published").order_by(Drill.title).all()
    ids = [d.id for d in drills]
    levels = {drill_id: (lo, hi) for drill_id, lo, hi in db.query(
        DrillVariation.drill_id, func.min(DrillVariation.level_min), func.max(DrillVariation.level_max)).filter(
        DrillVariation.drill_id.in_(ids)).group_by(DrillVariation.drill_id)}
    tags, votes = _tags(db, ids), _votes(db, ids, user)
    return [summary(d, tags.get(d.id, []), levels.get(d.id, (1, 5)), votes[d.id]) for d in drills]


@router.get("/drills/{slug}")
def drill_detail(slug: str, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    drill = db.query(Drill).filter_by(slug=slug, status="published").first()
    if not drill:
        raise HTTPException(404, "Drill not found")
    variations = db.query(DrillVariation).filter_by(drill_id=drill.id).order_by(DrillVariation.position).all()
    media = db.query(DrillMedia).filter_by(drill_id=drill.id).order_by(DrillMedia.position).all()
    links = db.query(DrillLink, Drill).join(Drill, Drill.id == DrillLink.to_drill_id).filter(
        DrillLink.from_drill_id == drill.id, Drill.status == "published").all()
    levels = (min(v.level_min for v in variations), max(v.level_max for v in variations))
    return {**summary(drill, _tags(db, [drill.id]).get(drill.id, []), levels, _votes(db, [drill.id], user)[drill.id]),
            "space": [float(drill.space_width_m), float(drill.space_length_m)] if drill.space_width_m is not None else None,
            "equipment": drill.equipment, "setup": drill.setup, "instructions": drill.instructions,
            "coaching_points": drill.coaching_points,
            "variations": [{"id": v.id, "kind": v.kind, "title": v.title, "change": v.change, "levels": [v.level_min, v.level_max],
                            "diagram_media_id": v.diagram_media_id, "video_media_id": v.video_media_id,
                            # Overrides of the drill's content; null means "same as the drill".
                            "setup": v.setup, "equipment": v.equipment, "instructions": v.instructions,
                            "coaching_points": v.coaching_points,
                            "players": [v.players_min, v.players_ideal, v.players_max] if v.players_min is not None else None,
                            "space": [float(v.space_width_m), float(v.space_length_m)] if v.space_width_m is not None else None}
                           for v in variations],
            "media": [{"id": m.id, "kind": m.kind, "caption": m.caption, "url": m.url, "start_seconds": m.video_start_seconds,
                       "diagram": m.diagram} for m in media],
            "links": [{"slug": d.slug, "title": d.title, "relation": link.relation} for link, d in links]}


DislikeReason = Literal["too_advanced", "too_easy", "unclear", "equipment_or_space", "did_not_work", "other"]


class VoteIn(BaseModel):
    vote: Literal[-1, 0, 1]  # 0 clears the coach's vote
    reason: DislikeReason | None = None

    @model_validator(mode="after")
    def reason_only_for_dislikes(self):
        if self.reason and self.vote != -1:
            raise ValueError("A reason can only be given with a dislike")
        return self


@router.put("/drills/{slug}/vote")
def vote_on_drill(slug: str, payload: VoteIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Like or dislike a drill. Each coach has one vote per drill; totals are shared, the vote itself is private."""
    drill = db.query(Drill).filter_by(slug=slug, status="published").first()
    if not drill:
        raise HTTPException(404, "Drill not found")
    existing = db.get(DrillVote, (user.id, drill.id))
    if payload.vote == 0:
        if existing:
            db.delete(existing)
    elif existing:
        existing.vote, existing.reason, existing.updated_at = payload.vote, payload.reason, utcnow()
    else:
        db.add(DrillVote(user_id=user.id, drill_id=drill.id, vote=payload.vote, reason=payload.reason, updated_at=utcnow()))
    db.commit()
    return _votes(db, [drill.id], user)[drill.id]

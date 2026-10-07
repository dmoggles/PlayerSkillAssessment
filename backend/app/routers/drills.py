"""The shared drill library, read by any signed-in coach."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession
from ..auth import current_user, require_member
from ..database import get_db
from ..matrix import version_tags
from ..models import utcnow, Assessment, Drill, DrillLink, DrillMedia, DrillTag, DrillVariation, DrillVote, Period, Player, PlayerGroup, Rating, SkillTag, User

router = APIRouter(tags=["drills"])


def _tags(db: DbSession, drill_ids: list[int]) -> dict[int, list[dict]]:
    out = {}
    rows = db.query(DrillTag, SkillTag).join(SkillTag, SkillTag.id == DrillTag.tag_id).filter(DrillTag.drill_id.in_(drill_ids))
    for link, tag in rows.order_by(DrillTag.weight.desc(), SkillTag.label):
        out.setdefault(link.drill_id, []).append({"id": tag.id, "label": tag.label, "area": tag.area, "weight": link.weight,
                                                   "on_ladder": link.on_ladder})
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
    return drill_out(db, drill, user)


def drill_out(db: DbSession, drill: Drill, user: User | None) -> dict:
    """A drill in full. Without a user (a shared plan's link) there are no votes and no related drills."""
    variations = db.query(DrillVariation).filter_by(drill_id=drill.id).order_by(DrillVariation.position).all()
    media = db.query(DrillMedia).filter_by(drill_id=drill.id).order_by(DrillMedia.position).all()
    links = db.query(DrillLink, Drill).join(Drill, Drill.id == DrillLink.to_drill_id).filter(
        DrillLink.from_drill_id == drill.id, Drill.status == "published").all()
    levels = (min(v.level_min for v in variations), max(v.level_max for v in variations))
    return {**summary(drill, _tags(db, [drill.id]).get(drill.id, []), levels, _votes(db, [drill.id], user)[drill.id] if user else None),
            "space": [float(drill.space_width_m), float(drill.space_length_m)] if drill.space_width_m is not None else None,
            "equipment": drill.equipment, "setup": drill.setup, "instructions": drill.instructions,
            "coaching_points": drill.coaching_points, "indoors": drill.indoors,
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
            "links": [{"slug": d.slug, "title": d.title, "relation": link.relation} for link, d in links] if user else []}


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


SUGGESTIONS_PER_SKILL = 3


def _library(db: DbSession, age_group: int | None, user: User):
    """Published drills for an age group (all of them when it is not known), with their tags, ladder tags,
    variations, votes and tag labels."""
    drills = db.query(Drill).filter_by(status="published").all()
    if age_group:
        drills = [d for d in drills if d.age_min <= age_group <= d.age_max]
    ids = [d.id for d in drills]
    drill_tags, ladder_tags = {}, {}
    for link in db.query(DrillTag).filter(DrillTag.drill_id.in_(ids)):
        drill_tags.setdefault(link.drill_id, {})[link.tag_id] = link.weight
        if link.on_ladder:
            ladder_tags.setdefault(link.drill_id, set()).add(link.tag_id)
    variations = {}
    for v in db.query(DrillVariation).filter(DrillVariation.drill_id.in_(ids)).order_by(DrillVariation.position):
        variations.setdefault(v.drill_id, []).append(v)
    return drills, drill_tags, ladder_tags, variations, _votes(db, ids, user), _tags(db, ids)


def _player_context(db: DbSession, team_id: int, player_id: int, period_id: int, user: User):
    """The player's playing group, the period, its skill tags and the coach's ratings for the player, or 404."""
    require_member(team_id, db, user)
    player, period = db.get(Player, player_id), db.get(Period, period_id)
    if not player or player.team_id != team_id or not period or period.team_id != team_id:
        raise HTTPException(404, "Not found")
    coach = db.query(Assessment).filter_by(player_id=player_id, period_id=period_id, assessor="coach").first()
    levels = {r.skill_id: r.score for r in db.query(Rating).filter_by(assessment_id=coach.id)} if coach else {}
    group = db.query(PlayerGroup).filter_by(player_id=player_id, period_id=period_id).first()
    return group.age_group if group else None, period, version_tags(db, period.matrix_version_id), levels


def variation_for_level(variations: list[DrillVariation], level: int | None) -> DrillVariation:
    """The hardest variation whose level range includes the player's level; the base one when unrated."""
    if level is not None:
        fitting = [v for v in variations if v.level_min <= level <= v.level_max]
        if fitting:
            return fitting[-1]
        # Beyond the drill's range: the nearest end of the ladder.
        return variations[-1] if level > variations[-1].level_max else variations[0]
    return next(v for v in variations if v.kind == "base")


@router.get("/teams/{team_id}/players/{player_id}/drill-suggestions")
def drill_suggestions(team_id: int, player_id: int, period_id: int, skills: list[str] = Query(default=[], max_length=10),
                      db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Drills for a player's priority skills, at the variation that matches the coach's rating of each skill.
    A drill matches through the tags it shares with the skill. The coach's own dislikes are left out, their likes
    come first; then the strength of the match and the other coaches' votes decide. Drills outside the player's
    playing group in that period are left out."""
    team, period, skill_tags, levels = _player_context(db, team_id, player_id, period_id, user)

    drills, drill_tags, ladder_tags, variations, votes, tags = _library(db, team, user)

    out = {}
    for skill_id in dict.fromkeys(skills):
        wanted = skill_tags.get(skill_id, {})
        level = levels.get(skill_id)
        matches = []
        for drill in drills:
            strength = sum(weight * drill_tags.get(drill.id, {}).get(tag, 0) for tag, weight in wanted.items())
            if strength and votes[drill.id]["mine"] != -1:
                matches.append((drill, strength))
        matches.sort(key=lambda m: (-votes[m[0].id]["mine"], -m[1], votes[m[0].id]["dislikes"] - votes[m[0].id]["likes"], m[0].title))
        suggested = []
        for drill, strength in matches[:SUGGESTIONS_PER_SKILL]:
            # Rungs only follow the player's level when the ladder describes this skill; otherwise the base version.
            follows = bool(ladder_tags.get(drill.id, set()) & {t for t in wanted if t in drill_tags[drill.id]})
            v = variation_for_level(variations[drill.id], level if follows else None)
            suggested.append({"slug": drill.slug, "title": drill.title, "summary": drill.summary, "format": drill.format,
                              "players": [drill.players_min, drill.players_ideal, drill.players_max],
                              "duration": [drill.duration_min, drill.duration_typical], "votes": votes[drill.id],
                              "tags": [t for t in tags.get(drill.id, []) if t["id"] in wanted],
                              "variation": {"id": v.id, "kind": v.kind, "title": v.title, "levels": [v.level_min, v.level_max],
                                            "level_matched": follows and level is not None},
                              "ladder_for": [] if follows else [t["label"] for t in tags.get(drill.id, []) if t["on_ladder"]]})
        out[skill_id] = {"tagged": bool(wanted), "level": level, "matches": len(matches), "drills": suggested}
    return out


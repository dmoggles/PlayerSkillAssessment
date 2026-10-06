"""Development plans: generated on request for coaches, and shared with players and parents through an expiring
link that needs no login. The link also opens the plan's drills, and only those."""
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, digest, fresh_token
from ..config import settings
from ..database import get_db
from ..matrix import document
from ..models import Drill, Period, Player, SharedPlan, Team, User, utcnow
from ..plans import plan as rules_plan
from .drills import _library, _player_context, drill_out

router = APIRouter(tags=["plans"])
GRACE_DAYS = 7  # a shared plan stays open a week past its last week


def build_plan(db: DbSession, team_id: int, player_id: int, period_id: int, skills: list[str], weeks: int, user: User) -> dict:
    team, period, skill_tags, levels = _player_context(db, team_id, player_id, period_id, user)
    labels = {s["id"]: s["label"] for section in document(db, period.matrix_version_id)["sections"] for s in section["skills"]}
    drills, drill_tags, ladder_tags, variations, votes, tags = _library(db, team, user)
    return rules_plan({
        "weeks": weeks,
        "priorities": [{"rank": rank, "skill_id": skill_id, "label": labels.get(skill_id, skill_id),
                        "level": levels.get(skill_id), "tags": skill_tags.get(skill_id, {})}
                       for rank, skill_id in enumerate(dict.fromkeys(skills), start=1)],
        "drills": [{"slug": d.slug, "title": d.title, "home_friendly": d.home_friendly,
                    "duration": [d.duration_min, d.duration_typical], "tags": drill_tags.get(d.id, {}),
                    "tag_labels": {t["id"]: t["label"] for t in tags.get(d.id, [])},
                    "ladder_tags": sorted(ladder_tags.get(d.id, set())),
                    "variations": [{"id": v.id, "kind": v.kind, "title": v.title, "levels": [v.level_min, v.level_max]}
                                   for v in variations.get(d.id, [])],
                    "my_vote": votes[d.id]["mine"], "net_votes": votes[d.id]["likes"] - votes[d.id]["dislikes"]}
                   for d in drills if variations.get(d.id)],
    })


@router.get("/teams/{team_id}/players/{player_id}/plan")
def development_plan(team_id: int, player_id: int, period_id: int, skills: list[str] = Query(default=[], max_length=5),
                     weeks: int = Query(default=4, ge=1, le=8), db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """A plan of club and home drills for the player's priorities, in rank order. Generated on request, not stored."""
    return build_plan(db, team_id, player_id, period_id, skills, weeks, user)


def share_status(shared: SharedPlan | None) -> dict | None:
    if not shared:
        return None
    return {"created_at": shared.created_at, "expires_at": shared.expires_at, "opened_at": shared.opened_at,
            "expired": shared.expires_at.replace(tzinfo=timezone.utc) <= utcnow(),
            # The priorities it was made for, in rank order, so the coach can tell whether it is out of date.
            "skills": [skill for _, skill in sorted({(i["rank"], i["skill_id"]) for i in shared.plan["slots"] + shared.plan["gaps"]})]}


@router.get("/teams/{team_id}/players/{player_id}/plan/share")
def plan_share_status(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    _player_context(db, team_id, player_id, period_id, user)
    return {"share": share_status(db.query(SharedPlan).filter_by(player_id=player_id, period_id=period_id).first())}


class ShareIn(BaseModel):
    period_id: int
    skills: list[str] = Field(min_length=1, max_length=5)
    weeks: int = Field(default=4, ge=1, le=8)


@router.post("/teams/{team_id}/players/{player_id}/plan/share")
def share_plan(team_id: int, player_id: int, body: ShareIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Freeze the plan for these priorities and return a link to it, replacing any earlier one. The raw link is
    only returned here."""
    built = build_plan(db, team_id, player_id, body.period_id, body.skills, body.weeks, user)
    player, period = db.get(Player, player_id), db.get(Period, body.period_id)
    shared = db.query(SharedPlan).filter_by(player_id=player_id, period_id=body.period_id).first()
    now, raw = utcnow(), fresh_token()
    replaced = bool(shared) and shared.expires_at.replace(tzinfo=timezone.utc) > now
    if not shared:
        shared = SharedPlan(player_id=player_id, period_id=body.period_id)
        db.add(shared)
    shared.plan, shared.token_hash, shared.created_by = built, digest(raw), user.id
    shared.created_at, shared.expires_at, shared.opened_at = now, now + timedelta(weeks=body.weeks, days=GRACE_DAYS), None
    record(db, team_id, user, "plan_shared", player=player.name, period=period.label, **({"replaced": True} if replaced else {}))
    db.commit()
    return {"url": f"{settings.public_base_url}/plan/{raw}", "share": share_status(shared)}


@router.delete("/teams/{team_id}/players/{player_id}/plan/share")
def revoke_plan_share(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    _player_context(db, team_id, player_id, period_id, user)
    shared = db.query(SharedPlan).filter_by(player_id=player_id, period_id=period_id).first()
    if shared:
        player, period = db.get(Player, player_id), db.get(Period, period_id)
        db.delete(shared)
        record(db, team_id, user, "plan_share_revoked", player=player.name, period=period.label)
        db.commit()
    return {"message": "Link revoked"}


def _open(db: DbSession, token: str) -> SharedPlan:
    shared = db.query(SharedPlan).filter_by(token_hash=digest(token)).first()
    if not shared:
        raise HTTPException(404, "Link unavailable")
    if shared.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(410, "This plan has expired. Ask the coach for a new link")
    return shared


@router.get("/plan/{token}")
def shared_plan(token: str, db: DbSession = Depends(get_db)):
    shared = _open(db, token)
    player, period = db.get(Player, shared.player_id), db.get(Period, shared.period_id)
    team = db.get(Team, player.team_id)
    if not shared.opened_at:
        shared.opened_at = utcnow()
        db.commit()
    return {"player": player.name, "team": team.name, "period": period.label, "created_at": shared.created_at,
            "expires_at": shared.expires_at, "plan": shared.plan}


@router.get("/plan/{token}/drills/{slug}")
def shared_plan_drill(token: str, slug: str, db: DbSession = Depends(get_db)):
    """One of the plan's drills, through the plan's link. Drills that are not in the plan are not available."""
    shared = _open(db, token)
    if slug not in {s["drill"] for s in shared.plan["slots"]}:
        raise HTTPException(404, "Drill not found")
    drill = db.query(Drill).filter_by(slug=slug, status="published").first()
    if not drill:
        raise HTTPException(404, "Drill not found")
    return drill_out(db, drill, None)

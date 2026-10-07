"""Development plans: generated from a player's priorities and saved, one per player and period. The saved plan
appears in the player report, so the report's share link is how players and parents see it."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user
from ..database import get_db
from ..matrix import document
from ..cycles import current_cycle, current_plan
from ..models import DevelopmentCycle, Period, Player, PlayerPlan, PriorityConfirmation, User, utcnow
from ..plans import plan as rules_plan
from .drills import _library, _player_context

router = APIRouter(tags=["plans"])


def build_plan(db: DbSession, team_id: int, player_id: int, period_id: int, skills: list[str], weeks: int, user: User) -> dict:
    age_group, period, skill_tags, levels = _player_context(db, team_id, player_id, period_id, user)
    labels = {s["id"]: s["label"] for section in document(db, period.matrix_version_id)["sections"] for s in section["skills"]}
    drills, drill_tags, ladder_tags, variations, votes, tags = _library(db, age_group, user)
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


def plan_skills(plan: dict) -> list[str]:
    """The priorities a plan was made for, in rank order, so the coach can tell whether it is out of date."""
    return [skill for _, skill in sorted({(i["rank"], i["skill_id"]) for i in plan["slots"] + plan["gaps"]})]


def plan_out(saved: PlayerPlan | None) -> dict:
    if not saved:
        return {"plan": None}
    return {"plan": saved.plan, "created_at": saved.created_at, "skills": plan_skills(saved.plan)}


@router.get("/teams/{team_id}/players/{player_id}/plan")
def saved_plan(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    _player_context(db, team_id, player_id, period_id, user)
    return plan_out(current_plan(db, player_id, period_id))


class PlanIn(BaseModel):
    period_id: int
    weeks: int = Field(default=4, ge=1, le=8)


@router.post("/teams/{team_id}/players/{player_id}/plan")
def generate_plan(team_id: int, player_id: int, body: PlanIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Generate a plan from the player's confirmed priorities and save it, replacing their plan for the period.
    Only saved priorities count, so the plan always matches the focus areas in the report, which shows it at once."""
    _player_context(db, team_id, player_id, body.period_id, user)
    cycle = current_cycle(db, player_id, body.period_id)
    skills = [p.skill_id for p in db.query(PriorityConfirmation).filter_by(cycle_id=cycle.id).order_by(PriorityConfirmation.rank)] if cycle else []
    if not skills:
        raise HTTPException(409, "Save the player's priorities before generating a plan")
    built = build_plan(db, team_id, player_id, body.period_id, skills, body.weeks, user)
    saved = db.query(PlayerPlan).filter_by(cycle_id=cycle.id).first()
    replaced = saved is not None
    if not saved:
        saved = PlayerPlan(player_id=player_id, period_id=body.period_id, cycle_id=cycle.id)
        db.add(saved)
    saved.plan, saved.created_by, saved.created_at = built, user.id, utcnow()
    player, period = db.get(Player, player_id), db.get(Period, body.period_id)
    record(db, team_id, user, "plan_saved", player=player.name, period=period.label, **({"replaced": True} if replaced else {}))
    db.commit()
    return plan_out(saved)


def cycle_out(db: DbSession, cycle: DevelopmentCycle, current: bool) -> dict:
    plan = db.query(PlayerPlan).filter_by(cycle_id=cycle.id).first()
    priorities = db.query(PriorityConfirmation).filter_by(cycle_id=cycle.id).order_by(PriorityConfirmation.rank).all()
    return {"id": cycle.id, "number": cycle.number, "started_at": cycle.started_at, "current": current,
            "priorities": [{"skill_id": p.skill_id, "rank": p.rank, "coach_note": p.coach_note} for p in priorities],
            "plan": plan.plan if plan else None}


@router.get("/teams/{team_id}/players/{player_id}/cycles")
def list_cycles(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The player's development cycles in a period, newest first; the first is the current one."""
    _player_context(db, team_id, player_id, period_id, user)
    cycles = db.query(DevelopmentCycle).filter_by(player_id=player_id, period_id=period_id).order_by(DevelopmentCycle.number.desc()).all()
    return [cycle_out(db, c, i == 0) for i, c in enumerate(cycles)]


class CycleIn(BaseModel):
    period_id: int


@router.post("/teams/{team_id}/players/{player_id}/cycles", status_code=201)
def start_cycle(team_id: int, player_id: int, body: CycleIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Start the next development cycle: new focus areas and a new plan, keeping the current cycle as history.
    Only once the current cycle has a saved plan, so cycles are not skipped by accident."""
    _player_context(db, team_id, player_id, body.period_id, user)
    cycle = current_cycle(db, player_id, body.period_id)
    if not cycle or not db.query(PlayerPlan).filter_by(cycle_id=cycle.id).first():
        raise HTTPException(409, "Generate a plan for the current cycle before starting the next one")
    nxt = DevelopmentCycle(player_id=player_id, period_id=body.period_id, number=cycle.number + 1, created_by=user.id)
    db.add(nxt)
    player, period = db.get(Player, player_id), db.get(Period, body.period_id)
    record(db, team_id, user, "cycle_started", player=player.name, period=period.label, number=nxt.number)
    db.commit()
    return cycle_out(db, nxt, True)

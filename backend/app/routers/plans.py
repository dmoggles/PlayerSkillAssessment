"""Development plans: generated from a player's priorities and saved, one per player and period. The saved plan
appears in the player report, so the report's share link is how players and parents see it."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user
from ..database import get_db
from ..matrix import document
from ..cycles import current_cycle, current_plan, latest_cycle_ids
from ..models import CycleCheckin, DevelopmentCycle, Period, Player, PlayerPlan, PriorityConfirmation, User, utcnow
from ..plans import plan as rules_plan, ranked
from .drills import _library, _player_context

router = APIRouter(tags=["plans"])


def _drill_data(drills, drill_tags, ladder_tags, variations, votes, tags) -> list[dict]:
    """Drills in the planner's input format."""
    return [{"slug": d.slug, "title": d.title, "home_friendly": d.home_friendly,
             "duration": [d.duration_min, d.duration_typical], "tags": drill_tags.get(d.id, {}),
             "tag_labels": {t["id"]: t["label"] for t in tags.get(d.id, [])},
             "ladder_tags": sorted(ladder_tags.get(d.id, set())),
             "variations": [{"id": v.id, "kind": v.kind, "title": v.title, "levels": [v.level_min, v.level_max]}
                            for v in variations.get(d.id, [])],
             "my_vote": votes[d.id]["mine"], "net_votes": votes[d.id]["likes"] - votes[d.id]["dislikes"]}
            for d in drills if variations.get(d.id)]


def _history(db: DbSession, player_id: int, current: DevelopmentCycle | None, catalog: dict) -> list[dict]:
    """The drills in the player's earlier plans, newest cycle first (cycles_ago 1 = the cycle before this one),
    with the version reached and that cycle's check-in for the skill."""
    rows = db.query(DevelopmentCycle, PlayerPlan, Period).join(PlayerPlan, PlayerPlan.cycle_id == DevelopmentCycle.id).join(
        Period, Period.id == DevelopmentCycle.period_id).filter(DevelopmentCycle.player_id == player_id).order_by(
        Period.created_at.desc(), Period.id.desc(), DevelopmentCycle.number.desc()).all()
    rows = [r for r in rows if not current or r[0].id != current.id]
    checkins = {(c.cycle_id, c.skill_id): c.trend for c in db.query(CycleCheckin).filter(CycleCheckin.cycle_id.in_([r[0].id for r in rows]))}
    uses = []
    for ago, (cycle, saved, _) in enumerate(rows, start=1):
        for slot in saved.plan["slots"]:
            ids = [v["id"] for v in catalog.get(slot["drill"], {}).get("variations", [])]
            last = slot["weeks"][-1]["id"] if slot["weeks"] else None
            uses.append({"drill": slot["drill"], "skill_id": slot["skill_id"], "slot": slot["slot"], "cycles_ago": ago,
                         "last_index": ids.index(last) if last in ids else 0, "checkin": checkins.get((cycle.id, slot["skill_id"]))})
    return uses


def _squad(db: DbSession, team_id: int, player_id: int, period_id: int) -> dict:
    """Training drills teammates' current plans use in this period, per skill: skill -> {drill: teammates}."""
    out = {}
    current = latest_cycle_ids(db, period_id=period_id)
    for saved in db.query(PlayerPlan).filter(PlayerPlan.cycle_id.in_(current), PlayerPlan.player_id != player_id):
        for slot in saved.plan["slots"]:
            if slot["slot"] == "club":
                bucket = out.setdefault(slot["skill_id"], {})
                bucket[slot["drill"]] = bucket.get(slot["drill"], 0) + 1
    return out


def _pins(saved_plan: dict | None) -> list[dict]:
    """The coach's choices in a saved plan, kept when it is regenerated: chosen drills and removed slots."""
    if not saved_plan:
        return []
    chosen = [{"skill_id": s["skill_id"], "slot": s["slot"], "drill": s["drill"], "start_variation_id": s["weeks"][0]["id"] if s["weeks"] else None}
              for s in saved_plan["slots"] if s.get("chosen_by") == "coach"]
    removed = [{"skill_id": g["skill_id"], "slot": g["slot"], "drill": None} for g in saved_plan["gaps"] if g["reason"] == "Removed by the coach."]
    return chosen + removed


def planner_input(db: DbSession, team_id: int, player_id: int, period_id: int, skills: list[str], weeks: int, user: User,
                  pins: list[dict] | None = None) -> dict:
    """Everything the planner needs, as plain data."""
    age_group, period, skill_tags, levels = _player_context(db, team_id, player_id, period_id, user)
    labels = {s["id"]: s["label"] for section in document(db, period.matrix_version_id)["sections"] for s in section["skills"]}
    drills = _drill_data(*_library(db, age_group, user))
    catalog = {d["slug"]: d for d in _drill_data(*_library(db, None, user))}  # any drill a coach may choose
    cycle = current_cycle(db, player_id, period_id)
    saved = db.query(PlayerPlan).filter_by(cycle_id=cycle.id).first() if cycle else None
    return {
        "weeks": weeks,
        "priorities": [{"rank": rank, "skill_id": skill_id, "label": labels.get(skill_id, skill_id),
                        "level": levels.get(skill_id), "tags": skill_tags.get(skill_id, {})}
                       for rank, skill_id in enumerate(dict.fromkeys(skills), start=1)],
        "drills": drills, "catalog": catalog,
        "history": _history(db, player_id, cycle, catalog),
        "squad": _squad(db, team_id, player_id, period_id),
        "pins": _pins(saved.plan if saved else None) if pins is None else pins,
    }


def build_plan(db: DbSession, team_id: int, player_id: int, period_id: int, skills: list[str], weeks: int, user: User) -> dict:
    return rules_plan(planner_input(db, team_id, player_id, period_id, skills, weeks, user))


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
    checkins = {c.skill_id: {"trend": c.trend, "note": c.note} for c in db.query(CycleCheckin).filter_by(cycle_id=cycle.id)}
    return {"id": cycle.id, "number": cycle.number, "started_at": cycle.started_at, "current": current,
            "priorities": [{"skill_id": p.skill_id, "rank": p.rank, "coach_note": p.coach_note} for p in priorities],
            "plan": plan.plan if plan else None, "checkin": checkins}


@router.get("/teams/{team_id}/players/{player_id}/cycles")
def list_cycles(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The player's development cycles in a period, newest first; the first is the current one."""
    _player_context(db, team_id, player_id, period_id, user)
    cycles = db.query(DevelopmentCycle).filter_by(player_id=player_id, period_id=period_id).order_by(DevelopmentCycle.number.desc()).all()
    return [cycle_out(db, c, i == 0) for i, c in enumerate(cycles)]


class CheckinIn(BaseModel):
    skill_id: str
    trend: Literal["better", "same", "worse"]
    note: str | None = Field(default=None, max_length=300)


class CycleIn(BaseModel):
    period_id: int
    # How the ending cycle's focus skills went; empty when the coach skips the check-in.
    checkin: list[CheckinIn] = Field(default=[], max_length=5)


@router.post("/teams/{team_id}/players/{player_id}/cycles", status_code=201)
def start_cycle(team_id: int, player_id: int, body: CycleIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Start the next development cycle: new focus areas and a new plan, keeping the current cycle as history.
    Only once the current cycle has a saved plan, so cycles are not skipped by accident."""
    _player_context(db, team_id, player_id, body.period_id, user)
    cycle = current_cycle(db, player_id, body.period_id)
    if not cycle or not db.query(PlayerPlan).filter_by(cycle_id=cycle.id).first():
        raise HTTPException(409, "Generate a plan for the current cycle before starting the next one")
    focus = {p.skill_id for p in db.query(PriorityConfirmation).filter_by(cycle_id=cycle.id)}
    skills = [c.skill_id for c in body.checkin]
    if len(skills) != len(set(skills)) or not set(skills) <= focus:
        raise HTTPException(422, "A check-in covers the current cycle's focus skills, once each")
    for c in body.checkin:
        db.add(CycleCheckin(cycle_id=cycle.id, skill_id=c.skill_id, trend=c.trend, note=(c.note or "").strip() or None, created_by=user.id))
    nxt = DevelopmentCycle(player_id=player_id, period_id=body.period_id, number=cycle.number + 1, created_by=user.id)
    db.add(nxt)
    player, period = db.get(Player, player_id), db.get(Period, body.period_id)
    record(db, team_id, user, "cycle_started", player=player.name, period=period.label, number=nxt.number, checked_in=bool(body.checkin))
    db.commit()
    return cycle_out(db, nxt, True)


def _editable(db: DbSession, team_id: int, player_id: int, period_id: int, user: User) -> tuple[PlayerPlan, list[str]]:
    _player_context(db, team_id, player_id, period_id, user)
    saved = current_plan(db, player_id, period_id)
    if not saved:
        raise HTTPException(409, "Generate a plan before changing it")
    return saved, plan_skills(saved.plan)


@router.get("/teams/{team_id}/players/{player_id}/plan/alternatives")
def plan_alternatives(team_id: int, player_id: int, period_id: int, skill_id: str, slot: Literal["club", "home"],
                      db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The planner's ranked candidates for one slot of the saved plan, each with why it scores as it does."""
    saved, skills = _editable(db, team_id, player_id, period_id, user)
    if skill_id not in skills:
        raise HTTPException(404, "Not a priority in this plan")
    data = planner_input(db, team_id, player_id, period_id, skills, saved.plan.get("weeks", 4), user)
    priority = next(p for p in data["priorities"] if p["skill_id"] == skill_id)
    return [{"slug": c["drill"]["slug"], "title": c["drill"]["title"], "score": c["score"], "notes": c["notes"],
             "variations": c["drill"]["variations"]} for c in ranked(priority, slot, data)[:8]]


class SlotIn(BaseModel):
    period_id: int
    skill_id: str
    slot: Literal["club", "home"]
    action: Literal["choose", "remove", "reset"]
    drill: str | None = None
    start_variation_id: int | None = None


@router.put("/teams/{team_id}/players/{player_id}/plan/slot")
def edit_plan_slot(team_id: int, player_id: int, body: SlotIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Override one slot of the saved plan: choose a drill (and starting version), remove the slot, or reset it to
    the planner's choice. Only that slot changes; the choice is kept when the plan is regenerated."""
    saved, skills = _editable(db, team_id, player_id, body.period_id, user)
    if body.skill_id not in skills:
        raise HTTPException(404, "Not a priority in this plan")
    weeks = saved.plan.get("weeks", 4)
    pins = [p for p in _pins(saved.plan) if (p["skill_id"], p["slot"]) != (body.skill_id, body.slot)]
    if body.action == "choose":
        data = planner_input(db, team_id, player_id, body.period_id, skills, weeks, user, pins)
        drill = data["catalog"].get(body.drill or "")
        if not drill:
            raise HTTPException(404, "Drill not found")
        if body.start_variation_id is not None and body.start_variation_id not in {v["id"] for v in drill["variations"]}:
            raise HTTPException(422, "That version belongs to another drill")
        pins.append({"skill_id": body.skill_id, "slot": body.slot, "drill": drill["slug"], "start_variation_id": body.start_variation_id})
    elif body.action == "remove":
        pins.append({"skill_id": body.skill_id, "slot": body.slot, "drill": None})
    fresh = rules_plan(planner_input(db, team_id, player_id, body.period_id, skills, weeks, user, pins))
    # Only the edited slot changes; the rest of the saved plan stays as it was.
    key = (body.skill_id, body.slot)
    keep = lambda items: [i for i in items if (i["skill_id"], i["slot"]) != key]
    new = lambda items: [i for i in items if (i["skill_id"], i["slot"]) == key]
    order = lambda i: (i["rank"], i["slot"] != "club")
    saved.plan = {**saved.plan, "slots": sorted(keep(saved.plan["slots"]) + new(fresh["slots"]), key=order),
                  "gaps": sorted(keep(saved.plan["gaps"]) + new(fresh["gaps"]), key=order)}
    player, period = db.get(Player, player_id), db.get(Period, body.period_id)
    record(db, team_id, user, "plan_slot_changed", player=player.name, period=period.label, skill=body.skill_id, slot=body.slot,
           change=body.action, **({"drill": body.drill} if body.action == "choose" else {}))
    db.commit()
    return plan_out(saved)

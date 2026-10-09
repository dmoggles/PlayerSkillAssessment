"""Confirmed priorities (per development cycle) and squad-level insights."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..auth import current_user, require_member
from ..cycles import current_priorities, ensure_cycle
from ..database import get_db
from ..insights import POSITION_ORDER, team_insights
from ..matrix import period_document, skill_set
from ..models import Assessment, PriorityConfirmation, User
from .assessments import require_active_player
from .teams import scoped_period, scoped_player


router = APIRouter(tags=["priorities"])


class PriorityIn(BaseModel):
    skill_id: str
    rank: int = Field(ge=1, le=3)
    algorithm_suggested: bool = True
    coach_note: str | None = Field(default=None, max_length=500)


class PrioritiesIn(BaseModel):
    priorities: list[PriorityIn]


@router.get("/teams/{team_id}/insights")
def insights(team_id: int, period_id: int | None = None, position: str | None = None, group: int | None = Query(default=None, ge=5, le=21),
             db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Squad trends across periods, plus common priorities and position groups for the given period.
    position limits trends and priorities to one primary position; group limits everything to one playing group."""
    require_member(team_id, db, user)
    if position is not None and position not in POSITION_ORDER:
        raise HTTPException(422, "Unknown position")
    return team_insights(db, team_id, scoped_period(db, team_id, period_id) if period_id else None, position, group)


@router.get("/teams/{team_id}/priorities")
def get_priorities(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_player(db, team_id, player_id)
    scoped_period(db, team_id, period_id)
    rows = current_priorities(db, player_id, period_id)
    return [{"skill_id": r.skill_id, "rank": r.rank, "algorithm_suggested": r.algorithm_suggested, "coach_note": r.coach_note} for r in rows]


@router.put("/teams/{team_id}/priorities")
def set_priorities(team_id: int, player_id: int, period_id: int, body: PrioritiesIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    require_active_player(db, team_id, player_id)
    doc = period_document(db, scoped_period(db, team_id, period_id))
    coach = db.query(Assessment).filter_by(player_id=player_id, period_id=period_id, assessor="coach").first()
    skills = skill_set(doc, coach.position) if coach else set()
    if not coach or skills - {r.skill_id for r in coach.ratings if r.score is not None}:
        raise HTTPException(409, "Complete the coach assessment first")
    ids = [p.skill_id for p in body.priorities]
    ranks = [p.rank for p in body.priorities]
    if len(ids) > 3 or len(ids) != len(set(ids)) or sorted(ranks) != list(range(1, len(ranks) + 1)) or not set(ids).issubset(skills):
        raise HTTPException(422, "Invalid priorities")
    cycle = ensure_cycle(db, player_id, period_id, user)
    db.query(PriorityConfirmation).filter_by(cycle_id=cycle.id).delete()
    db.flush()
    for p in body.priorities:
        db.add(PriorityConfirmation(player_id=player_id, period_id=period_id, cycle_id=cycle.id, **p.model_dump()))
    db.commit()
    return get_priorities(team_id, player_id, period_id, db, user)

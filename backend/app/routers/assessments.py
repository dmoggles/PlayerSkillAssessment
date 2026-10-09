from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from ..auth import current_user, require_member
from ..cycles import latest_cycle_ids
from ..database import get_db
from ..matrix import annotate_history, period_document, position_ids, rendered, skill_set, starter_version, version_visible_to_team
from ..models import Assessment, AssessmentRevision, CycleCheckin, DevelopmentCycle, Period, Player, PlayerGroup, PriorityConfirmation, Rating, Team, User, utcnow
from .teams import scoped_period, scoped_player


router = APIRouter(tags=["assessments"])


class RatingIn(BaseModel):
    skill_id: str
    score: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)
    # Still the previous period's score, not yet reviewed by the coach this period.
    carried: bool = False


class CoachAssessmentIn(BaseModel):
    player_id: int
    period_id: int
    version: int = Field(ge=0)
    primary_position: str
    secondary_position: str | None = None
    secondary_position_frequency: str | None = None
    note: str | None = Field(default=None, max_length=1000)
    ratings: list[RatingIn]


def clean_note(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def validate_ratings(ratings: list[RatingIn], skills: set[str]):
    ids = [r.skill_id for r in ratings]
    if len(ids) != len(set(ids)) or not set(ids).issubset(skills):
        raise HTTPException(422, "Invalid or repeated skill ID")


def assessment_out(a: Assessment | None):
    if not a:
        return None
    return {"id": a.id, "player_id": a.player_id, "player_name": a.player_name,
            "period_id": a.period_id, "assessor": a.assessor, "position": a.position,
            "primary_position": a.primary_position, "secondary_position": a.secondary_position,
            "secondary_position_frequency": a.secondary_position_frequency,
            "matrix_version": a.matrix_version, "version": a.version, "updated_by": a.updated_by,
            "created_at": a.created_at, "updated_at": a.updated_at,
            "note": a.note,
            "ratings": [{"skill_id": r.skill_id, "score": r.score, "note": r.note, "carried": r.carried} for r in a.ratings]}


def require_active_player(db: DbSession, team_id: int, player_id: int) -> Player:
    player = scoped_player(db, team_id, player_id)
    if not player.active:
        raise HTTPException(409, "Archived players are read-only. Restore the player to make changes")
    return player


def scoped_assessment(db: DbSession, team_id: int, player_id: int, period_id: int, assessor: str):
    scoped_player(db, team_id, player_id)
    scoped_period(db, team_id, period_id)
    return db.query(Assessment).filter_by(player_id=player_id, period_id=period_id, assessor=assessor).first()


@router.get("/skill-matrix")
def skill_matrix(db: DbSession = Depends(get_db)):
    """The starter template's latest version, with neutral (mixed) wording."""
    return rendered(db, starter_version(db).id, "mixed")


@router.get("/teams/{team_id}/matrix-versions/{version_id}")
def matrix_version(team_id: int, version_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    if not version_visible_to_team(db, team_id, version_id):
        raise HTTPException(404, "Matrix version not found")
    return {**rendered(db, version_id, db.get(Team, team_id).player_gender), "version_id": version_id}


def assessment_state(position, primary, secondary, frequency, note, ratings) -> tuple:
    """What a save would record, for spotting a save with no changes. Skills with neither a score nor a note
    count as not rated, however they were sent."""
    rated = sorted((r["skill_id"], r["score"], r["note"], bool(r.get("carried"))) for r in ratings if r["score"] is not None or r["note"])
    return position, primary, secondary, frequency, note, rated


@router.put("/teams/{team_id}/assessments/coach")
def save_coach_assessment(team_id: int, body: CoachAssessmentIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    require_active_player(db, team_id, body.player_id)
    doc = period_document(db, scoped_period(db, team_id, body.period_id))
    positions = position_ids(doc)
    if body.primary_position not in positions or (body.secondary_position and body.secondary_position not in positions):
        raise HTTPException(422, "Invalid position")
    if body.secondary_position == body.primary_position:
        raise HTTPException(422, "Secondary position must differ")
    if body.secondary_position and body.secondary_position_frequency not in ("rarely", "sometimes", "often"):
        raise HTTPException(422, "Invalid secondary position frequency")
    position = "goalkeeper" if body.primary_position == "goalkeeper" else "outfield"
    validate_ratings(body.ratings, skill_set(doc, position))
    a = db.query(Assessment).filter_by(player_id=body.player_id, period_id=body.period_id, assessor="coach").with_for_update(of=Assessment).first()
    if a and a.version != body.version or not a and body.version != 0:
        raise HTTPException(409, "Assessment changed. Reload before saving")
    ratings = [{"skill_id": r.skill_id, "score": r.score, "note": clean_note(r.note), "carried": r.carried and r.score is not None} for r in body.ratings]
    secondary_frequency = body.secondary_position_frequency if body.secondary_position else None
    if a and assessment_state(a.position, a.primary_position, a.secondary_position, a.secondary_position_frequency, a.note,
                              [{"skill_id": r.skill_id, "score": r.score, "note": r.note, "carried": r.carried} for r in a.ratings]) == assessment_state(
            position, body.primary_position, body.secondary_position, secondary_frequency, clean_note(body.note), ratings):
        # Nothing changed: no new version, no revision, nothing written.
        return {**assessment_out(a), "unchanged": True}
    if not a:
        a = Assessment(player_id=body.player_id, period_id=body.period_id, assessor="coach", position=position,
                       version=1, updated_by=user.id, matrix_version=doc["meta"]["version"])
        db.add(a)
        db.flush()
    else:
        a.version += 1
        db.query(Rating).filter_by(assessment_id=a.id).delete(synchronize_session=False)
        db.expire(a, ["ratings"])
    a.position = position
    a.primary_position = body.primary_position
    a.secondary_position = body.secondary_position
    a.secondary_position_frequency = secondary_frequency
    a.note = clean_note(body.note)
    a.updated_by = user.id
    a.updated_at = utcnow()
    for r in ratings:
        db.add(Rating(assessment_id=a.id, **r))
    snapshot = {"position": position, "primary_position": a.primary_position,
                "secondary_position": a.secondary_position, "secondary_position_frequency": a.secondary_position_frequency,
                "note": a.note, "ratings": ratings}
    db.add(AssessmentRevision(assessment_id=a.id, version=a.version, editor_id=user.id, snapshot=snapshot))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Assessment changed. Reload before saving")
    db.refresh(a)
    return assessment_out(a)


@router.get("/teams/{team_id}/assessments/coach")
def get_coach_assessment(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    return assessment_out(scoped_assessment(db, team_id, player_id, period_id, "coach"))


def visible_assessors(db: DbSession, team_id: int) -> tuple[str, ...]:
    """Self-assessments are hidden everywhere while the team has self-assessment turned off. They are kept, and
    come back if it is turned on again."""
    return ("coach", "player") if db.get(Team, team_id).self_assessment_enabled else ("coach",)


@router.get("/teams/{team_id}/assessments/compare")
def compare(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_player(db, team_id, player_id)
    scoped_period(db, team_id, period_id)
    rows = db.query(Assessment).filter(Assessment.player_id == player_id, Assessment.period_id == period_id,
                                       Assessment.assessor.in_(visible_assessors(db, team_id))).all()
    return {"coach": assessment_out(next((a for a in rows if a.assessor == "coach"), None)),
            "player": assessment_out(next((a for a in rows if a.assessor == "player"), None))}


@router.get("/teams/{team_id}/assessments/period/{period_id}")
def period_assessments(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_period(db, team_id, period_id)
    rows = db.query(Assessment).join(Player).filter(Player.team_id == team_id, Assessment.period_id == period_id,
                                                    Assessment.assessor.in_(visible_assessors(db, team_id))).all()
    return [assessment_out(a) for a in rows]


@router.get("/teams/{team_id}/players/{player_id}/history")
def player_history(team_id: int, player_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_player(db, team_id, player_id)
    rows = db.query(Assessment, Period).join(Period, Period.id == Assessment.period_id).filter(
        Assessment.player_id == player_id, Period.team_id == team_id,
        Assessment.assessor.in_(visible_assessors(db, team_id))).order_by(Period.created_at, Period.id).all()
    # Each period's priorities are its current cycle's; earlier cycles are listed separately.
    current = latest_cycle_ids(db, player_id=player_id)
    priorities = db.query(PriorityConfirmation).filter(PriorityConfirmation.player_id == player_id,
                                                       PriorityConfirmation.cycle_id.in_(current)).all()
    by_period, versions = {}, {}
    for a, p in rows:
        versions[p.id] = p.matrix_version_id
        item = by_period.setdefault(p.id, {"period_id": p.id, "label": p.label, "assessments": {}, "priorities": []})
        item["assessments"][a.assessor] = assessment_out(a)
    for priority in priorities:
        if priority.period_id in by_period:
            by_period[priority.period_id]["priorities"].append({"skill_id": priority.skill_id, "rank": priority.rank, "coach_note": priority.coach_note})
    add_playing_groups(db, player_id, by_period.values())
    add_earlier_cycles(db, player_id, by_period.values())
    return annotate_history(db, list(by_period.values()), [versions[pid] for pid in by_period])


def add_earlier_cycles(db: DbSession, player_id: int, rows) -> None:
    """Each history row gets its period's earlier cycles: number, start, priorities in rank order and check-in."""
    cycles = db.query(DevelopmentCycle).filter_by(player_id=player_id).order_by(DevelopmentCycle.number).all()
    latest = {}
    for c in cycles:
        latest[c.period_id] = max(latest.get(c.period_id, 0), c.number)
    earlier = [c for c in cycles if c.number < latest[c.period_id]]
    priorities = {}
    for p in db.query(PriorityConfirmation).filter(PriorityConfirmation.cycle_id.in_([c.id for c in earlier])).order_by(PriorityConfirmation.rank):
        priorities.setdefault(p.cycle_id, []).append({"skill_id": p.skill_id, "rank": p.rank})
    checkins = {}
    for c in db.query(CycleCheckin).filter(CycleCheckin.cycle_id.in_([c.id for c in earlier])):
        checkins.setdefault(c.cycle_id, {})[c.skill_id] = {"trend": c.trend, "note": c.note}
    for row in rows:
        row["earlier_cycles"] = [{"number": c.number, "started_at": c.started_at, "priorities": priorities.get(c.id, []),
                                  "checkin": checkins.get(c.id, {})} for c in earlier if c.period_id == row["period_id"]]


def add_playing_groups(db: DbSession, player_id: int, rows) -> None:
    """Each history row gets the player's playing group in that period (or None), so views can flag a change of
    cohort: ratings before and after a move up are judged against different players."""
    groups = {g.period_id: g.age_group for g in db.query(PlayerGroup).filter_by(player_id=player_id)}
    for row in rows:
        row["age_group"] = groups.get(row["period_id"])


@router.get("/teams/{team_id}/assessments/{assessment_id}/revisions")
def revisions(team_id: int, assessment_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    a = db.query(Assessment).join(Player).filter(Assessment.id == assessment_id, Player.team_id == team_id, Assessment.assessor == "coach").first()
    if not a:
        raise HTTPException(404, "Assessment not found")
    rows = db.query(AssessmentRevision, User).join(User, User.id == AssessmentRevision.editor_id).filter(
        AssessmentRevision.assessment_id == assessment_id).order_by(AssessmentRevision.version).all()
    return [{"version": r.version, "editor": u.email, "created_at": r.created_at, "snapshot": r.snapshot} for r, u in rows]

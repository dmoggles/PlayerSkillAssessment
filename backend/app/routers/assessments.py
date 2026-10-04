import json
from datetime import timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from ..auth import current_user, digest, fresh_token, require_member
from ..config import settings
from ..database import get_db
from ..models import Assessment, AssessmentRevision, Period, Player, PriorityConfirmation, Rating, SelfLink, Team, User, utcnow
from .teams import scoped_period, scoped_player


router = APIRouter(tags=["assessments"])
MATRIX = json.loads((Path(__file__).parents[2] / "bobtails_skill_matrix.json").read_text())
SKILLS = {kind: {skill["id"] for section in MATRIX["sections"]
                 if ("goalkeeper" in section["applies_to"] if kind == "goalkeeper" else any(p in section["applies_to"] for p in ("defender", "midfielder", "winger", "striker")))
                 for skill in section["skills"]} for kind in ("outfield", "goalkeeper")}
POSITIONS = {p["id"] for p in MATRIX["positions"]}


class RatingIn(BaseModel):
    skill_id: str
    score: int | None = Field(default=None, ge=1, le=5)


class CoachAssessmentIn(BaseModel):
    player_id: int
    period_id: int
    version: int = Field(ge=0)
    primary_position: str
    secondary_position: str | None = None
    secondary_position_frequency: str | None = None
    ratings: list[RatingIn]


class SelfAssessmentIn(BaseModel):
    position: str
    ratings: list[RatingIn]


class PriorityIn(BaseModel):
    skill_id: str
    rank: int = Field(ge=1, le=3)
    algorithm_suggested: bool = True
    coach_note: str | None = Field(default=None, max_length=500)


class PrioritiesIn(BaseModel):
    priorities: list[PriorityIn]


def validate_ratings(ratings: list[RatingIn], position: str):
    ids = [r.skill_id for r in ratings]
    if len(ids) != len(set(ids)) or not set(ids).issubset(SKILLS[position]):
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
            "ratings": [{"skill_id": r.skill_id, "score": r.score} for r in a.ratings]}


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
def skill_matrix():
    return {**MATRIX, "meta": {**MATRIX["meta"], "team": "Starter skill matrix", "season": "", "age_group": ""}}


@router.put("/teams/{team_id}/assessments/coach")
def save_coach_assessment(team_id: int, body: CoachAssessmentIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    require_active_player(db, team_id, body.player_id)
    scoped_period(db, team_id, body.period_id)
    if body.primary_position not in POSITIONS or (body.secondary_position and body.secondary_position not in POSITIONS):
        raise HTTPException(422, "Invalid position")
    if body.secondary_position == body.primary_position:
        raise HTTPException(422, "Secondary position must differ")
    if body.secondary_position and body.secondary_position_frequency not in ("rarely", "sometimes", "often"):
        raise HTTPException(422, "Invalid secondary position frequency")
    position = "goalkeeper" if body.primary_position == "goalkeeper" else "outfield"
    validate_ratings(body.ratings, position)
    a = db.query(Assessment).filter_by(player_id=body.player_id, period_id=body.period_id, assessor="coach").with_for_update(of=Assessment).first()
    if a and a.version != body.version or not a and body.version != 0:
        raise HTTPException(409, "Assessment changed. Reload before saving")
    if not a:
        a = Assessment(player_id=body.player_id, period_id=body.period_id, assessor="coach", position=position,
                       version=1, updated_by=user.id, matrix_version=MATRIX["meta"]["version"])
        db.add(a)
        db.flush()
    else:
        a.version += 1
        db.query(Rating).filter_by(assessment_id=a.id).delete(synchronize_session=False)
        db.expire(a, ["ratings"])
    a.position = position
    a.primary_position = body.primary_position
    a.secondary_position = body.secondary_position
    a.secondary_position_frequency = body.secondary_position_frequency if body.secondary_position else None
    a.updated_by = user.id
    a.updated_at = utcnow()
    for r in body.ratings:
        db.add(Rating(assessment_id=a.id, skill_id=r.skill_id, score=r.score))
    snapshot = {"position": position, "primary_position": a.primary_position,
                "secondary_position": a.secondary_position, "secondary_position_frequency": a.secondary_position_frequency,
                "ratings": [r.model_dump() for r in body.ratings]}
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


@router.get("/teams/{team_id}/assessments/compare")
def compare(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_player(db, team_id, player_id)
    scoped_period(db, team_id, period_id)
    rows = db.query(Assessment).filter_by(player_id=player_id, period_id=period_id).all()
    return {"coach": assessment_out(next((a for a in rows if a.assessor == "coach"), None)),
            "player": assessment_out(next((a for a in rows if a.assessor == "player"), None))}


@router.get("/teams/{team_id}/assessments/period/{period_id}")
def period_assessments(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_period(db, team_id, period_id)
    rows = db.query(Assessment).join(Player).filter(Player.team_id == team_id, Assessment.period_id == period_id).all()
    return [assessment_out(a) for a in rows]


@router.get("/teams/{team_id}/players/{player_id}/history")
def player_history(team_id: int, player_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_player(db, team_id, player_id)
    rows = db.query(Assessment, Period).join(Period, Period.id == Assessment.period_id).filter(
        Assessment.player_id == player_id, Period.team_id == team_id).order_by(Period.created_at, Period.id).all()
    priorities = db.query(PriorityConfirmation).filter_by(player_id=player_id).all()
    by_period = {}
    for a, p in rows:
        item = by_period.setdefault(p.id, {"period_id": p.id, "label": p.label, "assessments": {}, "priorities": []})
        item["assessments"][a.assessor] = assessment_out(a)
    for priority in priorities:
        if priority.period_id in by_period:
            by_period[priority.period_id]["priorities"].append({"skill_id": priority.skill_id, "rank": priority.rank, "coach_note": priority.coach_note})
    return list(by_period.values())


@router.get("/teams/{team_id}/assessments/{assessment_id}/revisions")
def revisions(team_id: int, assessment_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    a = db.query(Assessment).join(Player).filter(Assessment.id == assessment_id, Player.team_id == team_id, Assessment.assessor == "coach").first()
    if not a:
        raise HTTPException(404, "Assessment not found")
    rows = db.query(AssessmentRevision, User).join(User, User.id == AssessmentRevision.editor_id).filter(
        AssessmentRevision.assessment_id == assessment_id).order_by(AssessmentRevision.version).all()
    return [{"version": r.version, "editor": u.email, "created_at": r.created_at, "snapshot": r.snapshot} for r, u in rows]


@router.get("/teams/{team_id}/priorities")
def get_priorities(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_player(db, team_id, player_id)
    scoped_period(db, team_id, period_id)
    rows = db.query(PriorityConfirmation).filter_by(player_id=player_id, period_id=period_id).order_by(PriorityConfirmation.rank).all()
    return [{"skill_id": r.skill_id, "rank": r.rank, "algorithm_suggested": r.algorithm_suggested, "coach_note": r.coach_note} for r in rows]


@router.put("/teams/{team_id}/priorities")
def set_priorities(team_id: int, player_id: int, period_id: int, body: PrioritiesIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    require_active_player(db, team_id, player_id)
    scoped_period(db, team_id, period_id)
    coach = db.query(Assessment).filter_by(player_id=player_id, period_id=period_id, assessor="coach").first()
    if not coach or set(SKILLS[coach.position]) - {r.skill_id for r in coach.ratings if r.score is not None}:
        raise HTTPException(409, "Complete the coach assessment first")
    ids = [p.skill_id for p in body.priorities]
    ranks = [p.rank for p in body.priorities]
    if len(ids) > 3 or len(ids) != len(set(ids)) or sorted(ranks) != list(range(1, len(ranks) + 1)) or not set(ids).issubset(SKILLS[coach.position]):
        raise HTTPException(422, "Invalid priorities")
    db.query(PriorityConfirmation).filter_by(player_id=player_id, period_id=period_id).delete()
    for p in body.priorities:
        db.add(PriorityConfirmation(player_id=player_id, period_id=period_id, **p.model_dump()))
    db.commit()
    return get_priorities(team_id, player_id, period_id, db, user)


class SelfLinksIn(BaseModel):
    player_ids: list[int] | None = None


def ensure_self_assessment_open(db: DbSession, team_id: int, period: Period):
    if not db.get(Team, team_id).self_assessment_enabled or not period.is_active:
        raise HTTPException(409, "Self-assessment is unavailable")


def issue_link(db: DbSession, player: Player, period: Period) -> dict:
    """Create or replace the player's link for the period; the raw token is only returned here."""
    raw = fresh_token()
    now = utcnow()
    row = db.query(SelfLink).filter_by(player_id=player.id, period_id=period.id).first()
    if not row:
        row = SelfLink(player_id=player.id, period_id=period.id)
        db.add(row)
    row.token_hash = digest(raw)
    row.issued_at = now
    row.expires_at = now + timedelta(days=7)
    row.used_at = None
    row.opened_at = None
    return {"player_id": player.id, "player_name": player.name,
            "url": f"{settings.public_base_url}/self/{raw}", "expires_at": row.expires_at}


def link_status(link: SelfLink | None, submission: Assessment | None, now) -> str:
    if submission:
        return "submitted"
    if not link:
        return "not_sent"
    if link.expires_at.replace(tzinfo=timezone.utc) <= now:
        return "expired"
    return "opened" if link.opened_at else "sent"


@router.post("/teams/{team_id}/players/{player_id}/periods/{period_id}/self-link")
def issue_self_link(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    period = scoped_period(db, team_id, period_id)
    ensure_self_assessment_open(db, team_id, period)
    if not player.active:
        raise HTTPException(409, "Self-assessment is unavailable")
    if db.query(Assessment).filter_by(player_id=player_id, period_id=period_id, assessor="player").first():
        raise HTTPException(409, "Player has already submitted")
    issued = issue_link(db, player, period)
    db.commit()
    return {"url": issued["url"], "expires_at": issued["expires_at"]}


@router.get("/teams/{team_id}/periods/{period_id}/self-links")
def self_link_board(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_period(db, team_id, period_id)
    players = db.query(Player).filter_by(team_id=team_id, active=True).order_by(Player.name).all()
    ids = [p.id for p in players]
    links = {l.player_id: l for l in db.query(SelfLink).filter(SelfLink.period_id == period_id, SelfLink.player_id.in_(ids))}
    submissions = {a.player_id: a for a in db.query(Assessment).filter(
        Assessment.period_id == period_id, Assessment.assessor == "player", Assessment.player_id.in_(ids))}
    now = utcnow()
    rows = []
    for p in players:
        link, submission = links.get(p.id), submissions.get(p.id)
        rows.append({"player_id": p.id, "player_name": p.name, "status": link_status(link, submission, now),
                     "issued_at": link.issued_at if link else None, "expires_at": link.expires_at if link else None,
                     "opened_at": link.opened_at if link else None,
                     "submitted_at": submission.created_at if submission else None})
    return rows


@router.post("/teams/{team_id}/periods/{period_id}/self-links")
def issue_self_links(team_id: int, period_id: int, body: SelfLinksIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Issue links in bulk. Without player_ids, covers every active player who has neither submitted nor holds a live link."""
    require_member(team_id, db, user)
    period = scoped_period(db, team_id, period_id)
    ensure_self_assessment_open(db, team_id, period)
    board = {row["player_id"]: row for row in self_link_board(team_id, period_id, db, user)}
    if body.player_ids is None:
        targets = [pid for pid, row in board.items() if row["status"] in ("not_sent", "expired")]
    else:
        targets = list(dict.fromkeys(body.player_ids))
        for pid in targets:
            if pid not in board:
                raise HTTPException(404, "Player not found or archived")
            if board[pid]["status"] == "submitted":
                raise HTTPException(409, f"{board[pid]['player_name']} has already submitted")
    players = {p.id: p for p in db.query(Player).filter(Player.id.in_(targets))}
    issued = [issue_link(db, players[pid], period) for pid in targets]
    db.commit()
    return {"links": issued}


@router.delete("/teams/{team_id}/players/{player_id}/periods/{period_id}/self-link")
def revoke_self_link(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    scoped_player(db, team_id, player_id)
    scoped_period(db, team_id, period_id)
    db.query(SelfLink).filter_by(player_id=player_id, period_id=period_id).delete()
    db.commit()
    return {"message": "Link revoked"}


def valid_self_link(db: DbSession, raw: str, lock: bool = False):
    query = db.query(SelfLink, Player, Period, Team).join(Player, Player.id == SelfLink.player_id).join(
        Period, Period.id == SelfLink.period_id).join(Team, Team.id == Player.team_id).filter(SelfLink.token_hash == digest(raw), Period.team_id == Team.id)
    if lock:
        query = query.with_for_update(of=SelfLink)
    result = query.first()
    if not result:
        raise HTTPException(404, "Link unavailable")
    link, player, period, team = result
    if link.used_at or link.expires_at.replace(tzinfo=timezone.utc) <= utcnow() or not period.is_active or not team.self_assessment_enabled or not player.active:
        raise HTTPException(410, "Link expired or unavailable")
    return link, player, period, team


@router.get("/self/{token}")
def self_link_info(token: str, db: DbSession = Depends(get_db)):
    link, player, period, team = valid_self_link(db, token)
    if not link.opened_at:
        link.opened_at = utcnow()
        db.commit()
    return {"team": team.name, "player": player.name, "period": period.label, "expires_at": link.expires_at}


@router.post("/self/{token}", status_code=201)
def submit_self(token: str, body: SelfAssessmentIn, db: DbSession = Depends(get_db)):
    link, player, period, _ = valid_self_link(db, token, lock=True)
    if body.position not in ("outfield", "goalkeeper"):
        raise HTTPException(422, "Invalid position")
    validate_ratings(body.ratings, body.position)
    if db.query(Assessment).filter_by(player_id=player.id, period_id=period.id, assessor="player").first():
        raise HTTPException(409, "Already submitted")
    a = Assessment(player_id=player.id, period_id=period.id, assessor="player", position=body.position,
                   matrix_version=MATRIX["meta"]["version"])
    db.add(a)
    db.flush()
    for r in body.ratings:
        db.add(Rating(assessment_id=a.id, skill_id=r.skill_id, score=r.score))
    link.used_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Already submitted")
    db.refresh(a)
    return assessment_out(a)

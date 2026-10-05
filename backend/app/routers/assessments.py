from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, digest, fresh_token, require_member
from ..config import settings
from ..database import get_db
from ..matrix import document, period_document, position_ids, skill_set, starter_version, version_visible_to_team
from ..models import Assessment, AssessmentRevision, Period, Player, PlayerReport, PriorityConfirmation, Rating, SelfLink, Team, User, utcnow
from .teams import scoped_period, scoped_player


router = APIRouter(tags=["assessments"])


class RatingIn(BaseModel):
    skill_id: str
    score: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)


class CoachAssessmentIn(BaseModel):
    player_id: int
    period_id: int
    version: int = Field(ge=0)
    primary_position: str
    secondary_position: str | None = None
    secondary_position_frequency: str | None = None
    note: str | None = Field(default=None, max_length=1000)
    ratings: list[RatingIn]


class SelfAssessmentIn(BaseModel):
    position: str
    ratings: list[RatingIn]


class PriorityIn(BaseModel):
    skill_id: str
    rank: int = Field(ge=1, le=3)
    algorithm_suggested: bool = True
    coach_note: str | None = Field(default=None, max_length=500)


class ReportIn(BaseModel):
    message: str | None = Field(default=None, max_length=1000)


class PrioritiesIn(BaseModel):
    priorities: list[PriorityIn]


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
            "ratings": [{"skill_id": r.skill_id, "score": r.score, "note": r.note} for r in a.ratings]}


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
    """The starter template's latest version."""
    return document(db, starter_version(db).id)


@router.get("/teams/{team_id}/matrix-versions/{version_id}")
def matrix_version(team_id: int, version_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    if not version_visible_to_team(db, team_id, version_id):
        raise HTTPException(404, "Matrix version not found")
    return {**document(db, version_id), "version_id": version_id}


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
    a.secondary_position_frequency = body.secondary_position_frequency if body.secondary_position else None
    a.note = clean_note(body.note)
    a.updated_by = user.id
    a.updated_at = utcnow()
    ratings = [{"skill_id": r.skill_id, "score": r.score, "note": clean_note(r.note)} for r in body.ratings]
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


def report_payload(db: DbSession, team: Team, player: Player, period: Period) -> dict:
    """Player-safe report data: coach ratings and confirmed priorities for this period and earlier ones,
    plus the coach's message. Coach rating notes, overall notes and self-ratings are deliberately excluded."""
    periods = db.query(Period).filter(Period.team_id == team.id, Period.created_at <= period.created_at).order_by(
        Period.created_at, Period.id).all()
    periods = [p for p in periods if p.created_at < period.created_at or p.id <= period.id]
    ids = [p.id for p in periods]
    coach = {a.period_id: a for a in db.query(Assessment).filter(
        Assessment.player_id == player.id, Assessment.assessor == "coach", Assessment.period_id.in_(ids))}
    priorities = {}
    for row in db.query(PriorityConfirmation).filter(PriorityConfirmation.player_id == player.id,
                                                     PriorityConfirmation.period_id.in_(ids)).order_by(PriorityConfirmation.rank):
        priorities.setdefault(row.period_id, []).append({"skill_id": row.skill_id, "rank": row.rank, "coach_note": row.coach_note})
    report = db.query(PlayerReport).filter_by(player_id=player.id, period_id=period.id).first()
    history = []
    for p in periods:
        a = coach.get(p.id)
        history.append({"period_id": p.id, "label": p.label, "priorities": priorities.get(p.id, []),
                        "assessments": {"coach": {
                            "position": a.position, "primary_position": a.primary_position,
                            "secondary_position": a.secondary_position,
                            "ratings": [{"skill_id": r.skill_id, "score": r.score} for r in a.ratings],
                        }} if a else {}})
    return {"team": team.name, "player": player.name, "period_id": period.id, "period": period.label,
            "message": report.message if report else None, "history": history,
            "matrix": period_document(db, period)}


def share_status(report: PlayerReport | None) -> dict | None:
    if not report or not report.share_token_hash:
        return None
    expired = report.share_expires_at.replace(tzinfo=timezone.utc) <= utcnow()
    return {"issued_at": report.share_issued_at, "expires_at": report.share_expires_at,
            "opened_at": report.share_opened_at, "expired": expired}


def coach_report(db: DbSession, team: Team, player: Player, period: Period) -> dict:
    """The report as coaches see it: the player-safe payload plus the share link status."""
    report = db.query(PlayerReport).filter_by(player_id=player.id, period_id=period.id).first()
    return {**report_payload(db, team, player, period), "share": share_status(report)}


@router.get("/teams/{team_id}/players/{player_id}/periods/{period_id}/report")
def get_report(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    period = scoped_period(db, team_id, period_id)
    return coach_report(db, db.get(Team, team_id), player, period)


@router.put("/teams/{team_id}/players/{player_id}/periods/{period_id}/report")
def save_report(team_id: int, player_id: int, period_id: int, body: ReportIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = require_active_player(db, team_id, player_id)
    period = scoped_period(db, team_id, period_id)
    report = db.query(PlayerReport).filter_by(player_id=player_id, period_id=period_id).first()
    if not report:
        report = PlayerReport(player_id=player_id, period_id=period_id)
        db.add(report)
    report.message = clean_note(body.message)
    report.updated_by = user.id
    report.updated_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Report changed. Reload before saving")
    return coach_report(db, db.get(Team, team_id), player, period)


@router.post("/teams/{team_id}/players/{player_id}/periods/{period_id}/report/share")
def share_report(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Create a read-only link to the report, replacing any earlier one. The raw link is only returned here."""
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    period = scoped_period(db, team_id, period_id)
    report = db.query(PlayerReport).filter_by(player_id=player_id, period_id=period_id).first()
    if not report:
        report = PlayerReport(player_id=player_id, period_id=period_id)
        db.add(report)
    raw = fresh_token()
    now = utcnow()
    replaced = bool(report.share_token_hash) and report.share_expires_at.replace(tzinfo=timezone.utc) > now
    report.share_token_hash = digest(raw)
    report.share_issued_at = now
    report.share_expires_at = now + timedelta(days=30)
    report.share_opened_at = None
    record(db, team_id, user, "report_shared", player=player.name, period=period.label, **({"replaced": True} if replaced else {}))
    db.commit()
    return {"url": f"{settings.public_base_url}/report/{raw}", "expires_at": report.share_expires_at}


@router.delete("/teams/{team_id}/players/{player_id}/periods/{period_id}/report/share")
def revoke_report_share(team_id: int, player_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    period = scoped_period(db, team_id, period_id)
    report = db.query(PlayerReport).filter_by(player_id=player_id, period_id=period_id).first()
    if report and report.share_token_hash:
        report.share_token_hash = report.share_issued_at = report.share_expires_at = report.share_opened_at = None
        record(db, team_id, user, "report_share_revoked", player=player.name, period=period.label)
        db.commit()
    return {"message": "Link revoked"}


@router.get("/report/{token}")
def shared_report(token: str, db: DbSession = Depends(get_db)):
    found = db.query(PlayerReport, Player, Period, Team).join(Player, Player.id == PlayerReport.player_id).join(
        Period, Period.id == PlayerReport.period_id).join(Team, Team.id == Player.team_id).filter(
        PlayerReport.share_token_hash == digest(token)).first()
    if not found:
        raise HTTPException(404, "Link unavailable")
    report, player, period, team = found
    if report.share_expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(410, "This link has expired. Ask the coach for a new one")
    if not report.share_opened_at:
        report.share_opened_at = utcnow()
        db.commit()
    return report_payload(db, team, player, period)


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
    doc = period_document(db, scoped_period(db, team_id, period_id))
    coach = db.query(Assessment).filter_by(player_id=player_id, period_id=period_id, assessor="coach").first()
    skills = skill_set(doc, coach.position) if coach else set()
    if not coach or skills - {r.skill_id for r in coach.ratings if r.score is not None}:
        raise HTTPException(409, "Complete the coach assessment first")
    ids = [p.skill_id for p in body.priorities]
    ranks = [p.rank for p in body.priorities]
    if len(ids) > 3 or len(ids) != len(set(ids)) or sorted(ranks) != list(range(1, len(ranks) + 1)) or not set(ids).issubset(skills):
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
    return {"team": team.name, "player": player.name, "period": period.label, "expires_at": link.expires_at,
            "matrix": period_document(db, period)}


@router.post("/self/{token}", status_code=201)
def submit_self(token: str, body: SelfAssessmentIn, db: DbSession = Depends(get_db)):
    link, player, period, _ = valid_self_link(db, token, lock=True)
    if body.position not in ("outfield", "goalkeeper"):
        raise HTTPException(422, "Invalid position")
    doc = period_document(db, period)
    validate_ratings(body.ratings, skill_set(doc, body.position))
    if db.query(Assessment).filter_by(player_id=player.id, period_id=period.id, assessor="player").first():
        raise HTTPException(409, "Already submitted")
    a = Assessment(player_id=player.id, period_id=period.id, assessor="player", position=body.position,
                   matrix_version=doc["meta"]["version"])
    db.add(a)
    db.flush()
    for r in body.ratings:
        # Notes are coach-only; anything a player sends in note is ignored.
        db.add(Rating(assessment_id=a.id, skill_id=r.skill_id, score=r.score))
    link.used_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Already submitted")
    db.refresh(a)
    return assessment_out(a)

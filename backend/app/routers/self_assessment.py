"""Player self-assessment: one-time links per player and period, the squad link board, and the public form."""
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from ..auth import current_user, digest, fresh_token, require_member
from ..config import settings
from ..database import get_db
from ..matrix import period_document, rendered, skill_set
from ..models import Assessment, Period, Player, Rating, SelfLink, Team, User, utcnow
from .assessments import RatingIn, assessment_out, validate_ratings
from .teams import scoped_period, scoped_player


router = APIRouter(tags=["self-assessment"])


class SelfAssessmentIn(BaseModel):
    position: str
    ratings: list[RatingIn]


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
            "matrix": rendered(db, period.matrix_version_id, team.player_gender)}


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

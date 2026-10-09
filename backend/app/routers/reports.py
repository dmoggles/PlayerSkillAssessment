"""Player reports: the coach's message and the saved plan's home drills, and the read-only share link that
players and parents open without signing in (which also opens the plan's home drills)."""
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, digest, fresh_token, require_member
from ..config import settings
from ..cycles import current_plan, latest_cycle_ids
from ..database import get_db
from ..matrix import annotate_history, rendered
from ..models import Assessment, Drill, Period, Player, PlayerReport, PriorityConfirmation, Team, User, utcnow
from ..plans import home_view
from .assessments import add_earlier_cycles, add_playing_groups, clean_note, require_active_player
from .drills import drill_out
from .teams import scoped_period, scoped_player


router = APIRouter(tags=["reports"])


class ReportIn(BaseModel):
    message: str | None = Field(default=None, max_length=1000)


def report_payload(db: DbSession, team: Team, player: Player, period: Period) -> dict:
    """Player-safe report data: coach ratings and confirmed priorities for this period and earlier ones, the coach's
    message and the saved development plan. Coach rating notes, overall notes and self-ratings are deliberately excluded."""
    periods = db.query(Period).filter(Period.team_id == team.id, Period.created_at <= period.created_at).order_by(
        Period.created_at, Period.id).all()
    periods = [p for p in periods if p.created_at < period.created_at or p.id <= period.id]
    ids = [p.id for p in periods]
    coach = {a.period_id: a for a in db.query(Assessment).filter(
        Assessment.player_id == player.id, Assessment.assessor == "coach", Assessment.period_id.in_(ids))}
    priorities = {}
    current = latest_cycle_ids(db, player_id=player.id)
    for row in db.query(PriorityConfirmation).filter(PriorityConfirmation.player_id == player.id, PriorityConfirmation.period_id.in_(ids),
                                                     PriorityConfirmation.cycle_id.in_(current)).order_by(PriorityConfirmation.rank):
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
    annotate_history(db, history, [p.matrix_version_id for p in periods])
    add_playing_groups(db, player.id, history)
    add_earlier_cycles(db, player.id, history)
    saved_plan = current_plan(db, player.id, period.id)
    return {"team": team.name, "player": player.name, "period_id": period.id, "period": period.label,
            "message": report.message if report else None, "history": history,
            "plan": home_view(saved_plan.plan) if saved_plan else None,  # home drills only
            "matrix": rendered(db, period.matrix_version_id, team.player_gender)}


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


def share_length(db: DbSession, player_id: int, period_id: int) -> timedelta:
    """A shared report stays open for its plan plus a week, or 30 days when there is no plan."""
    saved = current_plan(db, player_id, period_id)
    return timedelta(weeks=saved.plan.get("weeks", 4), days=7) if saved else timedelta(days=30)


class ExtendIn(BaseModel):
    weeks: int = Field(ge=1, le=8)


@router.post("/teams/{team_id}/players/{player_id}/periods/{period_id}/report/share/extend")
def extend_report_share(team_id: int, player_id: int, period_id: int, body: ExtendIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Keep the same link open longer, counting from its expiry (or from now, if it has already expired)."""
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    period = scoped_period(db, team_id, period_id)
    report = db.query(PlayerReport).filter_by(player_id=player_id, period_id=period_id).first()
    if not report or not report.share_token_hash:
        raise HTTPException(409, "This report has no link to extend. Create one first")
    report.share_expires_at = max(report.share_expires_at.replace(tzinfo=timezone.utc), utcnow()) + timedelta(weeks=body.weeks)
    record(db, team_id, user, "report_share_extended", player=player.name, period=period.label, weeks=body.weeks)
    db.commit()
    return {"share": share_status(report)}


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
    report.share_expires_at = now + share_length(db, player_id, period_id)
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


def open_shared_report(db: DbSession, token: str):
    found = db.query(PlayerReport, Player, Period, Team).join(Player, Player.id == PlayerReport.player_id).join(
        Period, Period.id == PlayerReport.period_id).join(Team, Team.id == Player.team_id).filter(
        PlayerReport.share_token_hash == digest(token)).first()
    if not found:
        raise HTTPException(404, "Link unavailable")
    if found[0].share_expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(410, "This link has expired. Ask the coach for a new one")
    return found


@router.get("/report/{token}/drills/{slug}")
def shared_report_drill(token: str, slug: str, db: DbSession = Depends(get_db)):
    """A home drill from the report's development plan, through the report's link; no other drill is available."""
    report, player, period, team = open_shared_report(db, token)
    saved = current_plan(db, player.id, period.id)
    drill = db.query(Drill).filter_by(slug=slug, status="published").first()
    if not saved or not drill or slug not in {s["drill"] for s in home_view(saved.plan)["slots"]}:
        raise HTTPException(404, "Drill not found")
    return drill_out(db, drill, None)


@router.get("/report/{token}")
def shared_report(token: str, db: DbSession = Depends(get_db)):
    report, player, period, team = open_shared_report(db, token)
    if not report.share_opened_at:
        report.share_opened_at = utcnow()
        db.commit()
    return report_payload(db, team, player, period)

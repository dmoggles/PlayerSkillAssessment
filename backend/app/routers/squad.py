"""The squad over time: players, periods (with optional carry-over of ratings) and playing groups."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, require_member
from ..database import get_db
from ..matrix import period_document, skill_set, team_version, version_label
from ..models import Assessment, AssessmentRevision, Period, Player, Rating, PlayerGroup, Team, User
from .teams import nonblank, purge_assessment_data, scoped_period, scoped_player


router = APIRouter(tags=["squad"])


class PlayerBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


AgeGroup = Annotated[int, Field(ge=5, le=21)]


class PeriodBody(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    is_active: bool = True
    starts_season: bool = False
    # Playing groups the coach reviewed (player id -> U-number, or null for not set). Players left out carry over
    # from the previous period, moved up a year when the period starts a season.
    groups: dict[int, AgeGroup | None] | None = None
    # Start each player's coach assessment from the previous period's ratings, marked as carried until reviewed.
    carry_ratings: bool = False


class GroupBody(BaseModel):
    age_group: AgeGroup | None


class PeriodRename(BaseModel):
    label: str = Field(min_length=1, max_length=100)


def player_out(player: Player):
    return {"id": player.id, "name": player.name, "active": player.active}


def period_out(period: Period, db: DbSession | None = None):
    out = {"id": period.id, "label": period.label, "is_active": period.is_active, "created_at": period.created_at,
           "matrix_version_id": period.matrix_version_id, "starts_season": period.starts_season}
    if db is not None:
        out["matrix_label"] = version_label(db, period.matrix_version_id)
    return out


@router.get("/teams/{team_id}/players")
def list_players(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    return [player_out(p) for p in db.query(Player).filter_by(team_id=team_id).order_by(Player.name).all()]


@router.post("/teams/{team_id}/players", status_code=201)
def create_player(team_id: int, body: PlayerBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    name = nonblank(body.name)
    player = Player(team_id=team_id, name=name, name_key=name.casefold())
    db.add(player)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Player name already exists in this team")
    return player_out(player)


@router.patch("/teams/{team_id}/players/{player_id}")
def update_player(team_id: int, player_id: int, body: PlayerBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    player.name = nonblank(body.name)
    player.name_key = player.name.casefold()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Player name already exists in this team")
    return player_out(player)


@router.post("/teams/{team_id}/players/{player_id}/archive")
def archive_player(team_id: int, player_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    player.active = False
    db.commit()
    return player_out(player)


@router.post("/teams/{team_id}/players/{player_id}/restore")
def restore_player(team_id: int, player_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    player.active = True
    db.commit()
    return player_out(player)


@router.get("/teams/{team_id}/periods")
def list_periods(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    return [period_out(p, db) for p in db.query(Period).filter_by(team_id=team_id).order_by(Period.created_at.desc()).all()]


def carry_ratings(db: DbSession, team_id: int, previous: Period, period: Period, user: User) -> None:
    """Copy each active player's coach ratings from the previous period into this one, marked as carried. Positions
    come too; notes do not (they described that period). Skills the new period's matrix no longer rates are left out."""
    doc = period_document(db, period)
    active = {p.id for p in db.query(Player).filter_by(team_id=team_id, active=True)}
    for old in db.query(Assessment).filter_by(period_id=previous.id, assessor="coach"):
        if old.player_id not in active:
            continue
        skills = skill_set(doc, old.position)
        ratings = [{"skill_id": r.skill_id, "score": r.score, "note": None, "carried": True}
                   for r in old.ratings if r.score is not None and r.skill_id in skills]
        a = Assessment(player_id=old.player_id, period_id=period.id, assessor="coach", position=old.position,
                       primary_position=old.primary_position, secondary_position=old.secondary_position,
                       secondary_position_frequency=old.secondary_position_frequency, version=1, updated_by=user.id,
                       matrix_version=doc["meta"]["version"])
        db.add(a)
        db.flush()
        db.add_all(Rating(assessment_id=a.id, **r) for r in ratings)
        db.add(AssessmentRevision(assessment_id=a.id, version=1, editor_id=user.id, snapshot={
            "position": a.position, "primary_position": a.primary_position, "secondary_position": a.secondary_position,
            "secondary_position_frequency": a.secondary_position_frequency, "note": None, "ratings": ratings, "carried_from": previous.label}))


def carried_groups(db: DbSession, team_id: int, previous: Period | None, starts_season: bool) -> dict[int, int]:
    """Each player's playing group carried from the previous period; a new season moves everyone up a year."""
    if not previous:
        return {}
    rows = db.query(PlayerGroup).filter_by(period_id=previous.id).all()
    return {g.player_id: min(g.age_group + 1, 21) if starts_season else g.age_group for g in rows}


@router.get("/teams/{team_id}/periods/{period_id}/groups")
def period_groups(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Playing groups in a period: player id -> U-number (players without one are left out)."""
    require_member(team_id, db, user)
    scoped_period(db, team_id, period_id)
    return {str(g.player_id): g.age_group for g in db.query(PlayerGroup).filter_by(period_id=period_id)}


@router.put("/teams/{team_id}/players/{player_id}/group")
def set_player_group(team_id: int, player_id: int, period_id: int, body: GroupBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    period = scoped_period(db, team_id, period_id)
    current = db.query(PlayerGroup).filter_by(player_id=player_id, period_id=period_id).first()
    before = current.age_group if current else None
    if before != body.age_group:
        if body.age_group is None:
            db.delete(current)
        elif current:
            current.age_group = body.age_group
        else:
            db.add(PlayerGroup(player_id=player_id, period_id=period_id, age_group=body.age_group))
        record(db, team_id, user, "playing_group_changed", player=player.name, period=period.label, **{"from": before, "to": body.age_group})
        db.commit()
    return {"player_id": player_id, "age_group": body.age_group}


@router.post("/teams/{team_id}/periods", status_code=201)
def create_period(team_id: int, body: PeriodBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    db.query(Team).filter_by(id=team_id).with_for_update().first()
    if body.is_active:
        db.query(Period).filter_by(team_id=team_id).update({"is_active": False})
    previous = db.query(Period).filter_by(team_id=team_id).order_by(Period.created_at.desc(), Period.id.desc()).first()
    period = Period(team_id=team_id, label=nonblank(body.label), is_active=body.is_active, starts_season=body.starts_season,
                    matrix_version_id=team_version(db, db.get(Team, team_id)).id)
    db.add(period)
    db.flush()
    groups = carried_groups(db, team_id, previous, body.starts_season)
    for player_id, age in (body.groups or {}).items():
        scoped_player(db, team_id, player_id)
        groups[player_id] = age
    db.add_all(PlayerGroup(player_id=player_id, period_id=period.id, age_group=age) for player_id, age in groups.items() if age)
    if body.carry_ratings and previous:
        carry_ratings(db, team_id, previous, period, user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Period label already exists in this team")
    return period_out(period, db)


@router.post("/teams/{team_id}/periods/{period_id}/activate")
def activate_period(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    db.query(Team).filter_by(id=team_id).with_for_update().first()
    period = scoped_period(db, team_id, period_id)
    db.query(Period).filter_by(team_id=team_id).update({"is_active": False})
    period.is_active = True
    db.commit()
    return period_out(period, db)


@router.patch("/teams/{team_id}/periods/{period_id}")
def rename_period(team_id: int, period_id: int, body: PeriodRename, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    period = scoped_period(db, team_id, period_id)
    period.label = nonblank(body.label)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Period label already exists in this team")
    return period_out(period, db)


@router.delete("/teams/{team_id}/periods/{period_id}")
def delete_period(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    db.query(Team).filter_by(id=team_id).with_for_update().first()
    period = scoped_period(db, team_id, period_id)
    was_active = period.is_active
    record(db, team_id, user, "period_deleted", label=period.label)
    purge_assessment_data(db, period_ids=[period_id])
    db.delete(period)
    db.flush()
    if was_active:
        latest = db.query(Period).filter_by(team_id=team_id).order_by(Period.created_at.desc()).first()
        if latest:
            latest.is_active = True
    db.commit()
    return {"message": "Period deleted"}

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from ..auth import consume_auth_token, current_user, issue_auth_token, require_member, send_email
from ..config import settings
from ..database import get_db
from ..models import AuthToken, Membership, Period, Player, SelfLink, Team, User
from .accounts import delivery_message


router = APIRouter(tags=["teams"])


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamSettings(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    self_assessment_enabled: bool


class InviteBody(BaseModel):
    email: EmailStr


class AcceptBody(BaseModel):
    token: str


class PlayerBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PeriodBody(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    is_active: bool = True


def team_out(team: Team, role: str):
    return {"id": team.id, "name": team.name, "self_assessment_enabled": team.self_assessment_enabled, "role": role}


def player_out(player: Player):
    return {"id": player.id, "name": player.name, "active": player.active}


def period_out(period: Period):
    return {"id": period.id, "label": period.label, "is_active": period.is_active, "created_at": period.created_at}


def nonblank(value: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(422, "Name or label cannot be blank")
    return value


def scoped_player(db: DbSession, team_id: int, player_id: int) -> Player:
    player = db.query(Player).filter_by(team_id=team_id, id=player_id).first()
    if not player:
        raise HTTPException(404, "Player not found")
    return player


def scoped_period(db: DbSession, team_id: int, period_id: int) -> Period:
    period = db.query(Period).filter_by(team_id=team_id, id=period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")
    return period


@router.get("/teams")
def list_teams(db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Team, Membership).join(Membership, Membership.team_id == Team.id).filter(Membership.user_id == user.id).order_by(Team.name).all()
    return [team_out(team, member.role) for team, member in rows]


@router.post("/teams", status_code=201)
def create_team(body: TeamCreate, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    team = Team(name=nonblank(body.name))
    db.add(team)
    db.flush()
    db.add(Membership(team_id=team.id, user_id=user.id, role="owner"))
    db.commit()
    return team_out(team, "owner")


@router.patch("/teams/{team_id}")
def update_team(team_id: int, body: TeamSettings, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    team = db.get(Team, team_id)
    team.name = nonblank(body.name)
    team.self_assessment_enabled = body.self_assessment_enabled
    if not body.self_assessment_enabled:
        player_ids = db.query(Player.id).filter_by(team_id=team_id)
        db.query(SelfLink).filter(SelfLink.player_id.in_(player_ids)).delete(synchronize_session=False)
    db.commit()
    return team_out(team, "owner")


@router.get("/teams/{team_id}/members")
def members(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    rows = db.query(Membership, User).join(User, Membership.user_id == User.id).filter(Membership.team_id == team_id).all()
    return [{"user_id": u.id, "email": u.email, "role": m.role} for m, u in rows]


@router.delete("/teams/{team_id}/members/{member_user_id}")
def remove_member(team_id: int, member_user_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    member = db.query(Membership).filter_by(team_id=team_id, user_id=member_user_id, role="coach").first()
    if not member:
        raise HTTPException(404, "Coach not found")
    coach = db.get(User, member_user_id)
    db.query(AuthToken).filter_by(team_id=team_id, email=coach.email, purpose="invite").delete(synchronize_session=False)
    db.delete(member)
    db.commit()
    return {"message": "Coach removed"}


@router.post("/teams/{team_id}/invites")
def invite(team_id: int, body: InviteBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    email = body.email.strip().casefold()
    if db.query(Membership).join(User).filter(Membership.team_id == team_id, User.email == email).first():
        raise HTTPException(409, "Coach is already a member")
    token = issue_auth_token(db, email, "invite", team_id=team_id)
    try:
        send_email(email, "Team invitation", f"You have been invited to join a team. Open this link after signing in or registering:\n{settings.public_base_url}/invite/{token}")
    except Exception:
        db.rollback()
        raise HTTPException(503, "Email delivery unavailable")
    db.commit()
    return {"message": delivery_message("Invitation sent.")}


@router.post("/invites/accept")
def accept_invite(body: AcceptBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    token = consume_auth_token(db, body.token, "invite")
    if token.email != user.email or not db.get(Team, token.team_id):
        raise HTTPException(403, "Invitation is for another account")
    if not db.query(Membership).filter_by(team_id=token.team_id, user_id=user.id).first():
        db.add(Membership(team_id=token.team_id, user_id=user.id, role="coach"))
    db.commit()
    return {"team_id": token.team_id}


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


@router.get("/teams/{team_id}/periods")
def list_periods(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    return [period_out(p) for p in db.query(Period).filter_by(team_id=team_id).order_by(Period.created_at.desc()).all()]


@router.post("/teams/{team_id}/periods", status_code=201)
def create_period(team_id: int, body: PeriodBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    db.query(Team).filter_by(id=team_id).with_for_update().first()
    if body.is_active:
        db.query(Period).filter_by(team_id=team_id).update({"is_active": False})
    period = Period(team_id=team_id, label=nonblank(body.label), is_active=body.is_active)
    db.add(period)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Period label already exists in this team")
    return period_out(period)


@router.post("/teams/{team_id}/periods/{period_id}/activate")
def activate_period(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    db.query(Team).filter_by(id=team_id).with_for_update().first()
    period = scoped_period(db, team_id, period_id)
    db.query(Period).filter_by(team_id=team_id).update({"is_active": False})
    period.is_active = True
    db.commit()
    return period_out(period)

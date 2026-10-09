from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import consume_auth_token, current_user, issue_auth_token, require_member, send_email
from ..config import settings
from ..database import get_db
from ..models import Assessment, AssessmentRevision, AuditEvent, AuthToken, MatrixDraft, MatrixSkillTag, MatrixVersion, Membership, Period, Player, PlayerReport, PriorityConfirmation, Rating, SelfLink, PlayerGroup, PlayerPlan, DevelopmentCycle, CycleCheckin, SkillMatrix, Team, User
from .accounts import delivery_message


router = APIRouter(tags=["teams"])


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamSettings(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    self_assessment_enabled: bool
    player_gender: Literal["girls", "boys", "mixed"] | None = None


class TeamDelete(BaseModel):
    confirm_name: str


class MemberRole(BaseModel):
    role: Literal["owner", "coach"]


class InviteBody(BaseModel):
    email: EmailStr


class AcceptBody(BaseModel):
    token: str


def team_out(team: Team, role: str):
    return {"id": team.id, "name": team.name, "self_assessment_enabled": team.self_assessment_enabled,
            "player_gender": team.player_gender, "role": role}


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


def purge_assessment_data(db: DbSession, player_ids=None, period_ids=None):
    """Delete assessments, ratings, revisions, priorities, reports, saved plans, cycles and their check-ins, playing groups and self links for the given players or periods."""
    def scoped(model):
        query = db.query(model)
        if player_ids is not None:
            query = query.filter(model.player_id.in_(player_ids))
        if period_ids is not None:
            query = query.filter(model.period_id.in_(period_ids))
        return query
    assessment_ids = scoped(Assessment).with_entities(Assessment.id)
    db.query(Rating).filter(Rating.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
    db.query(AssessmentRevision).filter(AssessmentRevision.assessment_id.in_(assessment_ids)).delete(synchronize_session=False)
    db.query(CycleCheckin).filter(CycleCheckin.cycle_id.in_(scoped(DevelopmentCycle).with_entities(DevelopmentCycle.id))).delete(synchronize_session=False)
    for model in (Assessment, PriorityConfirmation, PlayerReport, SelfLink, PlayerPlan, PlayerGroup, DevelopmentCycle):
        scoped(model).delete(synchronize_session=False)


def owner_count(db: DbSession, team_id: int) -> int:
    return db.query(Membership).filter_by(team_id=team_id, role="owner").count()


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
    record(db, team.id, user, "team_created", name=team.name)
    db.commit()
    return team_out(team, "owner")


@router.patch("/teams/{team_id}")
def update_team(team_id: int, body: TeamSettings, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    team = db.get(Team, team_id)
    name = nonblank(body.name)
    if name != team.name:
        record(db, team_id, user, "team_renamed", **{"from": team.name, "to": name})
    if body.self_assessment_enabled != team.self_assessment_enabled:
        record(db, team_id, user, "self_assessment_" + ("enabled" if body.self_assessment_enabled else "disabled"))
    if body.player_gender and body.player_gender != team.player_gender:
        record(db, team_id, user, "player_gender_changed", **{"from": team.player_gender, "to": body.player_gender})
        team.player_gender = body.player_gender
    team.name = name
    team.self_assessment_enabled = body.self_assessment_enabled
    if not body.self_assessment_enabled:
        player_ids = db.query(Player.id).filter_by(team_id=team_id)
        db.query(SelfLink).filter(SelfLink.player_id.in_(player_ids)).delete(synchronize_session=False)
    db.commit()
    return team_out(team, "owner")


@router.delete("/teams/{team_id}")
def delete_team(team_id: int, body: TeamDelete, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    team = db.query(Team).filter_by(id=team_id).with_for_update().first()
    if body.confirm_name.strip() != team.name:
        raise HTTPException(422, "Type the team name exactly to confirm")
    player_ids = db.query(Player.id).filter_by(team_id=team_id)
    purge_assessment_data(db, player_ids=player_ids)
    db.query(Player).filter_by(team_id=team_id).delete(synchronize_session=False)
    db.query(Period).filter_by(team_id=team_id).delete(synchronize_session=False)
    db.query(MatrixDraft).filter_by(team_id=team_id).delete(synchronize_session=False)
    own_matrices = db.query(SkillMatrix.id).filter_by(team_id=team_id)
    own_versions = db.query(MatrixVersion.id).filter(MatrixVersion.matrix_id.in_(own_matrices))
    db.query(MatrixSkillTag).filter(MatrixSkillTag.matrix_version_id.in_(own_versions)).delete(synchronize_session=False)
    db.query(MatrixVersion).filter(MatrixVersion.matrix_id.in_(own_matrices)).delete(synchronize_session=False)
    db.query(SkillMatrix).filter_by(team_id=team_id).delete(synchronize_session=False)
    db.query(AuthToken).filter_by(team_id=team_id).delete(synchronize_session=False)
    db.query(Membership).filter_by(team_id=team_id).delete(synchronize_session=False)
    record(db, team_id, user, "team_deleted", name=team.name)
    db.delete(team)
    db.commit()
    return {"message": "Team deleted"}


@router.get("/teams/{team_id}/members")
def members(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    rows = db.query(Membership, User).join(User, Membership.user_id == User.id).filter(Membership.team_id == team_id).all()
    return [{"user_id": u.id, "email": u.email, "role": m.role} for m, u in rows]


@router.patch("/teams/{team_id}/members/{member_user_id}")
def change_member_role(team_id: int, member_user_id: int, body: MemberRole, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    db.query(Team).filter_by(id=team_id).with_for_update().first()
    member = db.query(Membership).filter_by(team_id=team_id, user_id=member_user_id).first()
    if not member:
        raise HTTPException(404, "Member not found")
    if member.role == "owner" and body.role == "coach" and owner_count(db, team_id) == 1:
        raise HTTPException(409, "A team needs at least one owner")
    target = db.get(User, member_user_id)
    if member.role != body.role:
        record(db, team_id, user, "role_changed", target.email, **{"from": member.role, "to": body.role})
    member.role = body.role
    db.commit()
    return {"user_id": member_user_id, "email": target.email, "role": member.role}


@router.delete("/teams/{team_id}/members/{member_user_id}")
def remove_member(team_id: int, member_user_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    # Any member may leave; only owners may remove someone else.
    require_member(team_id, db, user, owner=member_user_id != user.id)
    db.query(Team).filter_by(id=team_id).with_for_update().first()
    member = db.query(Membership).filter_by(team_id=team_id, user_id=member_user_id).first()
    if not member:
        raise HTTPException(404, "Member not found")
    if member.role == "owner" and owner_count(db, team_id) == 1:
        raise HTTPException(409, "A team needs at least one owner")
    removed = db.get(User, member_user_id)
    db.query(AuthToken).filter_by(team_id=team_id, email=removed.email, purpose="invite").delete(synchronize_session=False)
    if member_user_id == user.id:
        record(db, team_id, user, "member_left", role=member.role)
    else:
        record(db, team_id, user, "member_removed", removed.email, role=member.role)
    db.delete(member)
    db.commit()
    return {"message": "Member removed"}


@router.get("/teams/{team_id}/audit")
def audit_log(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    rows = db.query(AuditEvent).filter_by(team_id=team_id).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(100).all()
    return [{"id": e.id, "action": e.action, "actor_email": e.actor_email, "target_email": e.target_email,
             "details": e.details or {}, "created_at": e.created_at} for e in rows]


@router.post("/teams/{team_id}/invites")
def invite(team_id: int, body: InviteBody, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    email = body.email.strip().casefold()
    if db.query(Membership).join(User).filter(Membership.team_id == team_id, User.email == email).first():
        raise HTTPException(409, "Coach is already a member")
    token = issue_auth_token(db, email, "invite", team_id=team_id)
    record(db, team_id, user, "invite_sent", email)
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
        record(db, token.team_id, user, "invite_accepted")
    db.commit()
    return {"team_id": token.team_id}

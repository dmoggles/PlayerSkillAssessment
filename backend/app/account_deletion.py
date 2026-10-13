"""Deleting a coach's own account. The teams' records stay (they belong to the clubs) but no longer name the coach:
who saved an assessment or plan is cleared, and activity logs say "a deleted account" instead of their email."""
from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession
from .models import (Assessment, AssessmentRevision, AuditEvent, AuthToken, CycleCheckin, DevelopmentCycle, DrillVote,
                     MatrixDraft, MatrixVersion, Membership, PlayerPlan, PlayerReport, Session, Team, User)

DELETED_ACCOUNT = "a deleted account"
AUTHORED = ((Assessment, "updated_by"), (AssessmentRevision, "editor_id"), (DevelopmentCycle, "created_by"),
            (CycleCheckin, "created_by"), (PlayerReport, "updated_by"), (PlayerPlan, "created_by"),
            (MatrixVersion, "created_by"), (MatrixDraft, "updated_by"))


def teams_needing_another_owner(db: DbSession, user: User) -> list[str]:
    """Teams the user is the only owner of: they must hand them over or delete them first."""
    owned = db.query(Membership.team_id).filter_by(user_id=user.id, role="owner")
    names = []
    for team in db.query(Team).filter(Team.id.in_(owned)).order_by(Team.name):
        if db.query(Membership).filter_by(team_id=team.id, role="owner").count() == 1:
            names.append(team.name)
    return names


def erase_account(db: DbSession, user: User):
    team_ids = [m.team_id for m in db.query(Membership).filter_by(user_id=user.id)]
    for team_id in team_ids:
        db.add(AuditEvent(team_id=team_id, actor_email=DELETED_ACCOUNT, action="account_deleted"))
    db.query(AuditEvent).filter_by(actor_email=user.email).update({"actor_email": DELETED_ACCOUNT}, synchronize_session=False)
    db.query(AuditEvent).filter_by(target_email=user.email).update({"target_email": DELETED_ACCOUNT}, synchronize_session=False)
    for model, column in AUTHORED:
        db.query(model).filter(getattr(model, column) == user.id).update({column: None}, synchronize_session=False)
    db.query(AuthToken).filter(or_(AuthToken.user_id == user.id, AuthToken.email == user.email)).delete(synchronize_session=False)
    for model in (Session, Membership, DrillVote):
        db.query(model).filter_by(user_id=user.id).delete(synchronize_session=False)
    db.delete(user)

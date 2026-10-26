"""Everything recorded about one player, as one JSON document: what a club sends when a player or parent asks for
a copy of their data. Link tokens are left out (they would open the player's pages); coaches appear by email."""
from sqlalchemy.orm import Session as DbSession
from .account_deletion import DELETED_ACCOUNT
from .matrix import version_skills
from .models import (Assessment, AssessmentRevision, CycleCheckin, DevelopmentCycle, Period, Player, PlayerGroup,
                     PlayerPlan, PlayerReport, PracticeAssignment, PracticeAttempt, PracticeLink, PriorityConfirmation, Rating, SelfLink, SessionAttendance, Team, TrainingSession,
                     User, utcnow)

SECRETS = {"token_hash", "share_token_hash"}
USER_COLUMNS = {"updated_by", "created_by", "editor_id", "assigned_by"}
INTERNAL = {"player_id", "team_id"}


def player_export(db: DbSession, team: Team, player: Player) -> dict:
    emails = {}

    def coach(user_id):
        if user_id is not None and user_id not in emails:
            user = db.get(User, user_id)
            emails[user_id] = user.email if user else DELETED_ACCOUNT
        return emails.get(user_id)

    def row(obj, skip=()):
        out = {}
        for column in obj.__table__.columns:
            key = column.key
            if key in SECRETS or key in INTERNAL or key in skip:
                continue
            value = getattr(obj, key)
            out[key] = coach(value) if key in USER_COLUMNS else value
        return out

    owned = lambda model: db.query(model).filter_by(player_id=player.id).order_by(model.id).all()
    assessments = owned(Assessment)
    cycles = owned(DevelopmentCycle)
    period_ids = {r.period_id for model in (Assessment, DevelopmentCycle, PlayerGroup, PlayerReport, SelfLink)
                  for r in db.query(model.period_id).filter_by(player_id=player.id)}
    periods = db.query(Period).filter(Period.id.in_(period_ids)).order_by(Period.created_at).all()
    skills = {}
    for period in periods:
        skills.update({sid: skill["label"] for sid, (skill, _) in version_skills(db, period.matrix_version_id).items()})

    return {
        "exported_at": utcnow(),
        "team": team.name,
        "player": row(player),
        "periods": [row(p, skip={"is_active", "matrix_version_id"}) for p in periods],
        "skill_names": skills,
        "playing_groups": [row(g) for g in owned(PlayerGroup)],
        "assessments": [{**row(a, skip={"matrix_version", "version"}),
                         "ratings": [row(r, skip={"assessment_id"}) for r in db.query(Rating).filter_by(assessment_id=a.id).order_by(Rating.skill_id)],
                         "earlier_versions": [row(v, skip={"assessment_id"}) for v in db.query(AssessmentRevision).filter_by(assessment_id=a.id).order_by(AssessmentRevision.version)]}
                        for a in assessments],
        "development_cycles": [{**row(c),
                                "priorities": [row(p, skip={"cycle_id", "period_id"}) for p in db.query(PriorityConfirmation).filter_by(cycle_id=c.id).order_by(PriorityConfirmation.rank)],
                                "check_ins": [row(k, skip={"cycle_id"}) for k in db.query(CycleCheckin).filter_by(cycle_id=c.id).order_by(CycleCheckin.id)],
                                "plan": next((row(p, skip={"cycle_id", "period_id"}) for p in db.query(PlayerPlan).filter_by(cycle_id=c.id)), None)}
                               for c in cycles],
        "reports": [row(r) for r in owned(PlayerReport)],
        "self_assessment_links": [row(s) for s in owned(SelfLink)],
        # Team training sessions the player was expected at or came to, with their level group if there was one.
        "training_sessions": [{"date": ts.date, "title": ts.title, "expected": a.expected, "attended": a.attended,
                               "group": next((g["name"] for g in ts.groups if player.id in g["player_ids"]), None)}
                              for a, ts in db.query(SessionAttendance, TrainingSession).join(TrainingSession, TrainingSession.id == SessionAttendance.session_id)
                              .filter(SessionAttendance.player_id == player.id).order_by(TrainingSession.date, TrainingSession.id)],
        # Practice scenarios: the link (never its token), what the player was set, and every attempt.
        "practice": {"links": [row(k) for k in owned(PracticeLink)],
                     "assignments": [row(a) for a in owned(PracticeAssignment)],
                     "attempts": [row(a) for a in owned(PracticeAttempt)]},
    }

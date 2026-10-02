"""Populate a development deployment with repeatable, synthetic demo data."""

import secrets
from urllib.parse import urlparse

from sqlalchemy import select

from .auth import hasher
from .config import settings
from .database import SessionLocal
from .models import (
    Assessment, AssessmentRevision, Membership, Period, Player,
    PriorityConfirmation, Rating, Session, Team, User, utcnow,
)
from .routers.assessments import MATRIX, SKILLS


USERS = ("dev-owner@example.invalid", "dev-coach@example.invalid")
TEAMS = ("[DEV DEMO] Falcons", "[DEV DEMO] Hawks")
PERIODS = ("Autumn 2025", "Spring 2026", "Autumn 2026")
ROSTERS = (
    (("Alex Morgan", "defender"), ("Jamie Patel", "midfielder"),
     ("Taylor Reed", "winger"), ("Casey Brown", "goalkeeper"),
     ("Robin Chen", "striker"), ("Sam Kelly", "defender")),
    (("Jordan Ellis", "defender"), ("Avery Singh", "midfielder"),
     ("Riley Wilson", "goalkeeper"), ("Charlie Park", "striker")),
)


def get_or_create(db, model, lookup, **values):
    row = db.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
    if row is None:
        row = model(**lookup, **values)
        db.add(row)
        db.flush()
    return row


def scores(position, player_index, period_index, self_assessment=False):
    skill_ids = sorted(SKILLS["goalkeeper" if position == "goalkeeper" else "outfield"])
    result = {}
    for skill_index, skill_id in enumerate(skill_ids):
        base = 2 + ((player_index * 3 + skill_index) % 3)
        progress = 1 if period_index == 2 and skill_index % 3 == 0 else 0
        offset = (1 if (player_index + skill_index) % 5 == 0 else -1) if self_assessment else 0
        result[skill_id] = max(1, min(5, base + progress + offset))
    return result


def add_assessment(db, player, period, assessor, position, user, player_index, period_index):
    existing = db.execute(select(Assessment).filter_by(
        player_id=player.id, period_id=period.id, assessor=assessor
    )).scalar_one_or_none()
    if existing:
        return existing
    kind = "goalkeeper" if position == "goalkeeper" else "outfield"
    ratings = scores(position, player_index, period_index, assessor == "player")
    assessment = Assessment(
        player_id=player.id, period_id=period.id, assessor=assessor,
        position=kind, primary_position=position,
        matrix_version=MATRIX["meta"]["version"], version=1,
        updated_by=user.id if assessor == "coach" else None,
    )
    db.add(assessment)
    db.flush()
    for skill_id, score in ratings.items():
        db.add(Rating(assessment_id=assessment.id, skill_id=skill_id, score=score))
    if assessor == "coach":
        db.add(AssessmentRevision(
            assessment_id=assessment.id, version=1, editor_id=user.id,
            snapshot={"position": kind, "primary_position": position,
                      "secondary_position": None, "secondary_position_frequency": None,
                      "ratings": [{"skill_id": key, "score": value} for key, value in ratings.items()]},
        ))
    return assessment


def seed():
    host = (urlparse(settings.public_base_url).hostname or "").lower()
    if not any(part in host for part in ("dev", "staging", "test", "localhost")):
        raise SystemExit("Refusing to seed: PUBLIC_BASE_URL does not look like a development site")

    passwords = [secrets.token_urlsafe(20) for _ in USERS]
    with SessionLocal.begin() as db:
        users = []
        for email, password in zip(USERS, passwords):
            user = db.execute(select(User).filter_by(email=email)).scalar_one_or_none()
            if user is not None:
                memberships = db.execute(
                    select(Team.name).join(Membership).filter(Membership.user_id == user.id)
                ).scalars().all()
                if not memberships or any(name not in TEAMS for name in memberships):
                    raise RuntimeError(f"Refusing to rotate {email}: account is not exclusively a demo account")
            else:
                user = User(email=email, password_hash=hasher.hash(password), verified_at=utcnow())
                db.add(user)
                db.flush()
            user.password_hash = hasher.hash(password)
            user.verified_at = utcnow()
            db.query(Session).filter_by(user_id=user.id).delete()
            users.append(user)

        for team_index, (name, roster) in enumerate(zip(TEAMS, ROSTERS)):
            team = db.execute(select(Team).filter_by(name=name)).scalar_one_or_none()
            if team is None:
                team = Team(name=name, self_assessment_enabled=team_index == 0)
                db.add(team)
                db.flush()
            elif not db.execute(select(Membership).filter_by(
                team_id=team.id, user_id=users[team_index].id, role="owner"
            )).scalar_one_or_none():
                raise RuntimeError(f"Refusing to modify existing team {name!r} with a different owner")
            team.self_assessment_enabled = team_index == 0
            get_or_create(db, Membership, {"team_id": team.id, "user_id": users[team_index].id},
                          role="owner")
            if team_index == 0:
                get_or_create(db, Membership, {"team_id": team.id, "user_id": users[1].id},
                              role="coach")

            periods = []
            for period_index, label in enumerate(PERIODS):
                period = get_or_create(db, Period, {"team_id": team.id, "label": label},
                                       is_active=period_index == 2)
                period.is_active = period_index == 2
                periods.append(period)

            for player_index, (player_name, position) in enumerate(roster):
                player = get_or_create(db, Player,
                                       {"team_id": team.id, "name_key": player_name.casefold()},
                                       name=player_name, active=True)
                for period_index, period in enumerate(periods):
                    # A few missing coach assessments make the team views realistic.
                    if period_index == 1 and player_index == len(roster) - 1:
                        continue
                    add_assessment(db, player, period, "coach", position,
                                   users[team_index], player_index, period_index)
                    # Only some players have submitted; the second team disables self-assessment.
                    if team_index == 0 and (player_index + period_index) % 3 != 0:
                        add_assessment(db, player, period, "player", position,
                                       users[team_index], player_index, period_index)
                    if period_index == 2 and player_index < 3:
                        for rank, skill_id in enumerate(sorted(
                            SKILLS["goalkeeper" if position == "goalkeeper" else "outfield"]
                        )[:3], start=1):
                            get_or_create(db, PriorityConfirmation,
                                          {"player_id": player.id, "period_id": period.id, "rank": rank},
                                          skill_id=skill_id, algorithm_suggested=rank != 2,
                                          coach_note="Focus on this in training." if rank == 1 else None)

    print("Development demo data is ready. Passwords were rotated; previous sessions were revoked.")
    for email, password in zip(USERS, passwords):
        print(f"{email}  {password}")
    print("Keep these credentials private. They are shown only now and are not saved in a file.")


if __name__ == "__main__":
    seed()

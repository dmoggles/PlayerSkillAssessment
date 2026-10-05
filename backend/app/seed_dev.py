"""Populate a development deployment with repeatable, synthetic demo data."""

import random
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
from .matrix import document, skill_set, starter_version
from .routers.teams import purge_assessment_data


USERS = ("dev-owner@example.com", "dev-coach@example.com")
LEGACY_USERS = ("dev-owner@example.invalid", "dev-coach@example.invalid")
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


PRIORITY_NOTES = (
    "Work on this in every session.",
    "Quick wins here with a few focused drills.",
    "Talked through this together after the last match.",
)
RATING_NOTES = (
    "Rushes this under pressure.",
    "Big improvement in recent sessions.",
    "Good in drills, less so in matches.",
)


def skill_ids_for(doc, position):
    return sorted(skill_set(doc, "goalkeeper" if position == "goalkeeper" else "outfield"))


def clamp(score):
    return max(1, min(5, score))


def coach_scores_by_period(rng, doc, position, period_count):
    """Per-period coach scores: each player has their own strengths and weaknesses, then drifts."""
    talent = rng.choice((-1, 0, 0, 1))
    current = {skill_id: clamp(rng.choice((1, 2, 2, 3, 3, 3, 4, 4, 5)) + talent) for skill_id in skill_ids_for(doc, position)}
    periods = [dict(current)]
    for _ in range(1, period_count):
        current = {skill_id: clamp(score + rng.choices((-1, 0, 1), weights=(1, 6, 3))[0]) for skill_id, score in current.items()}
        periods.append(dict(current))
    return periods


def self_scores(rng, coach_scores):
    """Players mostly agree with the coach; a few skills are notably over- or under-rated."""
    return {skill_id: clamp(score + rng.choices((-2, -1, 0, 1, 2), weights=(1, 3, 6, 3, 1))[0])
            for skill_id, score in coach_scores.items()}


def weakest(rng, scores, count=3):
    return sorted(scores, key=lambda skill_id: (scores[skill_id], rng.random()))[:count]


def add_assessment(db, player, period, assessor, position, user, ratings, notes=None, note=None):
    kind = "goalkeeper" if position == "goalkeeper" else "outfield"
    notes = notes or {}
    assessment = Assessment(
        player_id=player.id, period_id=period.id, assessor=assessor,
        position=kind, primary_position=position, note=note,
        matrix_version=document(db, period.matrix_version_id)["meta"]["version"], version=1,
        updated_by=user.id if assessor == "coach" else None,
    )
    db.add(assessment)
    db.flush()
    rows = [{"skill_id": skill_id, "score": score, "note": notes.get(skill_id)} for skill_id, score in ratings.items()]
    for row in rows:
        db.add(Rating(assessment_id=assessment.id, **row))
    if assessor == "coach":
        db.add(AssessmentRevision(
            assessment_id=assessment.id, version=1, editor_id=user.id,
            snapshot={"position": kind, "primary_position": position,
                      "secondary_position": None, "secondary_position_frequency": None,
                      "note": note, "ratings": rows},
        ))
    return assessment


def seed():
    host = (urlparse(settings.public_base_url).hostname or "").lower()
    if not any(part in host for part in ("dev", "staging", "test", "localhost")):
        raise SystemExit("Refusing to seed: PUBLIC_BASE_URL does not look like a development site")

    passwords = [secrets.token_urlsafe(20) for _ in USERS]
    with SessionLocal.begin() as db:
        starter = starter_version(db)
        users = []
        for email, legacy_email, password in zip(USERS, LEGACY_USERS, passwords):
            user = db.execute(select(User).filter_by(email=email)).scalar_one_or_none()
            legacy_user = db.execute(select(User).filter_by(email=legacy_email)).scalar_one_or_none()
            if user is not None and legacy_user is not None:
                raise RuntimeError(f"Refusing to merge two demo accounts for {email}")
            if legacy_user is not None:
                user = legacy_user
            if user is not None:
                memberships = db.execute(
                    select(Team.name).join(Membership).filter(Membership.user_id == user.id)
                ).scalars().all()
                if not memberships or any(name not in TEAMS for name in memberships):
                    raise RuntimeError(f"Refusing to rotate {email}: account is not exclusively a demo account")
                user.email = email
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
                                       is_active=period_index == 2, matrix_version_id=starter.id)
                period.is_active = period_index == 2
                periods.append(period)

            # Demo assessments are regenerated on every run from a fixed seed, so reruns give the same data.
            players = []
            for player_name, position in roster:
                players.append((get_or_create(db, Player, {"team_id": team.id, "name_key": player_name.casefold()},
                                              name=player_name, active=True), position))
            purge_assessment_data(db, player_ids=[player.id for player, _ in players])
            db.flush()

            for player_index, (player, position) in enumerate(players):
                rng = random.Random(f"{team.name}/{player.name}")
                coach_periods = coach_scores_by_period(rng, starter.document, position, len(periods))
                previous_priorities = []
                for period_index, period in enumerate(periods):
                    # A missing coach assessment shows how follow-up skips back to an older period.
                    if period_index == 1 and player_index == len(players) - 1:
                        continue
                    ratings = dict(coach_periods[period_index])
                    # Last period's priorities move in a visible way: mostly improve, some hold or drop.
                    for skill_id in previous_priorities:
                        before = coach_periods[period_index - 1][skill_id] if period_index else ratings[skill_id]
                        ratings[skill_id] = clamp(before + rng.choices((-1, 0, 1), weights=(2, 3, 5))[0])
                    coach_periods[period_index] = ratings
                    notes = {skill_id: rng.choice(RATING_NOTES) for skill_id in rng.sample(sorted(ratings), 2)}
                    note = "Settled well into the team this period." if period_index == len(periods) - 1 and player_index % 2 == 0 else None
                    add_assessment(db, player, period, "coach", position, users[team_index], ratings, notes, note)
                    # Only some players have submitted; the second team disables self-assessment.
                    if team_index == 0 and (player_index + period_index) % 3 != 0:
                        add_assessment(db, player, period, "player", position, users[team_index], self_scores(rng, ratings))
                    # Earlier periods all have confirmed priorities; in the current period only some players do,
                    # so others show last period's priorities with Keep buttons.
                    if period_index < len(periods) - 1 or player_index % 3 == 0:
                        previous_priorities = weakest(rng, ratings)
                        for rank, skill_id in enumerate(previous_priorities, start=1):
                            db.add(PriorityConfirmation(player_id=player.id, period_id=period.id, rank=rank,
                                                        skill_id=skill_id, algorithm_suggested=rank != 2,
                                                        coach_note=PRIORITY_NOTES[rank - 1] if rank != 3 else None))

    print("Development demo data is ready. Passwords were rotated; previous sessions were revoked.")
    for email, password in zip(USERS, passwords):
        print(f"{email}  {password}")
    print("Keep these credentials private. They are shown only now and are not saved in a file.")


if __name__ == "__main__":
    seed()

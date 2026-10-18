"""Give an existing account a full demo squad on a development site: python -m app.seed_demo EMAIL [--team NAME]

The account owns the team. It gets 16 synthetic players (U12, two goalkeepers, one who has left and one who has just
joined), three periods of coach and self assessments, confirmed priorities and development plans (some players on
their second cycle, with a check-in), a few liked drills, and training sessions: past ones with attendance and notes,
and upcoming ones, one with a player already marked as not coming.

Rerunning replaces the team (and everything in it) with the same data again. The account itself is left alone, so
create it first with `python -m app.admin create-user EMAIL`.
"""
import argparse
import random
import sys
from datetime import date, timedelta

from .database import SessionLocal
from .matrix import starter_version
from .models import (CycleCheckin, DevelopmentCycle, Drill, DrillVote, Membership, Period, Player, PlayerGroup, PlayerReport,
                     PriorityConfirmation, Team, User, utcnow)
from .routers.plans import save_generated
from .routers.sessions import (AttendanceIn, AttendanceRow, BlockPatch, SessionIn, SessionPatch, change_block, create_session,
                               set_attendance, suggested_focus, update_session)
from .routers.teams import TeamDelete, delete_team
from .seed_dev import (PRIORITY_NOTES, RATING_NOTES, add_assessment, clamp, coach_scores_by_period, require_dev_site, self_scores,
                       weakest)

DEFAULT_TEAM = "[DEMO] Riverside U12"
AGE_GROUP = 12
ROSTER = (
    ("Ollie Hart", "goalkeeper"), ("Maya Osei", "goalkeeper"),
    ("Leo Fraser", "defender"), ("Isla Novak", "defender"), ("Theo Grant", "defender"), ("Ava Mensah", "defender"),
    ("Finn Doyle", "defender"),
    ("Zara Ahmed", "midfielder"), ("Noah Byrne", "midfielder"), ("Ruby Clarke", "midfielder"), ("Kai Romero", "midfielder"),
    ("Ella Shaw", "winger"), ("Arlo Price", "winger"),
    ("Sienna Lowe", "striker"), ("Jude Okafor", "striker"), ("Freddie Lane", "striker"),
)
LEFT = "Freddie Lane"     # left the club after the first period
JOINED = "Arlo Price"     # joined this period: assessed, but no priorities yet
CHECKIN_NOTES = ("Much more confident now.", "Still rushes it in matches.", None)
SESSION_NOTES = (
    "Good energy. The rondo worked well once we made the area bigger.",
    "Wet pitch, so we cut the game short. Group B found the opposed drill hard.",
    "Best session in a while: lots of shots, and the keepers were busy.",
    "Quiet one with a few away. Kept it simple.",
)
BLOCK_NOTES = ("Made the area smaller halfway through.", "Needed more balls, so add a spare bag next time.")


def periods_for(today: date) -> list[tuple[str, date]]:
    """Three half-season periods ending with the current one: (label, start)."""
    autumn = today.month >= 8
    year = today.year
    current = (f"Autumn {year}", date(year, 8, 1)) if autumn else (f"Spring {year}", date(year, 1, 1))
    middle = (f"Spring {year}", date(year, 1, 1)) if autumn else (f"Autumn {year - 1}", date(year - 1, 8, 1))
    first = (f"Autumn {year - 1}", date(year - 1, 8, 1)) if autumn else (f"Spring {year - 1}", date(year - 1, 1, 1))
    return [first, middle, current]


def training_days(today: date) -> tuple[list[date], list[date]]:
    """Tuesdays and Thursdays: the last eight before today, and the next two."""
    days = [today + timedelta(days=d) for d in range(-35, 10) if (today + timedelta(days=d)).weekday() in (1, 3)]
    return [d for d in days if d < today][-8:], [d for d in days if d >= today][:2]


def confirm_priorities(db, rng, player, period, user, ratings, number=1, previous=()):
    cycle = DevelopmentCycle(player_id=player.id, period_id=period.id, number=number, created_by=user.id)
    db.add(cycle)
    db.flush()
    skills = weakest(rng, {k: v for k, v in ratings.items() if k not in previous})
    for rank, skill_id in enumerate(skills, start=1):
        db.add(PriorityConfirmation(player_id=player.id, period_id=period.id, cycle_id=cycle.id, rank=rank, skill_id=skill_id,
                                    algorithm_suggested=rank != 2, coach_note=PRIORITY_NOTES[rank - 1] if rank != 3 else None))
    db.flush()
    return cycle, skills


def build_squad(db, user: User, name: str, today: date) -> tuple[Team, Period, list[Player]]:
    starter = starter_version(db)
    team = Team(name=name, self_assessment_enabled=True, player_gender="mixed")
    db.add(team)
    db.flush()
    db.add(Membership(team_id=team.id, user_id=user.id, role="owner"))
    periods = []
    for index, (label, _) in enumerate(periods_for(today)):
        period = Period(team_id=team.id, label=label, is_active=False, matrix_version_id=starter.id, starts_season=label.startswith("Autumn"))
        db.add(period)
        db.flush()
        periods.append(period)
    periods[-1].is_active = True
    db.flush()

    players = []
    for player_index, (player_name, position) in enumerate(ROSTER):
        player = Player(team_id=team.id, name=player_name, name_key=player_name.casefold(), active=player_name != LEFT)
        db.add(player)
        db.flush()
        players.append(player)
        rng = random.Random(f"demo/{player_name}")
        coach_periods = coach_scores_by_period(rng, starter.document, position, len(periods))
        previous = []
        for period_index, period in enumerate(periods):
            current = period_index == len(periods) - 1
            if (player_name == LEFT and period_index > 0) or (player_name == JOINED and not current):
                continue
            db.add(PlayerGroup(player_id=player.id, period_id=period.id, age_group=AGE_GROUP - (len(periods) - 1 - period_index) // 2))
            ratings = dict(coach_periods[period_index])
            # Last period's priorities mostly improve, so the progress views have something to show.
            for skill_id in previous:
                ratings[skill_id] = clamp(coach_periods[period_index - 1][skill_id] + rng.choices((-1, 0, 1), weights=(1, 3, 6))[0])
            coach_periods[period_index] = ratings
            notes = {skill_id: rng.choice(RATING_NOTES) for skill_id in rng.sample(sorted(ratings), 2)}
            note = "Settled in well this period." if current and player_index % 3 == 0 else None
            add_assessment(db, player, period, "coach", position, user, ratings, notes, note)
            if (player_index + period_index) % 4 != 0:
                add_assessment(db, player, period, "player", position, user, self_scores(rng, ratings))
            if player_name == JOINED:
                continue
            cycle, previous = confirm_priorities(db, rng, player, period, user, ratings)
            save_generated(db, team.id, player.id, period.id, 4, user, squad_run=True)
            # A third of the squad are on their second plan this period, after a check-in on the first.
            if current and player_index % 3 == 1:
                for skill_id, note in zip(previous, CHECKIN_NOTES):
                    db.add(CycleCheckin(cycle_id=cycle.id, skill_id=skill_id, trend=rng.choice(("better", "better", "same")),
                                        note=note, created_by=user.id))
                _, second = confirm_priorities(db, rng, player, period, user, ratings, number=2, previous=previous[:1])
                save_generated(db, team.id, player.id, period.id, 4, user, squad_run=True)
                previous = second
        if player_index % 4 == 0 and player_name not in (LEFT, JOINED):
            db.add(PlayerReport(player_id=player.id, period_id=periods[-1].id, updated_by=user.id, updated_at=utcnow(),
                                message="Great attitude this term. Keep working on your focus areas at home."))
    return team, periods[-1], players


def add_sessions(db, user: User, team: Team, period: Period, players: list[Player], today: date):
    rng = random.Random("demo/sessions")
    squad = [p.id for p in players if p.active]
    focus = [f["tag_id"] for f in suggested_focus(team.id, period.id, db, user)]
    past, upcoming = training_days(today)
    for index, day in enumerate(past + upcoming):
        away = set(rng.sample(squad, rng.choice((0, 1, 2))))
        groups = index % 3 == 1
        session = create_session(team.id, SessionIn(
            period_id=period.id, date=day, start_time="18:00" if day.weekday() == 1 else "18:30",
            length=(60, 75, 90, 60)[index % 4], focus_tags=[focus[index % len(focus)]] + ([focus[(index + 1) % len(focus)]] if index % 2 else []),
            player_ids=[pid for pid in squad if pid not in away], versions="groups" if groups else "single",
            group_count=3 if index % 6 == 4 else 2), db, user)
        if day < today:
            # Most expected players came; now and then one didn't, and someone not expected turned up.
            no_show = set(rng.sample(sorted(set(squad) - away), 1)) if index % 2 else set()
            surprise = set(list(away)[:1]) if index % 3 == 0 else set()
            rows = [AttendanceRow(player_id=pid, attended=(pid not in away and pid not in no_show) or pid in surprise) for pid in squad]
            set_attendance(team.id, session["id"], AttendanceIn(players=rows), db, user)
            if index % 2 == 0:
                update_session(team.id, session["id"], SessionPatch(notes=SESSION_NOTES[index // 2 % len(SESSION_NOTES)]), db, user)
            drills = [b for b in session["blocks"] if b["drill"]]
            if drills and index % 3 != 2:
                change_block(team.id, session["id"], drills[0]["id"], BlockPatch(notes=rng.choice(BLOCK_NOTES)), db, user)
        elif day == upcoming[-1] and away:
            # Pre-entered: a player has said they can't come.
            set_attendance(team.id, session["id"], AttendanceIn(players=[AttendanceRow(player_id=squad[0], expected=False)]), db, user)


def like_drills(db, user: User):
    for drill in db.query(Drill).filter(Drill.slug.in_(["rondo-4v1", "races-to-the-ball-on-the-coachs-call", "three-v-three-games-in-four-minute-blocks"])).all():
        if not db.get(DrillVote, (user.id, drill.id)):
            db.add(DrillVote(user_id=user.id, drill_id=drill.id, vote=1, updated_at=utcnow()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed_demo", description="Give an account a full demo squad (development sites only).")
    parser.add_argument("email")
    parser.add_argument("--team", default=DEFAULT_TEAM, help=f"team name (default {DEFAULT_TEAM!r})")
    args = parser.parse_args(argv)
    require_dev_site()
    email, name = args.email.strip().casefold(), args.team.strip()
    today = date.today()
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).first()
        if not user:
            print(f"No account for {email}. Create it with: python -m app.admin create-user {email}", file=sys.stderr)
            return 1
        old = db.query(Team).join(Membership).filter(Team.name == name, Membership.user_id == user.id, Membership.role == "owner").first()
        if db.query(Team).filter(Team.name == name).count() > (1 if old else 0):
            print(f"Another account already has a team called {name!r}. Pick another name with --team.", file=sys.stderr)
            return 1
        if old:
            delete_team(old.id, TeamDelete(confirm_name=name), db, user)
        team, period, players = build_squad(db, user, name, today)
        like_drills(db, user)
        db.commit()
        add_sessions(db, user, team, period, players, today)
    print(f"{email} now owns {name!r}: {len(ROSTER)} players, three periods, plans and training sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

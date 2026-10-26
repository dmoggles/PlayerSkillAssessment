"""Practice scenarios: the library coaches browse and preview, what they set a player, the player's link, and the
player's attempts and how they're going. Scoring happens in the app; this checks that an attempt fits its frame."""
from collections import Counter
from datetime import date, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..auth import current_user, digest, fresh_token, require_member
from ..config import settings
from ..database import get_db
from ..models import Player, PracticeAssignment, PracticeAttempt, PracticeLink, User, utcnow
from .. import practice
from .teams import scoped_player

router = APIRouter(tags=["practice"])

LINK_DAYS = 30  # a player's link works this long; issuing a new one replaces it
ATTEMPTS_PER_HOUR = 300  # more than any player needs, so a stuck or scripted page can't flood the table
WEEKS = 8  # weeks of attempts in a coach's summary
RECENT = 50  # attempts the most-missed checks are counted over


@router.get("/practice/scenarios")
def scenario_library(user: User = Depends(current_user)):
    """Every topic with its stages, and every scenario with its pitch filled in from its format."""
    return practice.library()


# What a player has been set, and how they've done.

def assigned_ids(assignments: list[PracticeAssignment]) -> list[str]:
    """The scenarios a player's assignments cover, in library order, each once."""
    wanted = set()
    for a in assignments:
        wanted |= {a.scenario_id} if a.scenario_id else {s["id"] for s in practice.scenarios() if s["topic"] == a.topic and s["stage"] == a.stage}
    return [s["id"] for s in practice.scenarios() if s["id"] in wanted]


def stars(first_tries: list[int]) -> int:
    """As the app works them out: from each frame's first try, 90 or more on average for three, 60 for two."""
    if not first_tries:
        return 0
    average = sum(first_tries) / len(first_tries)
    return 3 if average >= 90 else 2 if average >= 60 else 1


def scenario_progress(scenario: dict, attempts: list[PracticeAttempt]) -> dict:
    """Which frames the player has checked, and stars once they've done them all (from their latest first tries)."""
    mine = [a for a in attempts if a.scenario_id == scenario["id"]]
    latest_first = {}
    for a in sorted(mine, key=lambda a: a.id):
        if a.attempt_no == 1:
            latest_first[a.frame_id] = a.points
    frames = [f["id"] for f in scenario["frames"]]
    done = all(f in latest_first for f in frames)
    return {"frames_done": sum(f in latest_first for f in frames), "frames": len(frames), "done": done,
            "stars": stars([latest_first[f] for f in frames]) if done else 0}


def assignment_out(a: PracticeAssignment, library: dict[str, dict]) -> dict:
    if a.scenario_id:
        label = library[a.scenario_id]["title"] if a.scenario_id in library else "A scenario no longer in the library"
    else:
        topic = practice.TOPICS.get(a.topic, {})
        label = f"{topic.get('label', a.topic)}, stage {a.stage}: {topic.get('stages', {}).get(a.stage, '')}".rstrip(": ")
    return {"id": a.id, "topic": a.topic, "stage": a.stage, "scenario_id": a.scenario_id, "label": label,
            "due_on": a.due_on, "assigned_at": a.assigned_at,
            "scenario_ids": assigned_ids([a])}


def summary(attempts: list[PracticeAttempt], library: dict[str, dict], today: date) -> dict:
    """For the coach: attempts and average first-try points each week, average points by concept, and the checks
    missed most often lately."""
    firsts = [a for a in attempts if a.attempt_no == 1]
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=WEEKS - 1)
    weeks = []
    for n in range(WEEKS):
        begin = start + timedelta(weeks=n)
        in_week = [a for a in attempts if begin <= a.created_at.astimezone(timezone.utc).date() < begin + timedelta(weeks=1)]
        points = [a.points for a in in_week if a.attempt_no == 1]
        weeks.append({"week_of": begin, "attempts": len(in_week), "average": round(sum(points) / len(points)) if points else None})
    by_concept = {}
    for a in firsts:
        for concept in library.get(a.scenario_id, {}).get("concepts", []):
            by_concept.setdefault(concept, []).append(a.points)
    missed = Counter(check for a in sorted(attempts, key=lambda a: a.id)[-RECENT:] for check in a.failed_checks)
    return {"attempts": len(attempts), "weeks": weeks,
            "concepts": [{"concept": c, "average": round(sum(p) / len(p)), "tries": len(p)} for c, p in sorted(by_concept.items())],
            "missed": [{"check": c, "count": n} for c, n in missed.most_common(3)]}


def practice_state(db: DbSession, player: Player) -> dict:
    library = practice.by_id()
    assignments = db.query(PracticeAssignment).filter_by(player_id=player.id).order_by(PracticeAssignment.id).all()
    attempts = db.query(PracticeAttempt).filter_by(player_id=player.id).order_by(PracticeAttempt.id).all()
    link = db.query(PracticeLink).filter_by(player_id=player.id).first()
    now = utcnow()
    return {"link": {"issued_at": link.issued_at, "expires_at": link.expires_at, "opened_at": link.opened_at,
                     "active": link.expires_at.replace(tzinfo=timezone.utc) > now} if link else None,
            "assignments": [assignment_out(a, library) for a in assignments],
            "progress": {sid: scenario_progress(library[sid], attempts) for sid in assigned_ids(assignments)},
            "summary": summary(attempts, library, now.date())}


# The coach's side.

class AssignmentIn(BaseModel):
    topic: str | None = None
    stage: int | None = None
    scenario_id: str | None = None
    due_on: date | None = None


@router.get("/teams/{team_id}/players/{player_id}/practice")
def player_practice(team_id: int, player_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """What the player has been set, their link, their progress and a summary of their attempts. Practice, not
    assessment: none of it feeds the coach's ratings."""
    require_member(team_id, db, user)
    return practice_state(db, scoped_player(db, team_id, player_id))


@router.post("/teams/{team_id}/players/{player_id}/practice/assignments", status_code=201)
def assign(team_id: int, player_id: int, body: AssignmentIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Set a player a scenario, or a whole stage of a topic, with an optional date to do it by."""
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    if not player.active:
        raise HTTPException(409, "Restore the player to set them practice")
    if body.scenario_id:
        scenario = practice.by_id().get(body.scenario_id)
        if not scenario or body.stage is not None:
            raise HTTPException(422, "Choose a scenario from the library")
        row = PracticeAssignment(topic=scenario["topic"], scenario_id=scenario["id"])
    else:
        topic = practice.TOPICS.get(body.topic)
        if not topic or body.stage not in topic["stages"] or not any(s["topic"] == body.topic and s["stage"] == body.stage for s in practice.scenarios()):
            raise HTTPException(422, "Choose a topic and one of its stages")
        row = PracticeAssignment(topic=body.topic, stage=body.stage)
    row.team_id, row.player_id, row.assigned_by, row.due_on = team_id, player.id, user.id, body.due_on
    db.add(row)
    db.commit()
    return practice_state(db, player)


@router.delete("/teams/{team_id}/players/{player_id}/practice/assignments/{assignment_id}")
def unassign(team_id: int, player_id: int, assignment_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Take practice off a player's list. Their attempts are kept."""
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    row = db.query(PracticeAssignment).filter_by(id=assignment_id, player_id=player.id).first()
    if not row:
        raise HTTPException(404, "Assignment not found")
    db.delete(row)
    db.commit()
    return practice_state(db, player)


@router.post("/teams/{team_id}/players/{player_id}/practice/link")
def issue_link(team_id: int, player_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """A new link for the player to practise with, replacing any earlier one. The link is only shown now."""
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    if not player.active:
        raise HTTPException(409, "Restore the player to give them a practice link")
    raw, now = fresh_token(), utcnow()
    link = db.query(PracticeLink).filter_by(player_id=player.id).first() or PracticeLink(player_id=player.id)
    link.token_hash, link.issued_at, link.expires_at, link.opened_at = digest(raw), now, now + timedelta(days=LINK_DAYS), None
    db.add(link)
    db.commit()
    return {"url": f"{settings.public_base_url}/practice/{raw}", "expires_at": link.expires_at}


@router.delete("/teams/{team_id}/players/{player_id}/practice/link")
def revoke_link(team_id: int, player_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Stop the player's link working at once."""
    require_member(team_id, db, user)
    player = scoped_player(db, team_id, player_id)
    db.query(PracticeLink).filter_by(player_id=player.id).delete()
    db.commit()
    return practice_state(db, player)


# The player's side: everything goes through their link, and sees only their own practice.

def player_for(db: DbSession, token: str) -> Player:
    link = db.query(PracticeLink).filter_by(token_hash=digest(token)).first()
    player = db.get(Player, link.player_id) if link else None
    if not player or not player.active or link.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(404, "This practice link has expired or been replaced. Ask your coach for a new one.")
    return player


@router.get("/practice/{token}")
def my_practice(token: str, db: DbSession = Depends(get_db)):
    """The player's first name, and each piece of practice they've been set with its scenarios and their progress."""
    player = player_for(db, token)
    link = db.query(PracticeLink).filter_by(player_id=player.id).first()
    if not link.opened_at:
        link.opened_at = utcnow()
        db.commit()
    library = practice.by_id()
    assignments = db.query(PracticeAssignment).filter_by(player_id=player.id).order_by(PracticeAssignment.id).all()
    attempts = db.query(PracticeAttempt).filter_by(player_id=player.id).all()
    return {"name": player.name.split()[0],
            "assignments": [{**{k: v for k, v in assignment_out(a, library).items() if k in ("id", "label", "due_on")},
                             "scenarios": [{**library[sid], "progress": scenario_progress(library[sid], attempts)} for sid in assigned_ids([a])]}
                            for a in assignments]}


class AttemptIn(BaseModel):
    scenario_id: str = Field(max_length=80)
    frame_id: str = Field(max_length=40)
    attempt_no: int = Field(ge=1, le=100)
    x: float | None = Field(None, ge=0, le=200)
    y: float | None = Field(None, ge=0, le=200)
    points: int = Field(ge=0, le=100)
    zone_hit: int | None = Field(None, ge=0, le=practice.MAX_ZONES - 1)
    failed_checks: list[str] = Field(default_factory=list, max_length=10)
    duration_ms: int = Field(ge=0, le=3_600_000)


@router.post("/practice/{token}/attempts", status_code=201)
def save_attempt(token: str, body: AttemptIn, db: DbSession = Depends(get_db)):
    """Keep one check of one frame of a scenario the player has been set. It must fit the frame: a position on the
    pitch, points one of its zones gives, and only checks the frame runs."""
    player = player_for(db, token)
    if body.scenario_id not in assigned_ids(db.query(PracticeAssignment).filter_by(player_id=player.id).all()):
        raise HTTPException(404, "This scenario isn't on your list")
    scenario = practice.by_id()[body.scenario_id]
    frame = next((f for f in scenario["frames"] if f["id"] == body.frame_id), None)
    if not frame:
        raise HTTPException(422, "Unknown step")
    zones = frame["target"]["zones"]
    fits_zone = (body.zone_hit is None and body.points == 0) or (body.zone_hit is not None and body.zone_hit < len(zones) and zones[body.zone_hit]["points"] == body.points)
    on_pitch = body.x is not None and body.y is not None and body.x <= scenario["pitch"]["length"] and body.y <= scenario["pitch"]["width"]
    if not fits_zone or not on_pitch or not set(body.failed_checks) <= {c["check"] for c in frame["target"].get("checks", [])}:
        raise HTTPException(422, "That answer doesn't fit this step")
    if db.query(PracticeAttempt).filter(PracticeAttempt.player_id == player.id, PracticeAttempt.created_at > utcnow() - timedelta(hours=1)).count() >= ATTEMPTS_PER_HOUR:
        raise HTTPException(429, "That's a lot of practice for one hour. Have a rest and come back later.")
    db.add(PracticeAttempt(player_id=player.id, **body.model_dump()))
    db.commit()
    return {"saved": True}

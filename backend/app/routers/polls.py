"""Coaching polls, on the development site only: situations from a game where coaches put the player where they'd
coach them to go, with no scoring. Anyone with the link can answer; a site admin sees every answer on the pitch.
Polls are content in app/data/polls.json. With polls_enabled off (production), every route here answers 404."""
import json
import re
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DbSession
from ..config import settings
from ..database import get_db
from ..models import PollAnswer, User, utcnow
from .. import practice
from .accounts import throttle
from .admin import require_admin

DATA = Path(__file__).resolve().parent.parent / "data" / "polls.json"
RESPONDENT = re.compile(r"^[A-Za-z0-9-]{16,64}$")  # the random id a respondent's browser makes
SAVES_PER_WINDOW = 1000  # answers one address can save in 15 minutes: enough for a room of coaches on one wifi


def enabled():
    if not settings.polls_enabled:
        raise HTTPException(404, "Not found")


router = APIRouter(prefix="/polls", tags=["polls"], dependencies=[Depends(enabled)])


@lru_cache
def polls() -> dict[str, dict]:
    """Every poll by id, each situation with its format's pitch filled in."""
    formats = json.loads((Path(__file__).resolve().parent.parent / "data" / "practice_scenarios.json").read_text())["formats"]
    found = {}
    for poll in json.loads(DATA.read_text())["polls"]:
        for s in poll["scenarios"]:
            s["pitch"] = practice.pitch_for(s, formats)
        found[poll["id"]] = poll
    return found


def poll_problems(poll: dict) -> list[str]:
    """What's wrong with a poll's situations: everyone and every reference spot on the pitch, ids unique, and the
    player you move and the ball's holder there."""
    problems, seen = [], set()
    for s in poll["scenarios"]:
        where = f"{poll['id']}/{s['id']}"
        if s["id"] in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(s["id"])
        pitch = s["pitch"]
        depth = min(pitch["length"], (s.get("view") or {}).get("depth", pitch["length"] / 2 + 5))
        for p in s["team"] + s["opponents"] + s["references"] + [s["ball"]]:
            if not (0 <= p["x"] <= depth and 0 <= p["y"] <= pitch["width"]):
                problems.append(f"{where}: {p.get('id') or p.get('label') or 'ball'} is off the pitch drawn")
        if not any(p["id"] == s["controlled"] for p in s["team"]):
            problems.append(f"{where}: no player to move")
        if not any(p["id"] == s["ball"]["with"] for p in s["opponents"]):
            problems.append(f"{where}: the ball's holder is missing")
    return problems


def poll_for(poll_id: str) -> dict:
    poll = polls().get(poll_id)
    if not poll:
        raise HTTPException(404, "Poll not found")
    return poll


def respondent_ok(value: str) -> str:
    if not RESPONDENT.match(value):
        raise HTTPException(422, "Unknown respondent")
    return value


@router.get("/{poll_id}")
def get_poll(poll_id: str, respondent: str | None = None, db: DbSession = Depends(get_db)):
    """A poll to answer, without the reference spots (they'd hint at answers), and this respondent's answers so far."""
    poll = poll_for(poll_id)
    mine = db.query(PollAnswer).filter_by(poll_id=poll_id, respondent=respondent_ok(respondent)).all() if respondent else []
    return {"id": poll["id"], "title": poll["title"], "intro": poll["intro"],
            "scenarios": [{k: v for k, v in s.items() if k != "references"} for s in poll["scenarios"]],
            "name": next((a.name for a in mine if a.name), None),
            "answers": {a.scenario_id: {"x": a.x, "y": a.y} for a in mine}}


class AnswerIn(BaseModel):
    respondent: str
    name: str | None = Field(None, max_length=60)
    x: float = Field(ge=0, le=200)
    y: float = Field(ge=0, le=200)

    @field_validator("name")
    @classmethod
    def tidy(cls, value):
        value = " ".join((value or "").split())
        return value or None


@router.put("/{poll_id}/answers/{scenario_id}")
def save_answer(poll_id: str, scenario_id: str, body: AnswerIn, request: Request, db: DbSession = Depends(get_db)):
    """Keep where this respondent would put the player; a second answer to the same situation replaces the first.
    Their name, if given, goes on all their answers."""
    poll = poll_for(poll_id)
    scenario = next((s for s in poll["scenarios"] if s["id"] == scenario_id), None)
    if not scenario:
        raise HTTPException(404, "Unknown situation")
    respondent_ok(body.respondent)
    if body.x > scenario["pitch"]["length"] or body.y > scenario["pitch"]["width"]:
        raise HTTPException(422, "That's off the pitch")
    throttle(db, request, "poll", poll_id, SAVES_PER_WINDOW)
    now = utcnow()
    answer = db.query(PollAnswer).filter_by(poll_id=poll_id, respondent=body.respondent, scenario_id=scenario_id).first()
    if not answer:
        answer = PollAnswer(poll_id=poll_id, respondent=body.respondent, scenario_id=scenario_id, created_at=now)
        db.add(answer)
    answer.x, answer.y, answer.updated_at = round(body.x, 2), round(body.y, 2), now
    db.query(PollAnswer).filter_by(poll_id=poll_id, respondent=body.respondent).update({"name": body.name})
    answer.name = body.name
    db.commit()
    return {"saved": True}


@router.get("/{poll_id}/results")
def results(poll_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Every situation with its reference spots (for grouping answers) and everyone's answers."""
    poll = poll_for(poll_id)
    # Answers to situations since taken out of the poll aren't shown or counted.
    current = {s["id"] for s in poll["scenarios"]}
    answers = [a for a in db.query(PollAnswer).filter_by(poll_id=poll_id).order_by(PollAnswer.created_at) if a.scenario_id in current]
    people, names = [], {}
    for a in answers:
        if a.respondent not in names:
            people.append(a.respondent)
        names[a.respondent] = names.get(a.respondent) or a.name
    return {"id": poll["id"], "title": poll["title"], "scenarios": poll["scenarios"],
            "respondents": [{"id": r, "name": names[r], "answered": sum(a.respondent == r for a in answers)} for r in people],
            "answers": [{"respondent": a.respondent, "scenario_id": a.scenario_id, "x": a.x, "y": a.y, "updated_at": a.updated_at} for a in answers]}


@router.delete("/{poll_id}/respondents/{respondent}", status_code=204)
def remove_respondent(poll_id: str, respondent: str, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Take out one respondent's answers, such as a test run."""
    poll_for(poll_id)
    db.query(PollAnswer).filter_by(poll_id=poll_id, respondent=respondent_ok(respondent)).delete()
    db.commit()

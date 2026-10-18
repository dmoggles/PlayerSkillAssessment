"""A team's own drills: written by its coaches in a form, seen only by them, and used by the planners like any
library drill. They have no diagrams; a coach can add a YouTube or Vimeo link. A coach can offer one to the shared
library (see DrillSubmission)."""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, require_member
from ..database import get_db
from ..drills import apply_row, drill_problems
from ..models import Drill, DrillSubmission, SkillTag, User, utcnow
from .drills import drill_out, list_drills

router = APIRouter(tags=["drills"])
TEAM_SOURCE = "team"


class Version(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    change: str = Field(min_length=1, max_length=500)


class EquipmentIn(BaseModel):
    item: str
    quantity: int | None = Field(default=None, ge=1, le=99)


class TeamDrillIn(BaseModel):
    """The editor's fields. Easier and harder versions are optional; the rest is what every drill has."""
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=300)
    session_phase: str
    format: str
    players: list[int] = Field(min_length=3, max_length=3)
    ages: list[int] = Field(min_length=2, max_length=2)
    duration: list[int] = Field(min_length=2, max_length=2)
    intensity: str
    space: list[float] | None = Field(default=None, min_length=2, max_length=2)
    equipment: list[EquipmentIn] = Field(default=[], max_length=12)
    setup: str = Field(min_length=1, max_length=2000)
    instructions: list[str] = Field(min_length=1, max_length=12)
    coaching_points: list[str] = Field(default=[], max_length=12)
    tags: dict[str, float] = Field(default={}, max_length=6)
    home_friendly: bool = False
    indoors: str | None = Field(default=None, max_length=1000)
    easier: Version | None = None
    harder: Version | None = None
    video_url: str | None = Field(default=None, max_length=300)


def levels_for(easier: bool, harder: bool) -> dict[str, list[int]]:
    """Level ranges on the 1-5 scale for the versions a team drill has: easier, base and harder share the scale."""
    if easier and harder:
        return {"regression": [1, 2], "base": [2, 4], "escalator": [4, 5]}
    if easier:
        return {"regression": [1, 2], "base": [2, 5]}
    if harder:
        return {"base": [1, 4], "escalator": [4, 5]}
    return {"base": [1, 5]}


def row_from(body: TeamDrillIn, slug: str) -> dict:
    """The form as a data-file row, so it is checked and saved exactly like a library drill."""
    levels = levels_for(body.easier is not None, body.harder is not None)
    clean = lambda items: [i.strip() for i in items if i.strip()]
    variations = []
    if body.easier:
        variations.append({"kind": "regression", "title": body.easier.title.strip(), "change": body.easier.change.strip(), "levels": levels["regression"]})
    variations.append({"kind": "base", "title": body.title.strip(), "change": body.summary.strip(), "levels": levels["base"]})
    if body.harder:
        variations.append({"kind": "escalator", "title": body.harder.title.strip(), "change": body.harder.change.strip(), "levels": levels["escalator"]})
    row = {"slug": slug, "title": body.title.strip(), "summary": body.summary.strip(), "format": body.format, "players": body.players,
           "ages": body.ages, "duration": body.duration, "session_phase": body.session_phase, "intensity": body.intensity,
           "space": body.space, "home_friendly": body.home_friendly,
           "equipment": [{"item": e.item, **({"quantity": e.quantity} if e.quantity else {})} for e in body.equipment],
           "setup": body.setup.strip(), "instructions": clean(body.instructions), "coaching_points": clean(body.coaching_points),
           "tags": body.tags, "variations": variations,
           "media": [{"kind": "video", "url": body.video_url.strip(), "caption": ""}] if body.video_url and body.video_url.strip() else []}
    if body.home_friendly and body.indoors and body.indoors.strip():
        row["indoors"] = body.indoors.strip()
    if not row["space"]:
        del row["space"]
    return row


# The data checks' wording, for coaches: what to fix in the form.
PLAIN = (
    ("needs at least one Main (1.0) tag", "Choose at least one skill this drill mainly trains."),
    ("players must be", "Players: the smallest number, the best number and the most, in that order."),
    ("ages must be", "Ages: the youngest and oldest age group, from U4 to U23."),
    ("duration must be", "Minutes: the shortest useful run and the usual length, shortest first."),
    ("url must be https", "The video link must start with https://."),
    ("videos must be YouTube or Vimeo", "Videos must be YouTube or Vimeo links."),
    ("indoors must be text", "Indoor instructions only go with a drill that can be done at home."),
)


def plain(problem: str) -> str:
    return next((text for key, text in PLAIN if key in problem), problem[0].upper() + problem[1:] + ".")


def _slug_for(db: DbSession, team_id: int, title: str) -> str:
    base = f"t{team_id}-" + (re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:60].strip("-") or "drill")
    slug, n = base, 2
    while db.query(Drill.id).filter_by(slug=slug).first():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _team_drill(db: DbSession, team_id: int, slug: str) -> Drill:
    drill = db.query(Drill).filter_by(slug=slug, team_id=team_id, status="published").first()
    if not drill:
        raise HTTPException(404, "Drill not found")
    return drill


def _checked_row(db: DbSession, body: TeamDrillIn, slug: str) -> dict:
    """The form as a row, checked like a library drill; a 422 in plain words when something needs fixing."""
    row = row_from(body, slug)
    problems = drill_problems(row, {t.id for t in db.query(SkillTag).filter_by(active=True)})
    if problems:
        raise HTTPException(422, " ".join(dict.fromkeys(plain(p) for p in problems)))
    return row


def _save(db: DbSession, drill: Drill, row: dict, user: User):
    apply_row(db, drill, row, TEAM_SOURCE, variations_by_kind=True)
    drill.updated_by = user.id


@router.get("/teams/{team_id}/drills")
def team_drills(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The team's own drills, in the library's list format."""
    return [d for d in list_drills(team_id, db, user) if d["team_id"] == team_id]


@router.post("/teams/{team_id}/drills", status_code=201)
def create_team_drill(team_id: int, body: TeamDrillIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    slug = _slug_for(db, team_id, body.title)
    row = _checked_row(db, body, slug)
    drill = Drill(slug=slug, team_id=team_id, created_by=user.id, created_at=utcnow())
    db.add(drill)
    _save(db, drill, row, user)
    record(db, team_id, user, "team_drill_added", title=drill.title)
    db.commit()
    return drill_out(db, drill, user)


@router.put("/teams/{team_id}/drills/{slug}")
def update_team_drill(team_id: int, slug: str, body: TeamDrillIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Save the form again. Each version keeps its id, so sessions and plans that use it stay pointed at it."""
    require_member(team_id, db, user)
    drill = _team_drill(db, team_id, slug)
    _save(db, drill, _checked_row(db, body, slug), user)
    db.commit()
    return drill_out(db, drill, user)


@router.delete("/teams/{team_id}/drills/{slug}")
def delete_team_drill(team_id: int, slug: str, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Take a drill out of the team's library. It is retired rather than removed, so sessions and plans that used it
    still show it."""
    require_member(team_id, db, user)
    drill = _team_drill(db, team_id, slug)
    drill.status, drill.updated_by, drill.updated_at = "retired", user.id, utcnow()
    db.query(DrillSubmission).filter_by(drill_id=drill.id, status="pending").delete(synchronize_session=False)
    record(db, team_id, user, "team_drill_deleted", title=drill.title)
    db.commit()
    return {"message": "Drill deleted."}


class SubmitIn(BaseModel):
    note: str = Field(default="", max_length=1000)
    confirm_own: bool  # the coach confirms the drill is theirs (or their club's) to share


@router.post("/teams/{team_id}/drills/{slug}/submit", status_code=201)
def submit_team_drill(team_id: int, slug: str, body: SubmitIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Offer the drill to the shared library. An admin reviews it; accepted drills are written up with diagrams
    before they appear there."""
    require_member(team_id, db, user)
    drill = _team_drill(db, team_id, slug)
    if not body.confirm_own:
        raise HTTPException(422, "Confirm the drill is yours to share")
    if db.query(DrillSubmission).filter(DrillSubmission.drill_id == drill.id, DrillSubmission.status.in_(("pending", "accepted"))).first():
        raise HTTPException(409, "This drill has already been submitted")
    db.add(DrillSubmission(drill_id=drill.id, team_id=team_id, submitted_by=user.id, note=body.note.strip(), created_at=utcnow()))
    record(db, team_id, user, "team_drill_submitted", title=drill.title)
    db.commit()
    return drill_out(db, drill, user)

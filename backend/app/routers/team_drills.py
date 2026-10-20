"""A team's own drills: written by its coaches in a form, seen only by them, and used by the planners like any
library drill. They have no diagrams; a coach can add a YouTube or Vimeo link. A coach can offer one to the shared
library (see DrillSubmission)."""
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from .. import notify
from ..audit import record
from ..auth import current_user, require_member
from ..database import get_db
from ..drills import apply_row, drill_problems
from ..models import Drill, DrillMedia, DrillSubmission, DrillTag, DrillVariation, SkillTag, Team, User, utcnow
from .admin import require_admin
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
    # On a new drill: the library drill this is the team's version of. It replaces that drill for the team.
    shadows: str | None = Field(default=None, max_length=80)


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


def _library_to_shadow(db: DbSession, team_id: int, slug: str) -> Drill:
    """A library drill the team can make its own version of: published, and not already versioned by the team."""
    library = db.query(Drill).filter_by(slug=slug, status="published", team_id=None).first()
    if not library:
        raise HTTPException(422, "That isn't a drill in the shared library")
    existing = db.query(Drill).filter_by(team_id=team_id, shadows_drill_id=library.id, status="published").first()
    if existing:
        raise HTTPException(409, f"Your team already has its own version of {library.title}: {existing.title}")
    return library


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
    library = _library_to_shadow(db, team_id, body.shadows) if body.shadows else None
    slug = _slug_for(db, team_id, body.title)
    row = _checked_row(db, body, slug)
    drill = Drill(slug=slug, team_id=team_id, shadows_drill_id=library.id if library else None, created_by=user.id, created_at=utcnow())
    db.add(drill)
    _save(db, drill, row, user)
    record(db, team_id, user, "team_drill_added", title=drill.title, **({"version_of": library.title} if library else {}))
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


@router.post("/teams/{team_id}/drills/{slug}/unlink")
def unlink_team_drill(team_id: int, slug: str, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Stop the drill being the team's version of a library drill: both show, as separate drills."""
    require_member(team_id, db, user)
    drill = _team_drill(db, team_id, slug)
    if not drill.shadows_drill_id:
        raise HTTPException(409, "This drill isn't linked to a library drill")
    drill.shadows_drill_id, drill.updated_by, drill.updated_at = None, user.id, utcnow()
    db.commit()
    return drill_out(db, drill, user)


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
    submission = DrillSubmission(drill_id=drill.id, team_id=team_id, submitted_by=user.id, note=body.note.strip(), created_at=utcnow())
    db.add(submission)
    record(db, team_id, user, "team_drill_submitted", title=drill.title)
    db.commit()
    notify.drill_submitted(db, submission, drill, db.get(Team, team_id), user)
    return drill_out(db, drill, user)


# Site admins: drills teams offer to the shared library. Accepting reserves a library slug and gives the drill as a
# data-file row; it is published when a data file with that slug is loaded (see load_file), written up with
# diagrams like any library drill. Nothing a team writes reaches other teams before that.
SubmissionStatus = Literal["pending", "accepted", "declined", "published"]


def row_for(db: DbSession, drill: Drill, slug: str) -> dict:
    """A drill as a data-file row: the reverse of apply_row, for starting the library version from."""
    variations = db.query(DrillVariation).filter_by(drill_id=drill.id).order_by(DrillVariation.position)
    row = {"slug": slug, "title": drill.title, "summary": drill.summary, "format": drill.format,
           "players": [drill.players_min, drill.players_ideal, drill.players_max], "ages": [drill.age_min, drill.age_max],
           "duration": [drill.duration_min, drill.duration_typical], "session_phase": drill.session_phase, "intensity": drill.intensity}
    if drill.space_width_m is not None:
        row["space"] = [float(drill.space_width_m), float(drill.space_length_m)]
    row.update(home_friendly=drill.home_friendly, equipment=drill.equipment, setup=drill.setup, instructions=drill.instructions,
               coaching_points=drill.coaching_points,
               tags={t.tag_id: t.weight for t in db.query(DrillTag).filter_by(drill_id=drill.id)},
               variations=[{"kind": v.kind, "title": v.title, "change": v.change, "levels": [v.level_min, v.level_max]} for v in variations],
               media=[{"kind": m.kind, "url": m.url, "caption": m.caption} for m in db.query(DrillMedia).filter_by(drill_id=drill.id).order_by(DrillMedia.position)])
    if drill.indoors:
        row["indoors"] = drill.indoors
    return row


def submission_item(db: DbSession, s: DrillSubmission) -> dict:
    drill, team = db.get(Drill, s.drill_id), db.get(Team, s.team_id)
    return {"id": s.id, "status": s.status, "note": s.note, "reason": s.reason, "created_at": s.created_at, "reviewed_at": s.reviewed_at,
            "library_slug": s.library_slug, "team": team.name if team else None, "drill": drill_out(db, drill, None)}


def _submission(db: DbSession, submission_id: int) -> DrillSubmission:
    s = db.get(DrillSubmission, submission_id)
    if not s:
        raise HTTPException(404, "Submission not found")
    return s


class AcceptIn(BaseModel):
    library_slug: str = Field(default="", max_length=80)  # empty: made from the title


class DeclineIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/admin/drill-submissions")
def submission_queue(status: SubmissionStatus = "pending", db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Waiting ones oldest first, so none waits forever; the other lists newest first."""
    query = db.query(DrillSubmission).filter_by(status=status)
    order = DrillSubmission.id if status == "pending" else DrillSubmission.id.desc()
    return [submission_item(db, s) for s in query.order_by(order).limit(200)]


@router.post("/admin/drill-submissions/{submission_id}/accept")
def accept_submission(submission_id: int, body: AcceptIn, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    s = _submission(db, submission_id)
    if s.status not in ("pending", "declined"):
        raise HTTPException(409, "Only submissions waiting for review, or declined, can be accepted")
    drill = db.get(Drill, s.drill_id)
    slug = body.library_slug.strip() or re.sub(r"[^a-z0-9]+", "-", drill.title.casefold()).strip("-")[:80]
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) or re.match(r"t\d+-", slug):
        raise HTTPException(422, "The library slug is lowercase letters, digits and hyphens, and doesn't start like a team drill's")
    if db.query(Drill.id).filter_by(slug=slug).first() or db.query(DrillSubmission.id).filter(DrillSubmission.library_slug == slug, DrillSubmission.id != s.id).first():
        raise HTTPException(409, "A drill already has that slug: choose another")
    s.status, s.library_slug, s.reason, s.reviewed_by, s.reviewed_at = "accepted", slug, "", admin.id, utcnow()
    db.commit()
    return submission_item(db, s)


@router.post("/admin/drill-submissions/{submission_id}/decline")
def decline_submission(submission_id: int, body: DeclineIn, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Decline a submission, saying why; the team sees the reason on its drill."""
    s = _submission(db, submission_id)
    if s.status not in ("pending", "accepted"):
        raise HTTPException(409, "This submission has already been declined or published")
    s.status, s.library_slug, s.reason, s.reviewed_by, s.reviewed_at = "declined", None, body.reason.strip(), admin.id, utcnow()
    db.commit()
    return submission_item(db, s)


@router.get("/admin/drill-submissions/{submission_id}/row")
def submission_row(submission_id: int, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    """The drill as a data-file row with its library slug, to add to the next drills file with diagrams."""
    s = _submission(db, submission_id)
    if s.status != "accepted":
        raise HTTPException(409, "Accept the submission first")
    return row_for(db, db.get(Drill, s.drill_id), s.library_slug)

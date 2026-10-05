"""Owner-only editing of a team's skill matrix: one autosaved draft, then publish as a new version."""
import copy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, require_member
from ..database import get_db
from ..matrix import team_version
from ..matrix_editor import DraftError, active_tag_ids, classify, editable_document, normalise, problems, reserved_ids, skills_of, warnings
from ..models import Assessment, MatrixDraft, MatrixSkillTag, MatrixVersion, Period, SkillMatrix, SkillTag, Team, User, utcnow

router = APIRouter(tags=["matrices"])


class DraftIn(BaseModel):
    revision: int = Field(ge=0)
    document: dict


class PublishIn(BaseModel):
    revision: int = Field(ge=1)
    acknowledge: bool = False
    apply_to_current_period: bool = False


def draft_out(db: DbSession, team: Team, draft: MatrixDraft | None) -> dict:
    """The draft (or the current version when there is none) with what publishing would involve."""
    current = team_version(db, team)
    base_id = draft.base_version_id if draft else current.id
    base = editable_document(db, base_id)
    doc = draft.document if draft else base
    matrix = db.get(SkillMatrix, current.matrix_id)
    period = db.query(Period).filter_by(team_id=team.id, is_active=True).first()
    return {
        "current_period": {"label": period.label, "assessed": db.query(Assessment).filter_by(period_id=period.id).first() is not None}
        if period else None,
        "draft": draft is not None, "revision": draft.revision if draft else 0,
        "base_version_id": base_id, "current_version_id": current.id, "stale": base_id != current.id,
        "current": {"name": matrix.name, "version": current.version, "own": matrix.team_id is not None},
        "base_skill_ids": sorted(skills_of(base)),
        "document": doc, "problems": problems(doc, active_tag_ids(db)), "warnings": warnings(doc),
        "changes": classify(base, doc),
    }


@router.get("/skill-tags")
def skill_tags(db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The global tag taxonomy, for choosing a skill's tags."""
    return [{"id": t.id, "area": t.area, "label": t.label, "level_1": t.level_1, "level_3": t.level_3, "level_5": t.level_5,
             "active": t.active} for t in db.query(SkillTag).order_by(SkillTag.area, SkillTag.label)]


@router.get("/teams/{team_id}/matrix/draft")
def get_draft(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    return draft_out(db, db.get(Team, team_id), db.query(MatrixDraft).filter_by(team_id=team_id).first())


@router.put("/teams/{team_id}/matrix/draft")
def save_draft(team_id: int, body: DraftIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Autosave. The revision must match the stored draft (0 creates it), so owners cannot overwrite each other."""
    require_member(team_id, db, user, owner=True)
    team = db.query(Team).filter_by(id=team_id).with_for_update().first()
    draft = db.query(MatrixDraft).filter_by(team_id=team_id).first()
    if (draft.revision if draft else 0) != body.revision:
        raise HTTPException(409, "The draft was changed by another owner. Reload to continue")
    base_id = draft.base_version_id if draft else team_version(db, team).id
    base = editable_document(db, base_id)
    try:
        doc = normalise(body.document, base, reserved_ids(db, team_id, base))
    except DraftError as error:
        raise HTTPException(422, str(error))
    if not draft:
        draft = MatrixDraft(team_id=team_id, base_version_id=base_id, revision=0)
        db.add(draft)
    draft.document, draft.revision, draft.updated_by, draft.updated_at = doc, draft.revision + 1, user.id, utcnow()
    db.commit()
    return draft_out(db, team, draft)


@router.delete("/teams/{team_id}/matrix/draft")
def discard_draft(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    db.query(MatrixDraft).filter_by(team_id=team_id).delete()
    db.commit()
    return {"message": "Draft discarded"}


@router.post("/teams/{team_id}/matrix/publish")
def publish(team_id: int, body: PublishIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user, owner=True)
    team = db.query(Team).filter_by(id=team_id).with_for_update().first()
    draft = db.query(MatrixDraft).filter_by(team_id=team_id).first()
    if not draft or draft.revision != body.revision:
        raise HTTPException(409, "The draft changed. Reload before publishing")
    state = draft_out(db, team, draft)
    if state["stale"]:
        raise HTTPException(409, "A newer matrix was published since this draft started. Discard the draft and start again")
    if state["problems"]:
        raise HTTPException(409, {"message": "Fix these before publishing", "problems": state["problems"]})
    changes = state["changes"]
    if not any(changes.values()):
        raise HTTPException(409, "There are no changes to publish")
    if (changes["wording"] or changes["breaking"]) and not body.acknowledge:
        raise HTTPException(409, "Confirm that ratings for changed skills will not be directly comparable across periods")
    period = None
    if body.apply_to_current_period:
        period = db.query(Period).filter_by(team_id=team_id, is_active=True).first()
        if not period or db.query(Assessment).filter_by(period_id=period.id).first():
            raise HTTPException(409, "The current period already has assessments, so the new matrix can only apply to new periods")

    matrix = db.query(SkillMatrix).filter_by(team_id=team_id).first()
    if not matrix:
        matrix = SkillMatrix(team_id=team_id, name=f"{team.name} matrix")
        db.add(matrix)
        db.flush()
    number = (db.query(MatrixVersion.version).filter_by(matrix_id=matrix.id).order_by(MatrixVersion.version.desc()).limit(1).scalar() or 0) + 1
    doc = copy.deepcopy(draft.document)
    doc["meta"]["version"] = str(number)
    tags = {}
    for section in doc["sections"]:
        for item in [section, *section["skills"]]:
            for key in [k for k in item if k.startswith("_")]:
                del item[key]  # editor-only keys such as _key
        for skill in section["skills"]:
            tags[skill["id"]] = skill.pop("tags", {})
    version = MatrixVersion(matrix_id=matrix.id, version=number, document=doc, created_by=user.id, published_at=utcnow())
    db.add(version)
    db.flush()
    for skill_id, weights in tags.items():
        for tag_id, weight in weights.items():
            db.add(MatrixSkillTag(matrix_version_id=version.id, skill_id=skill_id, tag_id=tag_id, weight=weight))
    if period:
        period.matrix_version_id = version.id
    record(db, team_id, user, "matrix_published", version=number, applied_to=period.label if period else None,
           **{kind: len(items) for kind, items in changes.items() if items})
    db.delete(draft)
    db.commit()
    return {"version_id": version.id, "version": number, "applied_to_period": period.label if period else None}

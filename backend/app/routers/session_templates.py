"""A team's session templates: a length and the minutes for each part, shared by the team's coaches."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, require_member
from ..database import get_db
from ..models import SessionTemplate, TrainingSession, User, utcnow
from ..sessions import PHASES

router = APIRouter(tags=["sessions"])


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    length: int = Field(ge=15, le=150)
    minutes: dict[str, int] = Field(min_length=1)  # {phase: minutes}, only the parts included

    @field_validator("name")
    @classmethod
    def trimmed(cls, value):
        if not value.strip():
            raise ValueError("Give the template a name")
        return value.strip()

    @field_validator("minutes")
    @classmethod
    def known_parts(cls, value):
        unknown = sorted(set(value) - set(PHASES))
        if unknown:
            raise ValueError(f"Unknown part of a session: {', '.join(unknown)}")
        if any(not 1 <= m <= 90 for m in value.values()):
            raise ValueError("Each part takes 1 to 90 minutes")
        return {phase: value[phase] for phase in PHASES if phase in value}

    @model_validator(mode="after")
    def adds_up(self):
        total = sum(self.minutes.values())
        if total != self.length:
            raise ValueError(f"The parts add up to {total} of {self.length} minutes")
        return self


def template_out(t: SessionTemplate, used: int) -> dict:
    return {"id": t.id, "name": t.name, "length": t.length_minutes, "minutes": t.minutes, "used": used}


def _template(db: DbSession, team_id: int, template_id: int) -> SessionTemplate:
    t = db.query(SessionTemplate).filter_by(id=template_id, team_id=team_id).first()
    if not t:
        raise HTTPException(404, "Template not found")
    return t


def _name_free(db: DbSession, team_id: int, name: str, template_id: int | None = None):
    clash = db.query(SessionTemplate).filter(SessionTemplate.team_id == team_id, func.lower(SessionTemplate.name) == name.casefold(),
                                             SessionTemplate.id != (template_id or 0)).first()
    if clash:
        raise HTTPException(409, "This team already has a template with that name")


def _used(db: DbSession, template_id: int) -> int:
    return db.query(TrainingSession).filter_by(template_id=template_id).count()


@router.get("/teams/{team_id}/session-templates")
def list_templates(team_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    used = dict(db.query(TrainingSession.template_id, func.count()).filter(TrainingSession.team_id == team_id,
                                                                           TrainingSession.template_id.isnot(None)).group_by(TrainingSession.template_id))
    templates = db.query(SessionTemplate).filter_by(team_id=team_id).all()
    return [template_out(t, used.get(t.id, 0)) for t in sorted(templates, key=lambda t: t.name.casefold())]


@router.post("/teams/{team_id}/session-templates", status_code=201)
def create_template(team_id: int, body: TemplateIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    _name_free(db, team_id, body.name)
    now = utcnow()
    t = SessionTemplate(team_id=team_id, name=body.name, length_minutes=body.length, minutes=body.minutes,
                        created_by=user.id, updated_by=user.id, created_at=now, updated_at=now)
    db.add(t)
    record(db, team_id, user, "session_template_created", name=body.name)
    db.commit()
    return template_out(t, 0)


@router.put("/teams/{team_id}/session-templates/{template_id}")
def update_template(team_id: int, template_id: int, body: TemplateIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Change a template. Sessions already planned with it keep the breakdown they were planned with."""
    require_member(team_id, db, user)
    t = _template(db, team_id, template_id)
    _name_free(db, team_id, body.name, t.id)
    t.name, t.length_minutes, t.minutes = body.name, body.length, body.minutes
    t.updated_by, t.updated_at = user.id, utcnow()
    db.commit()
    return template_out(t, _used(db, t.id))


@router.delete("/teams/{team_id}/session-templates/{template_id}")
def delete_template(team_id: int, template_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Delete a template. Its sessions stay as they are."""
    require_member(team_id, db, user)
    t = _template(db, team_id, template_id)
    db.query(TrainingSession).filter_by(template_id=t.id).update({"template_id": None}, synchronize_session=False)
    record(db, team_id, user, "session_template_deleted", name=t.name)
    db.delete(t)
    db.commit()
    return {"message": "Template deleted."}

"""Team training sessions: planned from the squad's shared priorities, then edited, printed and recorded."""
from collections import Counter
from datetime import date as date_type
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, require_member
from ..cycles import current_plan
from ..database import get_db
from ..insights import player_tags, team_insights
from ..matrix import version_tags
from ..models import (Assessment, Drill, DrillVariation, Player, PlayerGroup, SessionAttendance, SessionBlock, SkillTag,
                      TrainingSession, User, utcnow)
from ..sessions import LENGTHS, plan as plan_session, split_groups
from .drills import _library
from .teams import scoped_period

router = APIRouter(tags=["sessions"])
GROUP_NAMES = ("Group A", "Group B", "Group C")
RECENT_SESSIONS = 3


class SessionIn(BaseModel):
    period_id: int
    date: date_type
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    length: int
    focus_tags: list[str] = Field(min_length=1, max_length=3)
    player_ids: list[int] = Field(min_length=1, max_length=60)
    versions: Literal["single", "groups"] = "single"
    group_count: int = Field(default=2, ge=2, le=3)
    title: str = Field(default="", max_length=120)

    @field_validator("length")
    @classmethod
    def known_length(cls, value):
        if value not in LENGTHS:
            raise ValueError(f"length must be one of {', '.join(map(str, LENGTHS))} minutes")
        return value


class SessionPatch(BaseModel):
    date: date_type | None = None
    start_time: str | None = Field(default=None, pattern=r"^(([01]\d|2[0-3]):[0-5]\d)?$")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


def _session(db: DbSession, team_id: int, session_id: int) -> TrainingSession:
    session = db.get(TrainingSession, session_id)
    if not session or session.team_id != team_id:
        raise HTTPException(404, "Session not found")
    return session


def _tag_labels(db: DbSession, tag_ids) -> dict[str, str]:
    return {t.id: t.label for t in db.query(SkillTag).filter(SkillTag.id.in_(list(tag_ids) or ["_"]))}


def _drills_for_planner(db: DbSession, age_group: int | None, user: User) -> list[dict]:
    drills, drill_tags, ladder_tags, variations, votes, tags = _library(db, age_group, user)
    return [{"slug": d.slug, "title": d.title, "session_phase": d.session_phase,
             "players": [d.players_min, d.players_ideal, d.players_max], "duration": [d.duration_min, d.duration_typical],
             "tags": drill_tags.get(d.id, {}), "tag_labels": {t["id"]: t["label"] for t in tags.get(d.id, [])},
             "ladder_tags": sorted(ladder_tags.get(d.id, set())),
             "variations": [{"id": v.id, "kind": v.kind, "title": v.title, "levels": [v.level_min, v.level_max]} for v in variations.get(d.id, [])],
             "my_vote": votes[d.id]["mine"], "net_votes": votes[d.id]["likes"] - votes[d.id]["dislikes"]}
            for d in drills if variations.get(d.id)]


def _levels(db: DbSession, period, player_ids: list[int], tag: str) -> dict[int, float | None]:
    """Each player's level on a tag, from their coach assessment in the period (None when not assessed)."""
    tags = version_tags(db, period.matrix_version_id)
    assessments = {a.player_id: a for a in db.query(Assessment).filter(
        Assessment.period_id == period.id, Assessment.assessor == "coach", Assessment.player_id.in_(player_ids))}
    return {pid: player_tags(tags, assessments[pid]).get(tag) if pid in assessments else None for pid in player_ids}


def _age_group(db: DbSession, period_id: int, player_ids: list[int]) -> int | None:
    """The most common playing group among the players, to match drills to; None when none is set."""
    ages = Counter(g.age_group for g in db.query(PlayerGroup).filter(PlayerGroup.period_id == period_id, PlayerGroup.player_id.in_(player_ids)))
    return ages.most_common(1)[0][0] if ages else None


def _recent(db: DbSession, team_id: int, before: date_type, exclude: int | None = None) -> dict[str, int]:
    """Drills from the team's last few sessions before a date: slug -> sessions ago (1 = the latest)."""
    query = db.query(TrainingSession).filter(TrainingSession.team_id == team_id, TrainingSession.date <= before)
    if exclude:
        query = query.filter(TrainingSession.id != exclude)
    sessions = query.order_by(TrainingSession.date.desc(), TrainingSession.id.desc()).limit(RECENT_SESSIONS).all()
    out = {}
    for ago, s in enumerate(sessions, start=1):
        for block in db.query(SessionBlock).filter(SessionBlock.session_id == s.id, SessionBlock.drill_id.isnot(None)):
            out.setdefault(db.get(Drill, block.drill_id).slug, ago)
    return out


def _in_plans(db: DbSession, period_id: int, player_ids: list[int]) -> dict[str, int]:
    counts = Counter()
    for pid in player_ids:
        saved = current_plan(db, pid, period_id)
        for slot in (saved.plan.get("slots", []) if saved else []):
            if slot.get("slot") == "club":
                counts[slot["drill"]] += 1
    return dict(counts)


def session_summary(db: DbSession, s: TrainingSession, labels: dict[str, str]) -> dict:
    rows = db.query(SessionAttendance).filter_by(session_id=s.id).all()
    return {"id": s.id, "period_id": s.period_id, "date": s.date.isoformat(), "start_time": s.start_time, "length": s.length_minutes,
            "title": s.title, "focus": [{"tag_id": t, "label": labels.get(t, t)} for t in s.focus_tags], "versions": s.versions,
            "expected": sum(r.expected for r in rows), "attended": sum(1 for r in rows if r.attended)}


def session_out(db: DbSession, s: TrainingSession) -> dict:
    labels = _tag_labels(db, s.focus_tags)
    names = {p.id: p.name for p in db.query(Player).filter_by(team_id=s.team_id)}
    attendance = db.query(SessionAttendance).filter_by(session_id=s.id).all()
    blocks = []
    for b in db.query(SessionBlock).filter_by(session_id=s.id).order_by(SessionBlock.position):
        drill = db.get(Drill, b.drill_id) if b.drill_id else None
        # In groups mode, a version per group; a block the squad runs together has one. A coach's own block has none.
        together = s.versions == "groups" and not b.group_variations
        if s.versions == "groups" and not together:
            variation_ids = [b.group_variations.get(str(i)) for i in range(len(s.groups))]
        else:
            variation_ids = [b.variation_id] if b.variation_id else []
        variations = {v.id: v for v in db.query(DrillVariation).filter(DrillVariation.id.in_([v for v in variation_ids if v] or [0]))}
        blocks.append({"id": b.id, "phase": b.phase, "minutes": b.minutes, "title": b.title, "notes": b.notes, "together": together,
                       "drill": {"slug": drill.slug, "title": drill.title} if drill else None, "chosen_by": b.chosen_by, "reasons": b.reasons,
                       "versions": [{"variation_id": vid, "kind": variations[vid].kind, "title": variations[vid].title,
                                     "levels": [variations[vid].level_min, variations[vid].level_max]} if vid in variations else None
                                    for vid in variation_ids]})
    return {**session_summary(db, s, labels), "notes": s.notes, "blocks": blocks,
            "groups": [{"name": g["name"], "players": [{"id": pid, "name": names.get(pid, "?")} for pid in g["player_ids"]]} for g in s.groups],
            "attendance": sorted(({"player_id": r.player_id, "name": names.get(r.player_id, "?"), "expected": r.expected, "attended": r.attended}
                                  for r in attendance), key=lambda r: r["name"].casefold()),
            "updated_at": s.updated_at}


@router.get("/teams/{team_id}/sessions")
def list_sessions(team_id: int, period_id: int | None = None, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The team's sessions, newest date first; only one period's when period_id is given."""
    require_member(team_id, db, user)
    query = db.query(TrainingSession).filter_by(team_id=team_id)
    if period_id is not None:
        query = query.filter_by(period_id=period_id)
    sessions = query.order_by(TrainingSession.date.desc(), TrainingSession.id.desc()).all()
    labels = _tag_labels(db, {t for s in sessions for t in s.focus_tags})
    return [session_summary(db, s, labels) for s in sessions]


@router.get("/teams/{team_id}/sessions/focus")
def suggested_focus(team_id: int, period_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The training focuses most players share in their current priorities, most players first."""
    require_member(team_id, db, user)
    period = scoped_period(db, team_id, period_id)
    insights = team_insights(db, team_id, period)
    tags = insights["tags"]
    return [{"tag_id": t["tag_id"], "label": tags.get(t["tag_id"], {}).get("label", t["tag_id"]), "players": len(t["players"])}
            for t in (insights["period"] or {}).get("priority_tags", [])[:5]]


@router.post("/teams/{team_id}/sessions", status_code=201)
def create_session(team_id: int, body: SessionIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Plan a session for the expected players and save it."""
    require_member(team_id, db, user)
    period = scoped_period(db, team_id, body.period_id)
    players = {p.id: p for p in db.query(Player).filter(Player.team_id == team_id, Player.id.in_(body.player_ids), Player.active.is_(True))}
    if len(players) != len(set(body.player_ids)):
        raise HTTPException(422, "Every expected player must be an active player in this team")
    labels = _tag_labels(db, body.focus_tags)
    if len(labels) != len(set(body.focus_tags)):
        raise HTTPException(422, "Unknown training focus")
    player_ids = sorted(players)
    if body.versions == "groups" and len(player_ids) < body.group_count:
        raise HTTPException(422, f"Splitting into {body.group_count} groups needs at least {body.group_count} players")

    levels = _levels(db, period, player_ids, body.focus_tags[0])
    group_ids = split_groups([(pid, levels[pid]) for pid in player_ids], body.group_count) if body.versions == "groups" else [player_ids]
    data = {"length": body.length, "focus": body.focus_tags,
            "groups": [{"levels": [levels[pid] for pid in ids]} for ids in group_ids],
            "drills": _drills_for_planner(db, _age_group(db, period.id, player_ids), user),
            "recent": _recent(db, team_id, body.date), "in_plans": _in_plans(db, period.id, player_ids)}
    result = plan_session(data)

    now = utcnow()
    title = body.title.strip() or " and ".join(labels[t] for t in body.focus_tags).capitalize()
    session = TrainingSession(team_id=team_id, period_id=period.id, date=body.date, start_time=body.start_time, length_minutes=body.length,
                              title=title[:120], focus_tags=body.focus_tags, versions=body.versions,
                              groups=[{"name": GROUP_NAMES[i], "player_ids": ids} for i, ids in enumerate(group_ids)] if body.versions == "groups" else [],
                              created_by=user.id, updated_by=user.id, created_at=now, updated_at=now)
    db.add(session)
    db.flush()
    slugs = {b["drill"] for b in result["blocks"] if b["drill"]}
    drill_ids = {d.slug: d.id for d in db.query(Drill).filter(Drill.slug.in_(slugs or ["_"]))}
    for position, b in enumerate(result["blocks"], start=1):
        db.add(SessionBlock(session_id=session.id, position=position, phase=b["phase"], minutes=b["minutes"],
                            drill_id=drill_ids.get(b["drill"]), title=b["title"], reasons=b["reasons"],
                            variation_id=b["variations"][0] if b["variations"] and (body.versions == "single" or b["together"]) else None,
                            group_variations={str(i): v for i, v in enumerate(b["variations"])} if body.versions == "groups" and not b["together"] else {}))
    db.add_all(SessionAttendance(session_id=session.id, player_id=pid, expected=True) for pid in player_ids)
    record(db, team_id, user, "session_created", date=body.date.isoformat(), title=session.title)
    db.commit()
    return session_out(db, session)


@router.get("/teams/{team_id}/sessions/{session_id}")
def get_session(team_id: int, session_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    return session_out(db, _session(db, team_id, session_id))


@router.patch("/teams/{team_id}/sessions/{session_id}")
def update_session(team_id: int, session_id: int, body: SessionPatch, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    session = _session(db, team_id, session_id)
    changes = body.model_dump(exclude_unset=True)
    if "date" in changes and changes["date"] is None:
        raise HTTPException(422, "A session needs a date")
    for key, value in changes.items():
        if key == "start_time":
            value = value or None
        elif isinstance(value, str):
            value = value.strip()
        setattr(session, key, value)
    session.updated_by, session.updated_at = user.id, utcnow()
    db.commit()
    return session_out(db, session)


@router.delete("/teams/{team_id}/sessions/{session_id}")
def delete_session(team_id: int, session_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    session = _session(db, team_id, session_id)
    record(db, team_id, user, "session_deleted", date=session.date.isoformat(), title=session.title)
    db.delete(session)
    db.commit()
    return {"message": "Session deleted."}

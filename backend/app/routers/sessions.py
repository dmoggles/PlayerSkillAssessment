"""Team training sessions: planned from the squad's shared priorities, then edited, printed and recorded."""
from collections import Counter
from datetime import date as date_type
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from ..audit import record
from ..auth import current_user, require_member
from ..cycles import current_plan
from ..database import get_db
from ..insights import player_tags, team_insights
from ..matrix import period_document, version_tags
from ..models import (Assessment, Drill, DrillVariation, Period, Player, PlayerGroup, SessionAttendance, SessionBlock, SessionTemplate,
                      SkillTag, TrainingSession, User, utcnow)
from ..sessions import (LENGTHS, PHASES, TOGETHER, balance_teams, block_groups, MAX_DRILL_GROUPS, drill_group_count, group_versions, plan as plan_session, ranked,
                        split_groups)
from .drills import _library
from .teams import scoped_period

router = APIRouter(tags=["sessions"])
GROUP_NAMES = ("Group A", "Group B", "Group C")
# An exercise's own level groups are numbered, so they aren't mistaken for the session's.
BLOCK_GROUP_NAMES = tuple(f"Group {i}" for i in range(1, 7))
TEAM_NAMES = ("Team 1", "Team 2")
RECENT_SESSIONS = 3


class SessionIn(BaseModel):
    period_id: int
    date: date_type
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    length: int | None = None  # 45, 60, 75 or 90: the default breakdown for that length; none with a template
    template_id: int | None = None
    focus_tags: list[str] = Field(min_length=1, max_length=3)
    player_ids: list[int] = Field(min_length=1, max_length=60)
    versions: Literal["single", "groups"] = "single"
    group_count: int = Field(default=2, ge=2, le=3)
    title: str = Field(default="", max_length=120)


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


def _drills_for_planner(db: DbSession, age_group: int | None, user: User, team_id: int) -> list[dict]:
    drills, drill_tags, ladder_tags, variations, votes, tags = _library(db, age_group, user, team_id)
    return [{"slug": d.slug, "title": d.title, "session_phase": d.session_phase,
             "players": [d.players_min, d.players_ideal, d.players_max], "duration": [d.duration_min, d.duration_typical],
             "tags": drill_tags.get(d.id, {}), "tag_labels": {t["id"]: t["label"] for t in tags.get(d.id, [])},
             "ladder_tags": sorted(ladder_tags.get(d.id, set())),
             "variations": [{"id": v.id, "kind": v.kind, "title": v.title, "levels": [v.level_min, v.level_max]} for v in variations.get(d.id, [])],
             "my_vote": votes[d.id]["mine"], "net_votes": votes[d.id]["likes"] - votes[d.id]["dislikes"], "team": d.team_id is not None}
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


def _planner_data(db: DbSession, team_id: int, period, focus: list[str], group_ids: list[list[int]], length: int, on: date_type,
                  user: User, exclude: int | None = None, minutes: dict | None = None) -> dict:
    """The planner's input for these players, split into these groups (one group in single mode)."""
    player_ids = [pid for ids in group_ids for pid in ids]
    levels = _levels(db, period, player_ids, focus[0])
    return {"length": length, "minutes": minutes, "focus": focus, "groups": [{"levels": [levels[pid] for pid in ids]} for ids in group_ids],
            "drills": _drills_for_planner(db, _age_group(db, period.id, player_ids), user, team_id),
            "recent": _recent(db, team_id, on, exclude), "in_plans": _in_plans(db, period.id, player_ids)}


def _expected_ids(db: DbSession, s: TrainingSession) -> list[int]:
    return sorted(r.player_id for r in db.query(SessionAttendance).filter_by(session_id=s.id, expected=True))


def _session_data(db: DbSession, s: TrainingSession, user: User) -> dict:
    """The planner's input for a saved session: its expected players, in its groups."""
    group_ids = [g["player_ids"] for g in s.groups] if s.versions == "groups" else [_expected_ids(db, s)]
    return _planner_data(db, s.team_id, db.get(Period, s.period_id), s.focus_tags, group_ids, s.length_minutes, s.date, user,
                         exclude=s.id, minutes=s.phase_minutes)


def _match_profiles(db: DbSession, s: TrainingSession, player_ids: list[int]) -> dict[int, dict]:
    """What the match teams are balanced on, per player: primary position and average coach score in the session's
    period, and age group. None where it isn't recorded."""
    assessments = {a.player_id: a for a in db.query(Assessment).filter(
        Assessment.period_id == s.period_id, Assessment.assessor == "coach", Assessment.player_id.in_(player_ids or [0]))}
    ages = {g.player_id: g.age_group for g in db.query(PlayerGroup).filter(PlayerGroup.period_id == s.period_id, PlayerGroup.player_id.in_(player_ids or [0]))}
    out = {}
    for pid in player_ids:
        a = assessments.get(pid)
        scores = [r.score for r in a.ratings if r.score is not None] if a else []
        out[pid] = {"id": pid, "position": a.primary_position if a and a.primary_position else None, "age": ages.get(pid),
                    "level": sum(scores) / len(scores) if scores else None}
    return out


def _positions(db: DbSession, s: TrainingSession) -> list[dict]:
    return period_document(db, db.get(Period, s.period_id))["positions"]


def _refresh_teams(db: DbSession, s: TrainingSession, rebalance: bool = False):
    """Balance the match teams from the expected players, keeping a coach's teams unless `rebalance`. No full squad
    game, or fewer than two players: no teams."""
    expected = _expected_ids(db, s)
    has_match = db.query(SessionBlock).filter_by(session_id=s.id, phase="full_squad_game").first() is not None
    if not has_match or len(expected) < 2:
        s.match_teams = None
        return
    if s.match_teams and s.match_teams.get("by") == "coach" and not rebalance:
        return
    order = [p["id"] for p in _positions(db, s)]
    s.match_teams = {"by": "planner", "player_ids": balance_teams(list(_match_profiles(db, s, expected).values()), order)}


def _match_teams_out(db: DbSession, s: TrainingSession, names: dict[int, str]) -> dict | None:
    """The two teams, each with its players and the averages it's balanced on."""
    if not s.match_teams:
        return None
    profiles = _match_profiles(db, s, [pid for team in s.match_teams["player_ids"] for pid in team])
    positions = _positions(db, s)
    labels = {p["id"]: p["label"] for p in positions}
    order = [p["id"] for p in positions]
    rank = lambda pos: order.index(pos) if pos in order else len(order)
    teams = []
    for name, team in zip(TEAM_NAMES, s.match_teams["player_ids"]):
        players = [profiles[pid] for pid in team]
        rated = [p["level"] for p in players if p["level"] is not None]
        aged = [p["age"] for p in players if p["age"] is not None]
        counts = Counter(p["position"] for p in players)
        teams.append({"name": name,
                      "players": sorted(({"id": p["id"], "name": names.get(p["id"], "?"), "position": p["position"],
                                          "position_label": labels.get(p["position"]), "age_group": p["age"]} for p in players),
                                        key=lambda p: (rank(p["position"]), p["name"].casefold())),
                      "positions": [{"position": pos, "label": labels.get(pos, pos) if pos else "Position not set", "count": counts[pos]}
                                    for pos in sorted(counts, key=rank)],
                      "average_level": round(sum(rated) / len(rated), 1) if rated else None,
                      "average_age_group": round(sum(aged) / len(aged), 1) if aged else None, "unrated": len(players) - len(rated)})
    return {"by": s.match_teams["by"], "teams": teams}


def _set_versions(block: SessionBlock, s: TrainingSession, variations: list[int], together: bool):
    """Store a block's versions: one for everyone, or one per group (the block's own groups, or the session's)."""
    if block.groups or (s.versions == "groups" and not together):
        block.variation_id, block.group_variations = None, {str(i): v for i, v in enumerate(variations)}
    else:
        block.variation_id, block.group_variations = (variations[0] if variations else None), {}


def _place_drill(db: DbSession, block: SessionBlock, s: TrainingSession, drill: dict | None, data: dict, title: str = ""):
    """Put a drill (planner format) in a block at each group's starting version, or make it the coach's own block.
    A block with its own groups splits them again for the new drill, whose player numbers may differ."""
    groups = block_groups(block.phase, data["groups"])
    together = s.versions == "groups" and len(groups) == 1
    if drill is None:
        block.drill_id, block.title, block.groups = None, title, None
        _set_versions(block, s, [], together)
        return
    block.drill_id, block.title = db.query(Drill.id).filter_by(slug=drill["slug"]).scalar(), drill["title"]
    if block.groups and _make_block_groups(db, s, block, drill, count=len(block.groups)):
        return
    block.groups = None
    _set_versions(block, s, group_versions(drill, data["focus"], groups), together)


def _make_block_groups(db: DbSession, s: TrainingSession, block: SessionBlock, drill: dict, groups: list[list[int]] | None = None,
                       count: int | None = None) -> bool:
    """Give a block its own level groups: these, or the expected players split by level on the session's first focus
    into `count` groups (the coach's choice), or as many as the drill's numbers suit. Each group starts at the version
    for its level. False, leaving the block as it was, when there aren't enough players for two groups."""
    period = db.get(Period, s.period_id)
    expected = _expected_ids(db, s)
    levels = _levels(db, period, expected, s.focus_tags[0])
    if groups is None:
        count = min(count, len(expected)) if count else drill_group_count(len(expected), drill["players"]) or min(2, len(expected))
        if count < 2:
            return False
        groups = split_groups([(pid, levels[pid]) for pid in expected], count)
    block.groups = groups
    _set_versions(block, s, group_versions(drill, s.focus_tags, [{"levels": [levels[pid] for pid in ids]} for ids in groups]), together=False)
    return True


def _renumber(db: DbSession, s: TrainingSession):
    """Keep blocks in phase order (warm-up first), and numbered 1, 2, 3..."""
    blocks = db.query(SessionBlock).filter_by(session_id=s.id).order_by(SessionBlock.position, SessionBlock.id).all()
    for position, b in enumerate(sorted(blocks, key=lambda b: PHASES.index(b.phase)), start=1):
        b.position = position


def _touch(s: TrainingSession, user: User):
    s.updated_by, s.updated_at = user.id, utcnow()


def session_summary(db: DbSession, s: TrainingSession, labels: dict[str, str]) -> dict:
    rows = db.query(SessionAttendance).filter_by(session_id=s.id).all()
    template = db.get(SessionTemplate, s.template_id) if s.template_id else None
    return {"id": s.id, "period_id": s.period_id, "date": s.date.isoformat(), "start_time": s.start_time, "length": s.length_minutes,
            "template": {"id": template.id, "name": template.name} if template else None, "title": s.title, "focus": [{"tag_id": t, "label": labels.get(t, t)} for t in s.focus_tags], "versions": s.versions,
            "expected": sum(r.expected for r in rows), "attended": sum(1 for r in rows if r.attended)}


def session_out(db: DbSession, s: TrainingSession) -> dict:
    labels = _tag_labels(db, s.focus_tags)
    names = {p.id: p.name for p in db.query(Player).filter_by(team_id=s.team_id)}
    attendance = db.query(SessionAttendance).filter_by(session_id=s.id).all()
    expected = sum(r.expected for r in attendance)
    blocks = []
    for b in db.query(SessionBlock).filter_by(session_id=s.id).order_by(SessionBlock.position):
        drill = db.get(Drill, b.drill_id) if b.drill_id else None
        # In groups mode, a version per group; a block the squad runs together has one. A coach's own block has none.
        # A block with its own groups has a version for each of them.
        together = s.versions == "groups" and not b.group_variations and not b.groups
        if b.groups:
            variation_ids = [b.group_variations.get(str(i)) for i in range(len(b.groups))]
        elif s.versions == "groups" and not together:
            variation_ids = [b.group_variations.get(str(i)) for i in range(len(s.groups))]
        else:
            variation_ids = [b.variation_id] if b.variation_id else []
        variations = {v.id: v for v in db.query(DrillVariation).filter(DrillVariation.id.in_([v for v in variation_ids if v] or [0]))}
        options = db.query(DrillVariation).filter_by(drill_id=drill.id).order_by(DrillVariation.position).all() if drill else []
        players = [drill.players_min, drill.players_ideal, drill.players_max] if drill else None
        blocks.append({"id": b.id, "phase": b.phase, "minutes": b.minutes, "title": b.title, "notes": b.notes, "together": together,
                       "groups": [{"name": BLOCK_GROUP_NAMES[i], "players": [{"id": pid, "name": names.get(pid, "?")} for pid in ids]}
                                  for i, ids in enumerate(b.groups)] if b.groups else None,
                       "drill_versions": [{"id": v.id, "kind": v.kind, "title": v.title, "levels": [v.level_min, v.level_max]} for v in options],
                       "drill": {"slug": drill.slug, "title": drill.title, "players": players} if drill else None, "chosen_by": b.chosen_by, "reasons": b.reasons,
                       # how many groups Make groups suggests: what the drill's player numbers suit
                       "suggested_groups": drill_group_count(expected, players) if drill else None,
                       "versions": [{"variation_id": vid, "kind": variations[vid].kind, "title": variations[vid].title,
                                     "levels": [variations[vid].level_min, variations[vid].level_max]} if vid in variations else None
                                    for vid in variation_ids]})
    return {**session_summary(db, s, labels), "notes": s.notes, "blocks": blocks,
            "groups": [{"name": g["name"], "players": [{"id": pid, "name": names.get(pid, "?")} for pid in g["player_ids"]]} for g in s.groups],
            "match_teams": _match_teams_out(db, s, names),
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


def default_title(blocks: list[dict], length: int, focus_labels: list[str]) -> str:
    """"Training match" when the full squad game is more than half the session; otherwise the focus, as "Passing and
    1v1 attacking"."""
    if sum(b["minutes"] for b in blocks if b["phase"] == "full_squad_game") * 2 > length:
        return "Training match"
    return " and ".join(focus_labels).capitalize()


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
    template = None
    if body.template_id is not None:
        template = db.query(SessionTemplate).filter_by(id=body.template_id, team_id=team_id).first()
        if not template:
            raise HTTPException(404, "Template not found")
        length, minutes = template.length_minutes, dict(template.minutes)
    elif body.length in LENGTHS:
        length, minutes = body.length, None
    else:
        raise HTTPException(422, f"Choose a template, or a length of {', '.join(map(str, LENGTHS))} minutes")
    if body.versions == "groups" and len(player_ids) < body.group_count:
        raise HTTPException(422, f"Splitting into {body.group_count} groups needs at least {body.group_count} players")

    levels = _levels(db, period, player_ids, body.focus_tags[0])
    group_ids = split_groups([(pid, levels[pid]) for pid in player_ids], body.group_count) if body.versions == "groups" else [player_ids]
    data = _planner_data(db, team_id, period, body.focus_tags, group_ids, length, body.date, user, minutes=minutes)
    result = plan_session(data)

    now = utcnow()
    title = body.title.strip() or default_title(result["blocks"], length, [labels[t] for t in body.focus_tags])
    session = TrainingSession(team_id=team_id, period_id=period.id, date=body.date, start_time=body.start_time, length_minutes=length,
                              template_id=template.id if template else None, phase_minutes=minutes,
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
    db.flush()
    _refresh_teams(db, session)
    record(db, team_id, user, "session_created", date=body.date.isoformat(), title=session.title)
    db.commit()
    return session_out(db, session)


@router.get("/teams/{team_id}/sessions/{session_id}")
def get_session(team_id: int, session_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    if s.match_teams is None:
        # Sessions planned before match teams existed get theirs on first opening.
        _refresh_teams(db, s)
        if s.match_teams:
            db.commit()
    return session_out(db, s)


@router.patch("/teams/{team_id}/sessions/{session_id}")
def update_session(team_id: int, session_id: int, body: SessionPatch, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    session = _session(db, team_id, session_id)
    changes = body.model_dump(exclude_unset=True)
    if "date" in changes and changes["date"] is None:
        raise HTTPException(422, "A session needs a date")
    if "title" in changes and not (changes["title"] or "").strip():
        raise HTTPException(422, "A session needs a name")
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


class BlockIn(BaseModel):
    phase: Literal[PHASES]
    minutes: int = Field(ge=1, le=120)
    drill: str | None = None  # a drill's slug; none for the coach's own activity
    title: str = Field(default="", max_length=160)


class BlockPatch(BaseModel):
    minutes: int | None = Field(default=None, ge=1, le=120)
    drill: str | None = None
    title: str | None = Field(default=None, max_length=160)
    versions: list[int] | None = Field(default=None, max_length=6)
    notes: str | None = Field(default=None, max_length=1000)


class GroupsIn(BaseModel):
    groups: list[list[int]] = Field(min_length=2, max_length=3)


def _block(db: DbSession, s: TrainingSession, block_id: int) -> SessionBlock:
    block = db.get(SessionBlock, block_id)
    if not block or block.session_id != s.id:
        raise HTTPException(404, "Block not found")
    return block


def _planner_drill(data: dict, slug: str) -> dict:
    drill = next((d for d in data["drills"] if d["slug"] == slug), None)
    if not drill:
        raise HTTPException(422, "That drill isn't in the library for this age group")
    return drill


@router.post("/teams/{team_id}/sessions/{session_id}/blocks", status_code=201)
def add_block(team_id: int, session_id: int, body: BlockIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Add a block to its part of the session, with a drill or the coach's own activity."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    if not body.drill and not body.title.strip():
        raise HTTPException(422, "Choose a drill, or describe the activity")
    data = _session_data(db, s, user)
    block = SessionBlock(session_id=s.id, position=10_000, phase=body.phase, minutes=body.minutes, chosen_by="coach", reasons=[])
    _place_drill(db, block, s, _planner_drill(data, body.drill) if body.drill else None, data, body.title.strip())
    db.add(block)
    db.flush()
    _renumber(db, s)
    _refresh_teams(db, s)
    _touch(s, user)
    db.commit()
    return session_out(db, s)


@router.put("/teams/{team_id}/sessions/{session_id}/blocks/{block_id}")
def change_block(team_id: int, session_id: int, block_id: int, body: BlockPatch, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Change a block: its minutes, drill (or the coach's own activity), versions, title or notes."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    block = _block(db, s, block_id)
    given = body.model_fields_set
    if "minutes" in given and body.minutes is not None:
        block.minutes = body.minutes
    if "drill" in given:
        data = _session_data(db, s, user)
        title = (body.title or "").strip() if body.drill is None else ""
        if body.drill is None and not title:
            raise HTTPException(422, "Describe the activity for a block without a drill")
        _place_drill(db, block, s, _planner_drill(data, body.drill) if body.drill else None, data, title)
    elif "title" in given and body.title is not None and block.drill_id is None:
        if not body.title.strip():
            raise HTTPException(422, "Describe the activity")
        block.title = body.title.strip()
    if "versions" in given and body.versions is not None:
        if block.drill_id is None:
            raise HTTPException(422, "A block without a drill has no versions")
        allowed = {v.id for v in db.query(DrillVariation).filter_by(drill_id=block.drill_id)}
        together = s.versions == "groups" and not block.group_variations and not block.groups
        wanted = len(block.groups) if block.groups else 1 if s.versions == "single" or together else len(s.groups)
        if len(body.versions) != wanted or not set(body.versions) <= allowed:
            raise HTTPException(422, f"Give {wanted} {'version' if wanted == 1 else 'versions'} of this block's drill")
        _set_versions(block, s, body.versions, together)
    if "notes" in given and body.notes is not None:
        block.notes = body.notes.strip()
    if given - {"notes"} and block.chosen_by != "coach":
        # Any change but a note makes the block the coach's: re-planning keeps it.
        block.chosen_by, block.reasons = "coach", ["Chosen by a coach."]
    _touch(s, user)
    db.commit()
    return session_out(db, s)


@router.delete("/teams/{team_id}/sessions/{session_id}/blocks/{block_id}")
def remove_block(team_id: int, session_id: int, block_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    db.delete(_block(db, s, block_id))
    db.flush()
    _renumber(db, s)
    _refresh_teams(db, s)
    _touch(s, user)
    db.commit()
    return session_out(db, s)


@router.get("/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/alternatives")
def block_alternatives(team_id: int, session_id: int, block_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Drills for this part of the session, best first, and every other drill in the library for this age group."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    block = _block(db, s, block_id)
    data = _session_data(db, s, user)
    candidates = ranked(block.phase, block.minutes, data)
    shown = {c["drill"]["slug"] for c in candidates}
    return {"ranked": [{"slug": c["drill"]["slug"], "title": c["drill"]["title"], "reasons": c["reasons"]} for c in candidates[:8]],
            "others": sorted(({"slug": d["slug"], "title": d["title"], "phase": d["session_phase"]} for d in data["drills"] if d["slug"] not in shown),
                             key=lambda d: d["title"])}


@router.put("/teams/{team_id}/sessions/{session_id}/groups")
def set_groups(team_id: int, session_id: int, body: GroupsIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Move players between level groups. Each block run in groups restarts at each group's level."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    if s.versions != "groups":
        raise HTTPException(409, "This session runs one version for everyone")
    flat = [pid for g in body.groups for pid in g]
    if sorted(flat) != _expected_ids(db, s):
        raise HTTPException(422, "Each expected player must be in exactly one group")
    s.groups = [{"name": GROUP_NAMES[i], "player_ids": ids} for i, ids in enumerate(body.groups)]
    data = _session_data(db, s, user)
    by_slug = {d["slug"]: d for d in data["drills"]}
    for block in db.query(SessionBlock).filter_by(session_id=s.id):
        if block.drill_id and block.group_variations and not block.groups:
            drill = by_slug.get(db.get(Drill, block.drill_id).slug)
            if drill:
                _set_versions(block, s, group_versions(drill, data["focus"], data["groups"]), together=False)
    _touch(s, user)
    db.commit()
    return session_out(db, s)


@router.post("/teams/{team_id}/sessions/{session_id}/regenerate")
def regenerate_session(team_id: int, session_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Plan the session again, keeping every block a coach chose or added."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    if not _expected_ids(db, s):
        raise HTTPException(422, "No players are expected at this session")
    data = _session_data(db, s, user)
    blocks = db.query(SessionBlock).filter_by(session_id=s.id).all()
    kept = [b for b in blocks if b.chosen_by == "coach"]
    kept_phases = {b.phase for b in kept}
    data["drills"] = [d for d in data["drills"] if d["slug"] not in {db.get(Drill, b.drill_id).slug for b in kept if b.drill_id}]
    data["kept_phases"] = sorted(kept_phases)
    for b in blocks:
        if b.chosen_by != "coach":
            db.delete(b)
    for i, planned in enumerate(plan_session(data)["blocks"]):
        if planned["phase"] in kept_phases:
            continue
        block = SessionBlock(session_id=s.id, position=10_000 + i, phase=planned["phase"], minutes=planned["minutes"],
                             title=planned["title"], reasons=planned["reasons"], chosen_by="planner")
        block.drill_id = db.query(Drill.id).filter_by(slug=planned["drill"]).scalar() if planned["drill"] else None
        _set_versions(block, s, planned["variations"], planned["together"])
        db.add(block)
    db.flush()
    _renumber(db, s)
    _refresh_teams(db, s)
    _touch(s, user)
    db.commit()
    return session_out(db, s)


class AttendanceRow(BaseModel):
    player_id: int
    expected: bool | None = None
    attended: bool | None = None


class AttendanceIn(BaseModel):
    players: list[AttendanceRow] = Field(min_length=1, max_length=80)


@router.put("/teams/{team_id}/sessions/{session_id}/attendance")
def set_attendance(team_id: int, session_id: int, body: AttendanceIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Who is expected (before the session, for planning) and who came (afterwards). In groups mode, newly expected
    players join the smallest group and players no longer expected leave theirs; blocks run in groups then restart at
    each group's level."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    team_players = {p.id for p in db.query(Player).filter_by(team_id=team_id)}
    rows = {r.player_id: r for r in db.query(SessionAttendance).filter_by(session_id=s.id)}
    before = _expected_ids(db, s)
    for item in body.players:
        if item.player_id not in team_players:
            raise HTTPException(422, "Every player must be in this team")
        row = rows.get(item.player_id)
        if row is None:
            row = SessionAttendance(session_id=s.id, player_id=item.player_id, expected=False)
            db.add(row)
            rows[item.player_id] = row
        if "expected" in item.model_fields_set and item.expected is not None:
            row.expected = item.expected
        if "attended" in item.model_fields_set:
            row.attended = item.attended
    db.flush()
    after = _expected_ids(db, s)
    if s.versions == "groups" and after != before:
        gone, joining = set(before) - set(after), [pid for pid in after if pid not in before]
        groups = [[pid for pid in g["player_ids"] if pid not in gone] for g in s.groups]
        for pid in joining:
            min(groups, key=len).append(pid)
        s.groups = [{"name": GROUP_NAMES[i], "player_ids": ids} for i, ids in enumerate(groups)]
        data = _session_data(db, s, user)
        by_slug = {d["slug"]: d for d in data["drills"]}
        for block in db.query(SessionBlock).filter_by(session_id=s.id):
            if block.drill_id and block.group_variations and not block.groups and block.chosen_by != "coach":
                drill = by_slug.get(db.get(Drill, block.drill_id).slug)
                if drill:
                    _set_versions(block, s, group_versions(drill, data["focus"], data["groups"]), together=False)
    if after != before:
        _refresh_teams(db, s, rebalance=True)  # teams from the players now expected, even the coach's
        _remake_block_groups(db, s, user)
    _touch(s, user)
    db.commit()
    return session_out(db, s)


def _remake_block_groups(db: DbSession, s: TrainingSession, user: User):
    """Exercises with their own groups split the players now expected again; with too few for two groups, the
    exercise goes back to running like the rest of the session."""
    blocks = db.query(SessionBlock).filter(SessionBlock.session_id == s.id, SessionBlock.groups.isnot(None)).all()
    if not blocks:
        return
    data = _session_data(db, s, user)
    by_slug = {d["slug"]: d for d in data["drills"]}
    for block in blocks:
        drill = by_slug.get(db.get(Drill, block.drill_id).slug) if block.drill_id else None
        if not drill or not _make_block_groups(db, s, block, drill, count=len(block.groups)):
            block.groups = None
            if drill:
                _place_drill(db, block, s, drill, data)


class BlockGroupsIn(BaseModel):
    groups: list[list[int]] = Field(min_length=2, max_length=MAX_DRILL_GROUPS)


class MakeGroupsIn(BaseModel):
    count: int | None = Field(None, ge=2, le=MAX_DRILL_GROUPS)  # none: as many as the drill's numbers suit


def _block_drill(db: DbSession, s: TrainingSession, block: SessionBlock, user: User) -> tuple[dict, dict]:
    if not block.drill_id:
        raise HTTPException(422, "Choose a drill for this block first")
    if block.phase == "full_squad_game":
        raise HTTPException(422, "The full squad game is played in two teams")
    data = _session_data(db, s, user)
    return _planner_drill(data, db.get(Drill, block.drill_id).slug), data


@router.post("/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/groups")
def make_block_groups(team_id: int, session_id: int, block_id: int, body: MakeGroupsIn | None = None, db: DbSession = Depends(get_db),
                      user: User = Depends(current_user)):
    """Split the expected players into level groups for this exercise, each at its own version; again if it has them.
    The coach chooses how many, or it's as many as the drill's numbers suit."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    block = _block(db, s, block_id)
    drill, _ = _block_drill(db, s, block, user)
    if not _make_block_groups(db, s, block, drill, count=body.count if body else None):
        raise HTTPException(422, "At least two players must be expected to make groups")
    block.chosen_by, block.reasons = "coach", ["Chosen by a coach."]
    _touch(s, user)
    db.commit()
    return session_out(db, s)


@router.put("/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/groups")
def set_block_groups(team_id: int, session_id: int, block_id: int, body: BlockGroupsIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Move players between an exercise's groups. Each group restarts at the version for its level."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    block = _block(db, s, block_id)
    if not block.groups:
        raise HTTPException(409, "This exercise has no groups of its own")
    drill, _ = _block_drill(db, s, block, user)
    if sorted(pid for g in body.groups for pid in g) != _expected_ids(db, s) or not all(body.groups):
        raise HTTPException(422, "Each expected player must be in exactly one group, and no group can be empty")
    _make_block_groups(db, s, block, drill, body.groups)
    _touch(s, user)
    db.commit()
    return session_out(db, s)


@router.delete("/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/groups")
def remove_block_groups(team_id: int, session_id: int, block_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The exercise goes back to running like the rest of the session: everyone together, or in the session's groups."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    block = _block(db, s, block_id)
    if block.groups:
        block.groups = None
        data = _session_data(db, s, user)
        drill = next((d for d in data["drills"] if block.drill_id and d["slug"] == db.get(Drill, block.drill_id).slug), None)
        if drill:
            _place_drill(db, block, s, drill, data)
        else:  # no longer in the library for this age group: keep the first group's version
            first = block.group_variations.get("0")
            per_group = s.versions == "groups" and block.phase not in TOGETHER
            _set_versions(block, s, [first] * (len(s.groups) if per_group else 1) if first else [], together=not per_group)
        _touch(s, user)
        db.commit()
    return session_out(db, s)


class MatchTeamsIn(BaseModel):
    teams: list[list[int]] = Field(min_length=2, max_length=2)


@router.put("/teams/{team_id}/sessions/{session_id}/match-teams")
def set_match_teams(team_id: int, session_id: int, body: MatchTeamsIn, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """The coach's own teams for the full squad game, kept until the expected players change."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    if not s.match_teams:
        raise HTTPException(409, "This session has no full squad game, or not enough players for two teams")
    if sorted(pid for team in body.teams for pid in team) != _expected_ids(db, s):
        raise HTTPException(422, "Each expected player must be in exactly one team")
    s.match_teams = {"by": "coach", "player_ids": body.teams}
    _touch(s, user)
    db.commit()
    return session_out(db, s)


@router.post("/teams/{team_id}/sessions/{session_id}/match-teams/suggest")
def suggest_match_teams(team_id: int, session_id: int, db: DbSession = Depends(get_db), user: User = Depends(current_user)):
    """Balance the teams again from scratch, replacing a coach's changes."""
    require_member(team_id, db, user)
    s = _session(db, team_id, session_id)
    _refresh_teams(db, s, rebalance=True)
    if not s.match_teams:
        raise HTTPException(409, "This session has no full squad game, or not enough players for two teams")
    _touch(s, user)
    db.commit()
    return session_out(db, s)

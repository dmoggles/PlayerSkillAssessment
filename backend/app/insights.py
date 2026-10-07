"""Squad-level insights from coach ratings: trends across periods, common priorities, and position groups.

Each player counts once per period (squad averages are averages of player averages). Section averages use each
period's own matrix; tag levels go through each version's tag mapping, so they compare across matrix versions.
An optional position filter limits trends and priorities to players whose primary position in that period matches;
the position breakdown always covers the whole squad. An optional playing group limits everything, positions
included, to players in that group in each period: ratings in different groups are judged against different cohorts.
"""
from collections import defaultdict
from statistics import mean
from sqlalchemy.orm import Session as DbSession
from .matrix import document, skill_changes, version_skills, version_tags
from .models import Assessment, Period, Player, PlayerGroup, PriorityConfirmation, SkillTag

POSITION_ORDER = ["goalkeeper", "defender", "midfielder", "winger", "striker"]


def _round(value):
    return round(value, 2) if value is not None else None


def player_sections(doc: dict, assessment: Assessment) -> dict[str, float]:
    """A player's average coach score per section that applies to their position (goalkeeper or outfield)."""
    scores = {r.skill_id: r.score for r in assessment.ratings if r.score is not None}
    out = {}
    for section in doc["sections"]:
        applies = "goalkeeper" in section["applies_to"] if assessment.position == "goalkeeper" else any(p != "goalkeeper" for p in section["applies_to"])
        values = [scores[s["id"]] for s in section["skills"] if s["id"] in scores]
        if applies and values:
            out[section["id"]] = mean(values)
    return out


def player_tags(tags_by_skill: dict, assessment: Assessment) -> dict[str, float]:
    """A player's tag levels: weighted average of coach scores through the version's skill-to-tag mapping."""
    totals = defaultdict(lambda: [0.0, 0.0])
    for r in assessment.ratings:
        if r.score is None:
            continue
        for tag, weight in tags_by_skill.get(r.skill_id, {}).items():
            totals[tag][0] += r.score * weight
            totals[tag][1] += weight
    return {tag: s / w for tag, (s, w) in totals.items() if w}


def squad(rows: list[dict]) -> dict:
    """Average per key across players, plus how many players contributed."""
    values = defaultdict(list)
    for row in rows:
        for key, value in row.items():
            values[key].append(value)
    return {key: {"average": _round(mean(v)), "players": len(v)} for key, v in values.items()}


def team_insights(db: DbSession, team_id: int, period: Period | None, position: str | None = None, group: int | None = None) -> dict:
    periods = db.query(Period).filter_by(team_id=team_id).order_by(Period.created_at, Period.id).all()
    assessments = db.query(Assessment).join(Player, Player.id == Assessment.player_id).filter(
        Player.team_id == team_id, Assessment.assessor == "coach").all()
    if group is not None:
        in_group = {(g.player_id, g.period_id) for g in db.query(PlayerGroup).filter(
            PlayerGroup.period_id.in_([p.id for p in periods]), PlayerGroup.age_group == group)}
        assessments = [a for a in assessments if (a.player_id, a.period_id) in in_group]
    by_period, filtered = defaultdict(list), defaultdict(list)
    for a in assessments:
        by_period[a.period_id].append(a)
        if position is None or (a.primary_position or a.position) == position:
            filtered[a.period_id].append(a)

    trend, previous_version = [], None
    used_tags, labels = set(), {}
    for p in periods:
        rated = filtered.get(p.id, [])
        if not rated:
            continue
        doc, tags = document(db, p.matrix_version_id), version_tags(db, p.matrix_version_id)
        labels.update({s["id"]: s["label"] for s in doc["sections"]})
        sections = squad([player_sections(doc, a) for a in rated])
        tag_rows = squad([player_tags(tags, a) for a in rated])
        used_tags.update(tag_rows)
        changed = set()
        if previous_version and previous_version != p.matrix_version_id:
            sections_of = {k: v[1] for k, v in {**version_skills(db, previous_version), **version_skills(db, p.matrix_version_id)}.items()}
            changed = {sections_of[s] for s, kind in skill_changes(db, previous_version, p.matrix_version_id).items()
                       if kind in ("reworded", "added", "retired", "moved") and s in sections_of}
        trend.append({"period_id": p.id, "label": p.label, "players": len(rated), "matrix_version_id": p.matrix_version_id,
                      "sections": sections, "tags": tag_rows, "changed_sections": sorted(changed)})
        previous_version = p.matrix_version_id

    tag_info = {t.id: {"label": t.label, "area": t.area} for t in db.query(SkillTag).filter(SkillTag.id.in_(used_tags | {"_"}))}
    result = {"trend": trend, "section_labels": labels, "tags": tag_info, "period": None, "position": position, "group": group}
    if period is None:
        return result

    doc, tags = document(db, period.matrix_version_id), version_tags(db, period.matrix_version_id)
    skill_labels = {s["id"]: s["label"] for section in doc["sections"] for s in section["skills"]}
    players = {pl.id: pl.name for pl in db.query(Player).filter_by(team_id=team_id)}
    if group is not None:
        players = {a.player_id: players[a.player_id] for a in by_period.get(period.id, [])}
    if position:
        players = {a.player_id: players[a.player_id] for a in filtered.get(period.id, [])}
    by_skill, by_tag = defaultdict(list), defaultdict(dict)
    for row in db.query(PriorityConfirmation).filter(PriorityConfirmation.period_id == period.id,
                                                    PriorityConfirmation.player_id.in_(players)).order_by(PriorityConfirmation.rank):
        name = players[row.player_id]
        by_skill[row.skill_id].append({"player": name, "rank": row.rank})
        for tag, weight in tags.get(row.skill_id, {}).items():
            if weight == 1.0:  # Main tags only, so a priority counts once per training focus
                by_tag[tag].setdefault(name, row.rank)
    priorities = sorted(({"skill_id": s, "label": skill_labels.get(s, s), "players": v} for s, v in by_skill.items()),
                        key=lambda x: (-len(x["players"]), x["label"]))
    priority_tags = sorted(({"tag_id": t, "players": [{"player": n, "rank": r} for n, r in v.items()]} for t, v in by_tag.items()),
                           key=lambda x: (-len(x["players"]), x["tag_id"]))
    tag_info.update({t.id: {"label": t.label, "area": t.area} for t in db.query(SkillTag).filter(SkillTag.id.in_(set(by_tag) | {"_"}))})

    groups = defaultdict(list)
    for a in by_period.get(period.id, []):
        groups[a.primary_position or a.position].append(a)
    positions = [{"position": pos, "players": len(groups[pos]),
                  "sections": squad([player_sections(doc, a) for a in groups[pos]]),
                  "tags": squad([player_tags(tags, a) for a in groups[pos]])}
                 for pos in POSITION_ORDER if groups.get(pos)]
    result["period"] = {"period_id": period.id, "label": period.label, "assessed": len(filtered.get(period.id, [])),
                        "priority_players": len({p["player"] for item in priorities for p in item["players"]}),
                        "priorities": priorities, "priority_tags": priority_tags, "positions": positions}
    return result

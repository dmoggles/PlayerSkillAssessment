"""Skill matrices stored in the database: lookups, the skill sets used for validation, and tag levels."""
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession
from .models import MatrixSkillTag, MatrixVersion, Period, SkillMatrix, Team
from .wording import render_document

# Published versions never change, so their documents can be cached for the life of the process.
_documents: dict[int, dict] = {}


def document(db: DbSession, version_id: int) -> dict:
    if version_id not in _documents:
        version = db.get(MatrixVersion, version_id)
        if version is None:
            raise LookupError(f"Matrix version {version_id} not found")
        _documents[version_id] = version.document
    return _documents[version_id]


def rendered(db: DbSession, version_id: int, gender: str) -> dict:
    """The document with pronoun placeholders filled in for a team's player gender."""
    return render_document(document(db, version_id), gender)


def skill_set(doc: dict, kind: str) -> set[str]:
    """Skill ids rated for 'goalkeeper' or 'outfield' players in this matrix."""
    def applies(section):
        targets = section["applies_to"]
        return "goalkeeper" in targets if kind == "goalkeeper" else any(p != "goalkeeper" for p in targets)
    return {skill["id"] for section in doc["sections"] if applies(section) for skill in section["skills"]}


def position_ids(doc: dict) -> set[str]:
    return {p["id"] for p in doc["positions"]}


def period_document(db: DbSession, period: Period) -> dict:
    return document(db, period.matrix_version_id)


def latest_version(db: DbSession, matrix_id: int) -> MatrixVersion:
    return db.query(MatrixVersion).filter_by(matrix_id=matrix_id).order_by(MatrixVersion.version.desc()).first()


def starter_version(db: DbSession) -> MatrixVersion:
    starter = db.query(SkillMatrix).filter(SkillMatrix.team_id.is_(None)).order_by(SkillMatrix.id).first()
    return latest_version(db, starter.id)


def team_version(db: DbSession, team: Team) -> MatrixVersion:
    """The version new periods use: the latest of the team's own matrix, else the starter template."""
    own = db.query(SkillMatrix).filter_by(team_id=team.id).first()
    return latest_version(db, own.id) if own else starter_version(db)


def version_visible_to_team(db: DbSession, team_id: int, version_id: int) -> bool:
    row = db.query(SkillMatrix).join(MatrixVersion, MatrixVersion.matrix_id == SkillMatrix.id).filter(
        MatrixVersion.id == version_id).first()
    return row is not None and row.team_id in (None, team_id)


def version_label(db: DbSession, version_id: int) -> str:
    """Short name for a matrix version, e.g. "Starter v1" or "Falcons matrix v2"."""
    version = db.get(MatrixVersion, version_id)
    matrix = db.get(SkillMatrix, version.matrix_id)
    return f"{'Starter' if matrix.team_id is None else matrix.name} v{version.version}"


_version_tags: dict[int, dict[str, dict[str, float]]] = {}


def version_tags(db: DbSession, version_id: int) -> dict[str, dict[str, float]]:
    """Skill id -> {tag id: weight} for a published version (cached; versions never change)."""
    if version_id not in _version_tags:
        tags = {}
        for row in db.query(MatrixSkillTag).filter_by(matrix_version_id=version_id):
            tags.setdefault(row.skill_id, {})[row.tag_id] = row.weight
        _version_tags[version_id] = tags
    return _version_tags[version_id]


def version_skills(db: DbSession, version_id: int) -> dict[str, tuple[dict, str]]:
    return {skill["id"]: (skill, section["id"]) for section in document(db, version_id)["sections"] for skill in section["skills"]}


def skill_changes(db: DbSession, old_id: int, new_id: int) -> dict[str, str]:
    """How each skill changed between two versions, as far as comparing ratings is concerned:
    reworded (name or level descriptions), added, retired, moved (to another section) or retagged."""
    if old_id == new_id:
        return {}
    old, new = version_skills(db, old_id), version_skills(db, new_id)
    old_tags, new_tags = version_tags(db, old_id), version_tags(db, new_id)
    changes = {skill_id: "added" for skill_id in new if skill_id not in old}
    changes.update({skill_id: "retired" for skill_id in old if skill_id not in new})
    for skill_id in new.keys() & old.keys():
        (before, before_section), (after, after_section) = old[skill_id], new[skill_id]
        if before["label"] != after["label"] or before["descriptors"] != after["descriptors"]:
            changes[skill_id] = "reworded"
        elif before_section != after_section:
            changes[skill_id] = "moved"
        elif old_tags.get(skill_id, {}) != new_tags.get(skill_id, {}):
            changes[skill_id] = "retagged"
    return changes


def annotate_history(db: DbSession, rows: list[dict], version_ids: list[int]) -> list[dict]:
    """Add each period's matrix version, its skill names and sections, and the skills that changed
    since the previous row, so history views can flag comparisons that cross a matrix change."""
    previous = None
    for row, version_id in zip(rows, version_ids):
        skills = version_skills(db, version_id)
        retired_from = version_skills(db, previous) if previous else {}
        row["matrix_version_id"] = version_id
        row["skill_changes"] = skill_changes(db, previous, version_id) if previous else {}
        row["skill_labels"] = {**{k: v[0]["label"] for k, v in retired_from.items()}, **{k: v[0]["label"] for k, v in skills.items()}}
        row["skill_sections"] = {**{k: v[1] for k, v in retired_from.items()}, **{k: v[1] for k, v in skills.items()}}
        previous = version_id
    return rows


def tag_levels(db: DbSession, player_id: int, period_id: int) -> dict[str, float]:
    """A player's level on each skill tag in a period: coach scores weighted through that period's tag mapping."""
    rows = db.execute(text("""
        SELECT mst.tag_id, SUM(r.score * mst.weight) / SUM(mst.weight) AS level
        FROM assessments a
        JOIN periods p ON p.id = a.period_id
        JOIN ratings r ON r.assessment_id = a.id AND r.score IS NOT NULL
        JOIN matrix_skill_tags mst ON mst.matrix_version_id = p.matrix_version_id AND mst.skill_id = r.skill_id
        WHERE a.player_id = :player AND a.period_id = :period AND a.assessor = 'coach'
        GROUP BY mst.tag_id
    """), {"player": player_id, "period": period_id}).all()
    return {tag: round(float(level), 2) for tag, level in rows}

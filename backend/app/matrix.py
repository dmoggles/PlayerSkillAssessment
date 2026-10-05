"""Skill matrices stored in the database: lookups, the skill sets used for validation, and tag levels."""
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession
from .models import MatrixVersion, Period, SkillMatrix, Team
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

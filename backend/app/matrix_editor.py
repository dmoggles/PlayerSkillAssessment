"""Editing a team's skill matrix: draft checks, automatic skill ids, change classification and publishing.

A draft is the version document plus, on each skill, the tags it feeds ({"tag_id": weight}). Shape errors and
changes to fixed settings are rejected outright (DraftError). Anything that only blocks publishing comes back
as a problem, so incomplete drafts can still autosave.
"""
import copy
import re
from sqlalchemy.orm import Session as DbSession
from .matrix import document
from .models import MatrixSkillTag, MatrixVersion, SkillMatrix, SkillTag
from .wording import literal_pronouns

# Not editable: the scale, positions and everything the priority formula depends on.
FIXED_KEYS = ("positions", "position_weight_values", "secondary_position_blend", "dependency_bonus", "priority")
OUTFIELD = ["defender", "midfielder", "winger", "striker"]
GOALKEEPER = ["goalkeeper"]
LEVELS = ("1", "3", "5")
IMPORTANCE = {"HIGH", "MED", "LOW"}
TAG_WEIGHTS = {1.0, 0.5}
LIMITS = {"label": 80, "descriptor": 300, "sections": 12, "skills": 30}


class DraftError(ValueError):
    pass


def expect(condition, message):
    if not condition:
        raise DraftError(message)


def editable_document(db: DbSession, version_id: int) -> dict:
    """A published version as a draft: raw text (placeholders kept) with each skill's tags attached."""
    doc = copy.deepcopy(document(db, version_id))
    tags = {}
    for row in db.query(MatrixSkillTag).filter_by(matrix_version_id=version_id):
        tags.setdefault(row.skill_id, {})[row.tag_id] = row.weight
    for section in doc["sections"]:
        for skill in section["skills"]:
            skill["tags"] = tags.get(skill["id"], {})
    return doc


def skills_of(doc: dict) -> dict[str, tuple[dict, dict]]:
    return {skill["id"]: (skill, section) for section in doc["sections"] for skill in section["skills"] if skill.get("id")}


def reserved_ids(db: DbSession, team_id: int, base_doc: dict) -> set[str]:
    """Every skill and section id ever used by this team's matrix or the starter templates it was copied from.
    Retired ids are never reused."""
    versions = db.query(MatrixVersion).join(SkillMatrix, SkillMatrix.id == MatrixVersion.matrix_id).filter(
        (SkillMatrix.team_id == team_id) | SkillMatrix.team_id.is_(None))
    docs = [base_doc] + [v.document for v in versions]
    return {item["id"] for doc in docs for section in doc["sections"] for item in [section, *section["skills"]]}


def new_id(label: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:60] or "skill"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}_{n}", n + 1
    taken.add(candidate)
    return candidate


def normalise(draft: dict, base_doc: dict, reserved: set[str]) -> dict:
    """Check the draft's shape and fixed settings, give new sections and skills their permanent ids,
    and derive dependency-root flags from the dependency map."""
    expect(isinstance(draft, dict) and isinstance(draft.get("sections"), list), "The matrix must have a list of sections")
    for key in FIXED_KEYS:
        expect(draft.get(key) == base_doc.get(key), f"{key} cannot be changed")
    expect(draft.get("meta", {}).get("scale") == base_doc["meta"]["scale"], "The rating scale cannot be changed")
    expect(len(draft["sections"]) <= LIMITS["sections"], f"A matrix can have at most {LIMITS['sections']} sections")
    doc = copy.deepcopy(draft)
    doc["meta"] = {**base_doc["meta"], **{k: v for k, v in doc.get("meta", {}).items() if k in ("age_group", "format", "formation")}}
    base_sections = {s["id"]: s for s in base_doc["sections"]}
    taken = set(reserved) | {item.get("id") for s in doc["sections"] for item in [s, *s.get("skills", [])] if isinstance(item, dict) and item.get("id")}
    positions = [p["id"] for p in base_doc["positions"]]
    for section in doc["sections"]:
        expect(isinstance(section, dict) and isinstance(section.get("skills"), list), "Each section needs a list of skills")
        expect(isinstance(section.get("label"), str) and len(section["label"]) <= LIMITS["label"], "Section names are text of at most 80 characters")
        expect(section.get("applies_to") in (OUTFIELD, GOALKEEPER), "A section is either for outfield players or goalkeepers")
        if section.get("id") in base_sections:
            expect(section["applies_to"] == base_sections[section["id"]]["applies_to"], "An existing section cannot switch between outfield and goalkeepers")
        if not section.get("id"):
            section["id"] = new_id(section["label"] or "section", taken)
        expect(len(section["skills"]) <= LIMITS["skills"], f"A section can have at most {LIMITS['skills']} skills")
        for skill in section["skills"]:
            expect(isinstance(skill, dict) and isinstance(skill.get("label"), str) and len(skill["label"]) <= LIMITS["label"], "Skill names are text of at most 80 characters")
            descriptors = skill.get("descriptors")
            expect(isinstance(descriptors, dict) and set(descriptors) == set(LEVELS) and all(isinstance(v, str) and len(v) <= LIMITS["descriptor"] for v in descriptors.values()),
                   "Each skill has descriptions for levels 1, 3 and 5 of at most 300 characters")
            # Outfield skills need every position (a goalkeeper can be an outfield player's secondary position);
            # goalkeeper skills are only ever rated for goalkeepers.
            needed = set(positions) if section["applies_to"] == OUTFIELD else set(GOALKEEPER)
            weights = skill.get("position_weights")
            expect(isinstance(weights, dict) and set(weights) == needed and set(weights.values()) <= IMPORTANCE,
                   "Each skill needs High, Medium or Low importance for every position it is rated for")
            tags = skill.get("tags", {})
            expect(isinstance(tags, dict) and all(isinstance(t, str) and w in TAG_WEIGHTS for t, w in tags.items()), "Tag weights are Main (1.0) or Partial (0.5)")
            if not skill.get("id"):
                skill["id"] = new_id(skill["label"] or "skill", taken)
    ids = [item["id"] for s in doc["sections"] for item in [s, *s["skills"]]]
    expect(len(ids) == len(set(ids)), "Section and skill ids must be unique")
    dependency_map = doc.get("dependency_map") or {}
    expect(isinstance(dependency_map, dict) and all(isinstance(v, list) for v in dependency_map.values()), "Dependencies must map a skill to a list of skills")
    doc["dependency_map"] = {k: v for k, v in dependency_map.items() if v}
    for skill, _ in skills_of(doc).values():
        skill["is_dependency_root"] = skill["id"] in doc["dependency_map"]
    return doc


def problems(doc: dict, active_tags: set[str]) -> list[str]:
    """Everything that must be fixed before publishing."""
    found = []
    skills = skills_of(doc)
    for section in doc["sections"]:
        if not section["label"].strip():
            found.append("A section has no name")
        if not section["skills"]:
            found.append(f"Section \"{section['label']}\" has no skills")
    for skill, section in skills.values():
        name = skill["label"].strip() or "A skill"
        if not skill["label"].strip():
            found.append(f"A skill in \"{section['label']}\" has no name")
        if any(not skill["descriptors"][level].strip() for level in LEVELS):
            found.append(f"{name} needs descriptions for levels 1, 3 and 5")
        if not skill.get("tags"):
            found.append(f"{name} needs at least one skill tag")
        if not any(w == 1.0 for w in skill.get("tags", {}).values()) and skill.get("tags"):
            found.append(f"{name} needs one Main tag")
        for tag in skill.get("tags", {}):
            if tag not in active_tags:
                found.append(f"{name} uses an unknown or retired tag: {tag}")
    for root, targets in doc["dependency_map"].items():
        for skill_id in [root, *targets]:
            if skill_id not in skills:
                found.append(f"A dependency refers to a skill that is not in the matrix: {skill_id}")
        if root in targets:
            found.append(f"{skills[root][0]['label']} cannot depend on itself")
    return found


def warnings(doc: dict) -> list[str]:
    """Plain pronouns that would not follow the team's player setting."""
    found = []
    for skill, _ in skills_of(doc).values():
        for level in LEVELS:
            words = literal_pronouns(skill["descriptors"][level])
            if words:
                found.append(f"{skill['label']}, level {level}: use placeholders instead of \"{', '.join(dict.fromkeys(words))}\"")
    return found


def classify(base: dict, draft: dict) -> dict[str, list[str]]:
    """Group the draft's changes by their effect on comparing ratings across periods."""
    changes = {"addition": [], "wording": [], "suggestions": [], "breaking": [], "layout": []}
    old, new = skills_of(base), skills_of(draft)
    old_sections = {s["id"]: s for s in base["sections"]}
    for skill_id, (skill, section) in new.items():
        if skill_id not in old:
            changes["addition"].append(f"Added {skill['label']} to {section['label']}")
            continue
        before, before_section = old[skill_id]
        name = before["label"]
        if skill["label"] != before["label"]:
            changes["wording"].append(f"Renamed {name} to {skill['label']}")
        for level in LEVELS:
            if skill["descriptors"][level] != before["descriptors"][level]:
                changes["wording"].append(f"Changed the level {level} description of {skill['label']}")
        if skill["position_weights"] != before["position_weights"]:
            changes["suggestions"].append(f"Changed position importance of {skill['label']}")
        if sorted(draft["dependency_map"].get(skill_id, [])) != sorted(base.get("dependency_map", {}).get(skill_id, [])):
            changes["suggestions"].append(f"Changed what depends on {skill['label']}")
        if skill.get("tags", {}) != before.get("tags", {}):
            changes["breaking"].append(f"Changed the skill tags of {skill['label']}")
        if section["id"] != before_section["id"]:
            changes["breaking"].append(f"Moved {skill['label']} from {before_section['label']} to {section['label']}")
    for skill_id, (skill, section) in old.items():
        if skill_id not in new:
            changes["breaking"].append(f"Retired {skill['label']}")
    for section in draft["sections"]:
        if section["id"] not in old_sections:
            changes["addition"].append(f"Added section {section['label']}")
        elif section["label"] != old_sections[section["id"]]["label"]:
            changes["layout"].append(f"Renamed section {old_sections[section['id']]['label']} to {section['label']}")
    if reordered(base, draft):
        changes["layout"].append("Changed the order of sections or skills")
    return changes


def reordered(base: dict, draft: dict) -> bool:
    """Whether sections, or skills within a section, that exist in both appear in a different order."""
    def common(a, b):
        keep = {x["id"] for x in b}
        return [x["id"] for x in a if x["id"] in keep]
    if common(base["sections"], draft["sections"]) != common(draft["sections"], base["sections"]):
        return True
    draft_sections = {s["id"]: s for s in draft["sections"]}
    return any(common(s["skills"], draft_sections[s["id"]]["skills"]) != common(draft_sections[s["id"]]["skills"], s["skills"])
               for s in base["sections"] if s["id"] in draft_sections)


def active_tag_ids(db: DbSession) -> set[str]:
    return {t.id for t in db.query(SkillTag).filter_by(active=True)}

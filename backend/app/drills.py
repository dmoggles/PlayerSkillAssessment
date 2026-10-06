"""The shared drill library: checks for drill data and animated diagrams, and loading drills from data files.

Drills are content, not schema: app admins edit app/data/drills_vN.json and the loader syncs them on every deploy
(`python -m app.drills`). A file is applied all or nothing; drills are matched by slug; a drill that disappears
from the file it came from is retired, never deleted.
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy.orm import Session as DbSession
from .models import Drill, DrillLink, DrillMedia, DrillTag, DrillVariation, SkillTag, utcnow

DATA_DIR = Path(__file__).parent / "data"
FORMATS = {"individual", "small_group", "unit", "team"}
PHASES = {"warm_up", "technical", "opposed", "small_sided_game", "cool_down"}
INTENSITIES = {"low", "medium", "high"}
EQUIPMENT = {"cones", "balls", "bibs", "goals", "mini_goals", "mannequins", "hurdles", "ladders", "poles", "other"}
KIND_ORDER = {"regression": 0, "base": 1, "escalator": 2}
VIDEO_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com", "player.vimeo.com"}
OBJECT_TYPES = {"player", "cone", "ball", "mannequin"}
ACTIONS = {"pass", "run", "dribble", "shot", "move"}
MAX_STEPS, MAX_OBJECTS = 12, 30


class DrillError(ValueError):
    pass


def _is_point(value, pitch) -> bool:
    return (isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)
            and 0 <= value[0] <= pitch["width"] and 0 <= value[1] <= pitch["length"])


def diagram_problems(diagram) -> list[str]:
    """Everything wrong with an animated diagram, checked by replaying its steps."""
    if not isinstance(diagram, dict):
        return ["diagram must be an object"]
    pitch, objects, steps = diagram.get("pitch"), diagram.get("objects"), diagram.get("steps")
    if not (isinstance(pitch, dict) and all(isinstance(pitch.get(k), (int, float)) and pitch[k] > 0 for k in ("width", "length"))):
        return ["pitch needs a positive width and length in metres"]
    if not isinstance(objects, dict) or not 1 <= len(objects) <= MAX_OBJECTS:
        return [f"diagram needs 1 to {MAX_OBJECTS} objects"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        return [f"diagram needs 1 to {MAX_STEPS} steps"]
    problems = []
    goals = {}
    for goal in pitch.get("goals", []):
        if not (isinstance(goal, dict) and goal.get("id") and _is_point(goal.get("at"), pitch)):
            problems.append("each goal needs an id and a point on the pitch")
        else:
            goals[goal["id"]] = goal
    players, holder = set(), None
    for name, obj in objects.items():
        kind = obj.get("type") if isinstance(obj, dict) else None
        if kind not in OBJECT_TYPES:
            problems.append(f"{name}: unknown object type {kind!r}")
            continue
        if kind == "ball":
            if obj.get("with") is not None:
                holder = obj["with"]
            elif not _is_point(obj.get("at"), pitch):
                problems.append(f"{name}: a ball needs 'with' a player or 'at' a point")
            continue
        if not _is_point(obj.get("at"), pitch):
            problems.append(f"{name}: position must be on the pitch")
        if kind == "player":
            players.add(name)
            if obj.get("team") not in ("A", "B", "N"):
                problems.append(f"{name}: team must be A, B or N")
    if sum(1 for obj in objects.values() if isinstance(obj, dict) and obj.get("type") == "ball") > 1:
        problems.append("a diagram has at most one ball")
    if holder is not None and holder not in players:
        problems.append(f"ball: {holder} is not a player")
    for number, step in enumerate(steps, start=1):
        where = f"step {number}"
        if not isinstance(step, dict) or not isinstance(step.get("label"), str) or not isinstance(step.get("actions"), list) or not step["actions"]:
            problems.append(f"{where}: needs a label and at least one action")
            continue
        if "duration" in step and not (isinstance(step["duration"], (int, float)) and 0.3 <= step["duration"] <= 5):
            problems.append(f"{where}: duration must be 0.3 to 5 seconds")
        new_holder = holder
        for action in step["actions"]:
            if not (isinstance(action, dict) and len(action) == 1 and next(iter(action)) in ACTIONS):
                problems.append(f"{where}: unknown action {action!r}")
                continue
            kind, spec = next(iter(action.items()))
            if kind == "pass":
                if spec.get("from") != holder:
                    problems.append(f"{where}: {spec.get('from')} passes without the ball")
                if spec.get("to") not in players:
                    problems.append(f"{where}: pass to unknown player {spec.get('to')}")
                new_holder = spec.get("to")
            elif kind == "shot":
                if spec.get("who") != holder:
                    problems.append(f"{where}: {spec.get('who')} shoots without the ball")
                # A shot goes to a goal's centre, or to a point (a corner of the goal, a target).
                target = spec.get("to")
                if not (_is_point(target, pitch) or (isinstance(target, str) and target in goals)):
                    problems.append(f"{where}: shot at unknown goal {spec.get('to')}")
                new_holder = None
            else:
                who = spec.get("who")
                if kind in ("run", "dribble") and who not in players:
                    problems.append(f"{where}: {who} is not a player")
                if kind == "move" and (who not in objects or objects[who].get("type") == "ball"):
                    problems.append(f"{where}: cannot move {who}")
                if kind == "dribble" and who != holder:
                    problems.append(f"{where}: {who} dribbles without the ball")
                if not _is_point(spec.get("to"), pitch):
                    problems.append(f"{where}: {kind} target is off the pitch")
        holder = new_holder
    return problems


def drill_problems(raw: dict, active_tags: set[str]) -> list[str]:
    """Everything that stops a drill from being loaded."""
    p = []
    req = lambda key, kind: isinstance(raw.get(key), kind)
    if not (req("slug", str) and raw["slug"] and len(raw["slug"]) <= 80 and raw["slug"].replace("-", "").isalnum()):
        p.append("slug must be lowercase letters, digits and hyphens")
    if not (req("title", str) and 0 < len(raw["title"]) <= 120):
        p.append("title is required (at most 120 characters)")
    if raw.get("format") not in FORMATS:
        p.append(f"format must be one of {sorted(FORMATS)}")
    if raw.get("session_phase") not in PHASES:
        p.append(f"session_phase must be one of {sorted(PHASES)}")
    if raw.get("intensity") not in INTENSITIES:
        p.append(f"intensity must be one of {sorted(INTENSITIES)}")
    players, ages, duration = raw.get("players"), raw.get("ages"), raw.get("duration")
    if not (isinstance(players, list) and len(players) == 3 and 1 <= players[0] <= players[1] <= players[2]):
        p.append("players must be [min, ideal, max] with 1 <= min <= ideal <= max")
    if not (isinstance(ages, list) and len(ages) == 2 and 4 <= ages[0] <= ages[1] <= 23):
        p.append("ages must be [min, max] U-ages between 4 and 23")
    if not (isinstance(duration, list) and len(duration) == 2 and 1 <= duration[0] <= duration[1]):
        p.append("duration must be [min, typical] minutes")
    for item in raw.get("equipment", []):
        if item.get("item") not in EQUIPMENT:
            p.append(f"unknown equipment {item.get('item')!r}")
    tags = raw.get("tags") or {}
    if not tags or 1.0 not in tags.values():
        p.append("needs at least one Main (1.0) tag")
    for tag, weight in tags.items():
        if tag not in active_tags:
            p.append(f"unknown or retired tag {tag!r}")
        if weight not in (1.0, 0.5):
            p.append(f"tag {tag} weight must be 1.0 or 0.5")
    # Optional: the tags whose progress the variation ladder describes (default: all of them).
    ladder = raw.get("ladder_tags")
    if ladder is not None and not (isinstance(ladder, list) and ladder and set(ladder) <= set(tags)):
        p.append("ladder_tags must be a non-empty list of this drill's tags")
    variations = raw.get("variations") or []
    kinds = [v.get("kind") for v in variations]
    if kinds.count("base") != 1:
        p.append("needs exactly one base variation")
    if any(k not in KIND_ORDER for k in kinds) or [KIND_ORDER.get(k, 0) for k in kinds] != sorted(KIND_ORDER.get(k, 0) for k in kinds):
        p.append("variations run regression, base, escalator in that order")
    previous = None
    media = raw.get("media") or []
    for v in variations:
        name = f"variation {v.get('title')!r}"
        if "players" in v and not (isinstance(v["players"], list) and len(v["players"]) == 3 and 1 <= v["players"][0] <= v["players"][1] <= v["players"][2]):
            p.append(f"{name}: players must be [min, ideal, max]")
        if "space" in v and not (isinstance(v["space"], list) and len(v["space"]) == 2 and all(isinstance(x, (int, float)) and x > 0 for x in v["space"])):
            p.append(f"{name}: space must be [width, length] in metres")
        for key in ("instructions", "coaching_points"):
            if key in v and not (isinstance(v[key], list) and v[key] and all(isinstance(x, str) and x for x in v[key])):
                p.append(f"{name}: {key} must be a non-empty list of text")
        if "setup" in v and not (isinstance(v["setup"], str) and v["setup"]):
            p.append(f"{name}: setup must be text")
        for item in v.get("equipment", []):
            if item.get("item") not in EQUIPMENT:
                p.append(f"{name}: unknown equipment {item.get('item')!r}")
        levels = v.get("levels")
        if not (isinstance(levels, list) and len(levels) == 2 and 1 <= levels[0] <= levels[1] <= 5):
            p.append(f"variation {v.get('title')!r}: levels must be [min, max] within 1-5")
            continue
        if previous and not (previous[0] <= levels[0] <= previous[1]):
            p.append(f"variation {v.get('title')!r}: levels must continue from the previous variation without a gap")
        previous = levels
        if "diagram" in v and not (isinstance(v["diagram"], int) and 0 <= v["diagram"] < len(media) and media[v["diagram"]].get("kind") == "diagram"):
            p.append(f"variation {v.get('title')!r}: diagram must point at one of this drill's diagrams")
        if "video" in v and not (isinstance(v["video"], int) and 0 <= v["video"] < len(media) and media[v["video"]].get("kind") == "video"):
            p.append(f"variation {v.get('title')!r}: video must point at one of this drill's videos")
    for i, m in enumerate(media):
        if m.get("kind") == "diagram":
            p += [f"diagram {i + 1}: {problem}" for problem in diagram_problems(m.get("diagram"))]
        elif m.get("kind") in ("video", "link"):
            parsed = urlparse(m.get("url") or "")
            if parsed.scheme != "https":
                p.append(f"media {i + 1}: url must be https")
            elif m["kind"] == "video" and parsed.hostname not in VIDEO_HOSTS:
                p.append(f"media {i + 1}: videos must be YouTube or Vimeo")
        else:
            p.append(f"media {i + 1}: kind must be video, diagram or link")
    return p


def load_file(db: DbSession, path: Path) -> dict:
    """Apply one data file: insert or update its drills by slug and retire the ones it no longer lists."""
    data = json.loads(path.read_text())
    version, rows = data["source_version"], data["drills"]
    active = {t.id for t in db.query(SkillTag).filter_by(active=True)}
    slugs = [r.get("slug") for r in rows]
    problems = [f"{r.get('slug')}: {problem}" for r in rows for problem in drill_problems(r, active)]
    problems += [f"duplicate slug {s}" for s in {s for s in slugs if slugs.count(s) > 1}]
    for r in rows:
        problems += [f"{r['slug']}: link to unknown drill {link.get('to')}" for link in r.get("links", [])
                     if link.get("to") not in slugs and not db.query(Drill).filter_by(slug=link.get("to")).first()]
    if problems:
        raise DrillError(f"{path.name}:\n  " + "\n  ".join(problems))
    counts = {"added": 0, "updated": 0, "retired": 0}
    by_slug = {}
    for r in rows:
        drill = db.query(Drill).filter_by(slug=r["slug"]).first()
        counts["updated" if drill else "added"] += 1
        if not drill:
            drill = Drill(slug=r["slug"], created_at=utcnow())
            db.add(drill)
        (drill.players_min, drill.players_ideal, drill.players_max), (drill.age_min, drill.age_max) = r["players"], r["ages"]
        drill.duration_min, drill.duration_typical = r["duration"]
        drill.space_width_m, drill.space_length_m = r.get("space") or (None, None)
        for key in ("title", "format", "session_phase", "intensity"):
            setattr(drill, key, r[key])
        drill.summary, drill.setup = r.get("summary", ""), r.get("setup", "")
        drill.equipment, drill.instructions, drill.coaching_points = r.get("equipment", []), r.get("instructions", []), r.get("coaching_points", [])
        drill.home_friendly, drill.status = r.get("home_friendly", False), r.get("status", "published")
        drill.source_version, drill.updated_at = version, utcnow()
        db.flush()
        for model in (DrillVariation, DrillMedia, DrillTag):
            db.query(model).filter_by(drill_id=drill.id).delete()
        db.query(DrillLink).filter_by(from_drill_id=drill.id).delete()
        ladder = set(r.get("ladder_tags") or r["tags"])
        db.add_all(DrillTag(drill_id=drill.id, tag_id=tag, weight=weight, on_ladder=tag in ladder) for tag, weight in r["tags"].items())
        media = [DrillMedia(drill_id=drill.id, position=i + 1, kind=m["kind"], caption=m.get("caption", ""), url=m.get("url"),
                            video_start_seconds=m.get("start_seconds"), diagram=m.get("diagram")) for i, m in enumerate(r.get("media", []))]
        db.add_all(media)
        db.flush()
        db.add_all(DrillVariation(drill_id=drill.id, position=i + 1, kind=v["kind"], title=v["title"], change=v.get("change", ""),
                                  level_min=v["levels"][0], level_max=v["levels"][1],
                                  diagram_media_id=media[v["diagram"]].id if "diagram" in v else None,
                                  video_media_id=media[v["video"]].id if "video" in v else None,
                                  setup=v.get("setup"), equipment=v.get("equipment"), instructions=v.get("instructions"),
                                  coaching_points=v.get("coaching_points"),
                                  players_min=v["players"][0] if "players" in v else None,
                                  players_ideal=v["players"][1] if "players" in v else None,
                                  players_max=v["players"][2] if "players" in v else None,
                                  space_width_m=v["space"][0] if "space" in v else None,
                                  space_length_m=v["space"][1] if "space" in v else None)
                   for i, v in enumerate(r["variations"]))
        by_slug[r["slug"]] = (drill, r)
    db.flush()
    for drill, r in by_slug.values():
        for link in r.get("links", []):
            target = by_slug[link["to"]][0] if link["to"] in by_slug else db.query(Drill).filter_by(slug=link["to"]).first()
            db.add(DrillLink(from_drill_id=drill.id, to_drill_id=target.id, relation=link["relation"]))
    for drill in db.query(Drill).filter(Drill.source_version == version, Drill.slug.notin_(slugs), Drill.status != "retired"):
        drill.status = "retired"
        counts["retired"] += 1
    db.commit()
    return counts


def load_all(db: DbSession, paths: list[Path] | None = None) -> dict[str, dict]:
    return {path.name: load_file(db, path) for path in (paths or sorted(DATA_DIR.glob("drills_v*.json")))}


if __name__ == "__main__":
    from .database import SessionLocal
    with SessionLocal() as session:
        try:
            for name, counts in load_all(session, [Path(a) for a in sys.argv[1:]] or None).items():
                print(f"{name}: {counts['added']} added, {counts['updated']} updated, {counts['retired']} retired")
        except DrillError as error:
            print(f"Drill data rejected; nothing was changed.\n{error}", file=sys.stderr)
            sys.exit(1)

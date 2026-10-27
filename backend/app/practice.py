"""Practice scenarios: frozen game situations a player solves on a top-down pitch, such as where to stand when
defending off the ball. They're content, like drills: written in app/data/practice_scenarios.json, checked here,
and served as they are. Scoring happens in the app (src/practice/practiceModel.js); this module only checks that
every scenario is well formed, so a mistake fails the tests rather than a player's screen.

Coordinates are metres on the pitch of the scenario's format. x runs from our own goal line (0) up the pitch, y
across it, so our goal's centre is (0, width / 2) whatever the format. A scenario can be for any format and age
group, and any topic: a topic brings its own roles, concepts and diagnostic checks.
"""
import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "practice_scenarios.json"

# FA pitch sizes in metres for each format are in the data file, under "formats": the pitch, the goal's width, the
# penalty area (depth up the pitch, width across it) and the penalty spot's distance from the goal line. A scenario
# can override any of them in its own "pitch".
FORMAT_KEYS = {"length", "width", "goalWidth", "penaltyArea", "penaltySpot"}

# What each topic teaches: the roles a player takes, the concepts scenarios are tagged with, the checks that
# diagnose a position (src/practice/checks.js runs them), and the name of each stage.
TOPICS = {
    "defending_off_ball": {
        "label": "Off-ball defending",
        "roles": {"MARK", "PRESS", "COVER", "SCAN"},
        "concepts": {"GOAL_SIDE", "BALL_SIDE", "DISTANCE_TIGHT", "DISTANCE_DROP", "PRESS", "COVER", "SCAN_MARKER", "NEAREST_THREAT", "COMMUNICATE"},
        "checks": {"GOAL_SIDE", "BALL_SIDE", "DISTANCE_TIGHT", "DISTANCE_DROP", "BEHIND_PRESSER", "NEAREST_THREAT", "KEEP_IN_FRONT"},
        "stages": {1: "Goal-side basics", 2: "The ball moves", 3: "Press or cover", 4: "Two attackers", 5: "Just lost the ball"},
    },
}
# Checks that need the opponent the player is responsible for (the frame's `mark`), or a teammate pressing the ball.
NEEDS_MARK = {"GOAL_SIDE", "BALL_SIDE", "DISTANCE_TIGHT", "DISTANCE_DROP", "NEAREST_THREAT"}
NEEDS_PRESSER = {"BEHIND_PRESSER"}
# Thresholds a scenario may override, for bigger or smaller spaces than the defaults in src/practice/thresholds.js.
THRESHOLDS = {"goalSideAngle", "lineTolerance", "tightBallRange", "tightDistance", "dropBallRange", "dropDistance",
              "coverBackMin", "coverBackMax", "coverAngle", "keepInFrontReach"}
TASKS = {"position"}  # what the player does in a frame: drag their player into position
ACTIONS = {"PRESS", "COVER", "MARK"}  # a teammate's action, drawn as an arrow or a label
MAX_FRAMES, MAX_PLAYERS, MAX_ZONES = 6, 22, 4
PROMPT_LENGTH, MESSAGE_LENGTH = 120, 120


class ScenarioError(ValueError):
    pass


def pitch_for(scenario: dict, formats: dict) -> dict:
    """The scenario's pitch: its format's, with any of the scenario's own measurements."""
    base = formats.get(scenario.get("format")) or next(iter(formats.values()))
    own = scenario.get("pitch") or {}
    return {**base, **own, "penaltyArea": {**base["penaltyArea"], **(own.get("penaltyArea") or {})}}


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _on_pitch(x, y, pitch) -> bool:
    return _number(x) and _number(y) and 0 <= x <= pitch["length"] and 0 <= y <= pitch["width"]


def _zone_problems(zone, pitch, where: str) -> list[str]:
    if not isinstance(zone, dict) or not (_number(zone.get("points")) and 0 < zone["points"] <= 100):
        return [f"{where}: each zone needs points from 1 to 100"]
    if zone.get("type") == "ellipse":
        if not (_on_pitch(zone.get("cx"), zone.get("cy"), pitch) and _number(zone.get("rx")) and _number(zone.get("ry"))
                and zone["rx"] > 0 and zone["ry"] > 0):
            return [f"{where}: an ellipse needs a centre on the pitch and positive radii"]
        return []
    if zone.get("type") == "polygon":
        points = zone.get("corners")
        if not (isinstance(points, list) and len(points) >= 3 and all(isinstance(p, list) and len(p) == 2 and _on_pitch(*p, pitch) for p in points)):
            return [f"{where}: a polygon needs at least three corners, each on the pitch"]
        return []
    return [f"{where}: a zone is an ellipse or a polygon"]


def scenario_problems(scenario, formats: dict, tags: set[str] | None = None) -> list[str]:
    """Everything wrong with one scenario, in plain words. `tags`, when given, are the skill tags that exist."""
    if not isinstance(scenario, dict):
        return ["a scenario must be an object"]
    sid = scenario.get("id") or "?"
    problems = []
    say = problems.append
    topic = TOPICS.get(scenario.get("topic"))
    if not (isinstance(scenario.get("id"), str) and scenario["id"].replace("-", "").isalnum() and scenario["id"].islower()):
        say(f"{sid}: id must be lower-case letters, numbers and hyphens")
    if not topic:
        return problems + [f"{sid}: unknown topic {scenario.get('topic')!r}"]
    if not (isinstance(scenario.get("title"), str) and 3 <= len(scenario["title"]) <= 80):
        say(f"{sid}: title must be 3 to 80 characters")
    if scenario.get("stage") not in topic["stages"]:
        say(f"{sid}: stage must be one of {sorted(topic['stages'])}")
    if scenario.get("format") not in formats:
        say(f"{sid}: format must be one of {sorted(formats)}")
    ages = scenario.get("ages")
    if not (isinstance(ages, list) and len(ages) == 2 and all(isinstance(a, int) for a in ages) and 6 <= ages[0] <= ages[1] <= 23):
        say(f"{sid}: ages must be [youngest, oldest] age groups, from U6 to U23")
    if scenario.get("role") not in topic["roles"]:
        say(f"{sid}: role must be one of {sorted(topic['roles'])}")
    concepts = scenario.get("concepts")
    if not (isinstance(concepts, list) and concepts and set(concepts) <= topic["concepts"]):
        say(f"{sid}: concepts must be a non-empty list from {sorted(topic['concepts'])}")
    skills = scenario.get("skills", [])
    if not isinstance(skills, list) or (tags is not None and not set(skills) <= tags):
        say(f"{sid}: skills must be skill tag ids")
    unknown = set(scenario.get("thresholds") or {}) - THRESHOLDS
    if unknown or not all(_number(v) and v > 0 for v in (scenario.get("thresholds") or {}).values()):
        say(f"{sid}: thresholds must be positive numbers, from {sorted(THRESHOLDS)}")
    if scenario.get("lines") is not None and not isinstance(scenario["lines"], bool):
        say(f"{sid}: lines must be true or false")
    pitch = pitch_for(scenario, formats)
    view = scenario.get("view")
    if view is not None and not (isinstance(view, dict) and _number(view.get("depth")) and 10 <= view["depth"] <= pitch["length"]):
        say(f"{sid}: view.depth must be from 10 m to the pitch's length")
    controlled = scenario.get("controlled")
    frames = scenario.get("frames")
    if not (isinstance(frames, list) and 1 <= len(frames) <= MAX_FRAMES):
        return problems + [f"{sid}: a scenario needs 1 to {MAX_FRAMES} frames"]
    ids = [f.get("id") if isinstance(f, dict) else None for f in frames]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        say(f"{sid}: every frame needs its own id")
    for n, frame in enumerate(frames):
        if isinstance(frame, dict):
            problems.extend(_frame_problems(frame, f"{sid} {frame.get('id') or n + 1}", topic, pitch, controlled,
                                            ids[n + 1] if n + 1 < len(ids) else None))
    return problems


def _frame_problems(frame: dict, where: str, topic: dict, pitch: dict, controlled, following) -> list[str]:
    problems = []
    say = problems.append
    if frame.get("task", "position") not in TASKS:
        say(f"{where}: task must be one of {sorted(TASKS)}")
    if not (isinstance(frame.get("prompt"), str) and 3 <= len(frame["prompt"]) <= PROMPT_LENGTH):
        say(f"{where}: prompt must be 3 to {PROMPT_LENGTH} characters")
    people = {}
    for side in ("team", "opponents"):
        group = frame.get(side)
        if not isinstance(group, list) or (side == "team" and not group):
            say(f"{where}: {side} must be a list of players")
            continue
        for p in group:
            if not (isinstance(p, dict) and isinstance(p.get("id"), str) and _on_pitch(p.get("x"), p.get("y"), pitch)):
                say(f"{where}: each of {side} needs an id and a position on the pitch")
            elif p["id"] in people:
                say(f"{where}: {p['id']} appears twice")
            elif p.get("label") is not None and not (isinstance(p["label"], str) and 1 <= len(p["label"]) <= 3):
                say(f"{where}: {p['id']}'s label is a shirt number or up to three characters")
            else:
                people[p["id"]] = (side, p)
                if p.get("action") is not None and (side != "team" or p["action"] not in ACTIONS):
                    say(f"{where}: {p['id']}'s action must be one of {sorted(ACTIONS)}, for the team")
    if len(people) > MAX_PLAYERS:
        say(f"{where}: at most {MAX_PLAYERS} players")
    # A frame can hand the player a different teammate to play, such as each defender in turn.
    controlled = frame.get("controlled", controlled)
    if people.get(controlled, ("",))[0] != "team":
        say(f"{where}: the controlled player {controlled!r} must be in the team")
    ball = frame.get("ball")
    if not (isinstance(ball, dict) and _on_pitch(ball.get("x"), ball.get("y"), pitch)):
        say(f"{where}: the ball needs a position on the pitch")
    elif ball.get("with") is not None:
        holder = people.get(ball["with"])
        if not holder or holder[1]["id"] == controlled:
            say(f"{where}: the ball is with a player in the frame, not the controlled player")
        elif ((holder[1]["x"] - ball["x"]) ** 2 + (holder[1]["y"] - ball["y"]) ** 2) ** 0.5 > 1.5:
            say(f"{where}: the ball must be at {ball['with']}'s feet")
    mark = frame.get("mark")
    if mark is not None and people.get(mark, ("",))[0] != "opponents":
        say(f"{where}: mark must be an opponent's id")
    # The player isn't shown which opponent is theirs: working it out is part of it. The lines to goal may start on.
    if frame.get("lines") is not None and not isinstance(frame["lines"], bool):
        say(f"{where}: lines must be true or false")
    target = frame.get("target")
    if not isinstance(target, dict):
        return problems + [f"{where}: a frame needs a target"]
    zones = target.get("zones")
    if not (isinstance(zones, list) and 1 <= len(zones) <= MAX_ZONES):
        say(f"{where}: a target needs 1 to {MAX_ZONES} zones")
    else:
        for zone in zones:
            problems.extend(_zone_problems(zone, pitch, where))
        points = [z.get("points") for z in zones if isinstance(z, dict)]
        if points and (max(points) != 100 or len(set(points)) != len(points)):
            say(f"{where}: one zone scores 100, and every zone scores differently")
    if not (isinstance(target.get("reasonCorrect"), str) and 3 <= len(target["reasonCorrect"]) <= MESSAGE_LENGTH):
        say(f"{where}: reasonCorrect must be 3 to {MESSAGE_LENGTH} characters")
    checks = target.get("checks", [])
    if not isinstance(checks, list):
        return problems + [f"{where}: checks must be a list"]
    for check in checks:
        cid = check.get("check") if isinstance(check, dict) else None
        if cid not in topic["checks"]:
            say(f"{where}: unknown check {cid!r}")
            continue
        clues = check.get("clues")
        if clues is not None and not (isinstance(clues, list) and 1 <= len(clues) <= 2 and all(isinstance(c, str) and 3 <= len(c) <= MESSAGE_LENGTH for c in clues)):
            say(f"{where}: {cid}'s clues must be one or two sentences of 3 to {MESSAGE_LENGTH} characters: a question first, then a pointer")
        if cid in NEEDS_MARK and mark is None:
            say(f"{where}: {cid} needs the frame's mark")
        if cid in NEEDS_PRESSER and not any(side == "team" and p.get("action") == "PRESS" for side, p in people.values()):
            say(f"{where}: {cid} needs a teammate pressing")
        threats = frame.get("threats")
        if cid == "KEEP_IN_FRONT" and not (isinstance(threats, list) and len(threats) >= 2 and all(people.get(t, ("",))[0] == "opponents" for t in threats)):
            say(f"{where}: KEEP_IN_FRONT needs the frame's threats: two or more opponents' ids")
    nxt = frame.get("next")
    if nxt is not None and (not isinstance(nxt, dict) or nxt.get("frame") != following):
        say(f"{where}: next must name the frame that follows it")
    if nxt is None and following is not None:
        say(f"{where}: frames play in order, so every frame but the last needs next")
    return problems


def file_problems(data, tags: set[str] | None = None) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get("scenarios"), list):
        return ["the file needs a list of scenarios"]
    formats = data.get("formats")
    if not (isinstance(formats, dict) and formats and all(isinstance(f, dict) and set(f) == FORMAT_KEYS and _number(f["length"]) and _number(f["width"])
                                                          and _number(f["goalWidth"]) for f in formats.values())):
        return [f"the file needs formats, each with {sorted(FORMAT_KEYS)}"]
    problems = [p for s in data["scenarios"] for p in scenario_problems(s, formats, tags)]
    ids = [s.get("id") for s in data["scenarios"] if isinstance(s, dict)]
    problems += [f"{i}: id used twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    return problems


@lru_cache
def scenarios() -> tuple[dict, ...]:
    """Every scenario, checked, each with its pitch filled in from its format. Raises on a bad file."""
    data = json.loads(DATA_FILE.read_text())
    problems = file_problems(data)
    if problems:
        raise ScenarioError("; ".join(problems))
    return tuple({**s, "pitch": pitch_for(s, data["formats"])} for s in data["scenarios"])


def by_id() -> dict[str, dict]:
    return {s["id"]: s for s in scenarios()}


def resolve(scenario_id: str) -> dict | None:
    """A scenario by its id: a hand-made one, or a generated one made again from its seed."""
    from . import practice_generator
    found = by_id().get(scenario_id)
    if found or not (parsed := practice_generator.parse_id(scenario_id)):
        return found
    return practice_generator.generate(*parsed)


def library() -> dict:
    """What the app needs to list and play scenarios: topics with their stages, and every scenario."""
    return {"topics": [{"id": tid, "label": t["label"], "stages": [{"stage": n, "label": label} for n, label in t["stages"].items()]}
                       for tid, t in TOPICS.items()],
            "scenarios": list(scenarios())}

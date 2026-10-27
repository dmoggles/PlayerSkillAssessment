"""Random practice situations, made from the stages as templates. Each is an ordinary scenario (the same format as
app/data/practice_scenarios.json), so scoring, clues, attempts and summaries work as for hand-made ones.

A situation is fixed by its seed: the same topic, stage, format and seed always make the same scenario, and its id
says all four (gen5-def-s2-9v9-48213), so the server can make it again to check an attempt. Change how situations
are made and the version goes up (gen2), so old attempts keep their meaning.

Best spots come from the coaching rules the checks test: goal-side on the attacker's line to goal, shifted towards
the ball, closer the nearer the ball is; or behind a pressing teammate, turned towards the next threat. Situations
that come out cramped or ambiguous are thrown away and the next one is tried, still from the same seed. The tests
check thousands of them against the app's own scoring (frontend/tests/fixtures/generated_scenarios.json).

    python -m app.practice_generator --samples   rewrite that fixture
    python -m app.practice_generator --sheet N    N situations per stage and format, as JSON, for a review sheet
"""
import json
import math
import random
import sys
from functools import lru_cache
from pathlib import Path
from . import practice

VERSION = "gen5"  # gen5: tight is about 3 m, not 2; gen2: covering in stage 4; gen3: every other attacker marked in stage 2; gen4: balanced cover in stage 3
TOPIC_CODES = {"def": "defending_off_ball"}
STAGES = {"defending_off_ball": (1, 2, 3, 4)}  # stage 5 is real games, written by hand
AGES = {"7v7": [9, 12], "9v9": [11, 13], "11v11": [12, 18]}
SPACING = 2.5  # metres between players, except a marker or presser and their attacker
TRIES = 60
FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "generated_scenarios.json"

# Distance classes, by how far the ball is from the attacker, kept clear of the checks' thresholds (8 m and 20 m):
# how far off them the best spot is, and the radii of the zones worth 100 and 60.
CLASSES = {
    "near": {"ball": (0, 6.5), "off": 3.0, "zones": (1.0, 2.2)},
    "mid": {"ball": (9.5, 18), "off": 4.5, "zones": (1.5, 3.0)},
    "far": {"ball": (21.5, 30), "off": 6.0, "zones": (1.8, 3.0)},
}
PROMPTS = {
    "near_carrier": ["An attacker has the ball near you. Where do you stand?", "They're on the ball and coming at you. Where do you stand?"],
    "near": ["The ball is close by. Where do you stand?", "A pass goes to an attacker nearby. Where do you stand?"],
    "mid": ["The ball is in midfield. Where do you stand?", "The ball is a little way off. Where do you stand?"],
    "far": ["The ball is far away. Where do you stand?", "The ball is on the other side. Where do you stand?"],
    "moved": ["The ball moves. Where now?", "A pass goes across. Where now?", "The ball is passed. Where do you go now?"],
    "cover": ["Your partner presses the ball. Where do you stand?", "A teammate goes to the ball. Where do you go?"],
    "nearest": ["You're the nearest to the ball. What do you do?", "The ball comes towards you. What do you do?"],
    "two": ["Two attackers are near you. Where do you stand?", "Who's the danger here? Where do you stand?"],
}
REASONS = {
    "near": "Close enough to stop them turning, not so close they can spin you.",
    "near_carrier": "Don't dive in: stay goal-side and make them go wide.",
    "mid": "Goal-side, a few steps off, and on the ball's side.",
    "far": "Dropped off and goal-side: you see the ball and the attacker.",
    "cover": "Behind your partner and goal-side of the free attacker: you cover both.",
    "nearest": "You're nearest, so you press: goal-side, without diving in.",
    "two": "The free attacker is nearer goal than the ball: they're the danger.",
    "two_cover": "The free attacker isn't ahead of the ball: cover your partner first.",
}


class Unfit(Exception):
    """This try made a situation that doesn't teach cleanly; try again from the seed."""


@lru_cache
def formats() -> dict:
    return json.loads(practice.DATA_FILE.read_text())["formats"]


# Geometry, in metres: x up the pitch from our goal line, y across it.

def _sub(a, b): return (a[0] - b[0], a[1] - b[1])
def _dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def _cross(a, b, p): return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _line_distance(a, b, p):
    return abs(_cross(a, b, p)) / _dist(a, b)


def goal_side_spot(attacker, ball, goal, off, shift):
    """`off` metres from the attacker towards the middle of the goal, then `shift` metres across towards the ball's
    side of that line, never more than a third of `off` (about 18 degrees, well inside the goal-side angle)."""
    length = _dist(attacker, goal)
    ux, uy = (goal[0] - attacker[0]) / length, (goal[1] - attacker[1]) / length
    base = (attacker[0] + ux * off, attacker[1] + uy * off)
    normal = (-uy, ux)
    if _cross(attacker, goal, (base[0] + normal[0], base[1] + normal[1])) * _cross(attacker, goal, ball) < 0:
        normal = (uy, -ux)
    shift = min(shift, off / 3)
    return (base[0] + normal[0] * shift, base[1] + normal[1] * shift)


def cover_spot(presser, threat, goal, back, turn):
    """`back` metres behind a pressing teammate on their line to goal, turned `turn` degrees towards the next threat."""
    angle = math.atan2(goal[1] - presser[1], goal[0] - presser[0])
    side = 1 if _cross(presser, goal, threat) > 0 else -1
    a = angle + side * math.radians(turn)
    return (presser[0] + back * math.cos(a), presser[1] + back * math.sin(a))


def _angle_at(at, a, b):
    """Degrees between the lines from `at` to `a` and from `at` to `b`."""
    u, v = _sub(a, at), _sub(b, at)
    lengths = math.hypot(*u) * math.hypot(*v)
    return math.degrees(math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / lengths)))) if lengths else 0


def keeps_in_front(p, attackers, goal, angle=29, reach=13.5):
    """Goal-side of every attacker, with room to spare under the check's 35 degrees, and near enough the nearest to
    step out (the check allows 15 m)."""
    return all(_dist(p, goal) < _dist(a, goal) - 1 and _angle_at(a, goal, p) <= angle for a in attackers) \
        and min(_dist(p, a) for a in attackers) <= reach


def balanced_cover(presser, carrier, threat, goal, depth):
    """Where to cover when a teammate presses and another attacker is free: as near as possible to halfway between
    a few metres behind the presser and a few metres goal-side of the free attacker, keeping both attackers (the
    ball carrier and the free one) in front of you. None if there's no such spot on the pitch shown."""
    behind = cover_spot(presser, threat, goal, 5.0, 15)
    goal_side = goal_side_spot(threat, carrier, goal, 4.0, 0)
    aim = ((behind[0] + goal_side[0]) / 2, (behind[1] + goal_side[1]) / 2)
    best = None
    for i in range(-24, 25):
        for j in range(-24, 25):
            p = (round(aim[0] + i * 0.25, 2), round(aim[1] + j * 0.25, 2))
            if 1 <= p[0] <= depth - 1 and keeps_in_front(p, (carrier, threat), goal) and (best is None or _dist(p, aim) < _dist(best, aim)):
                best = p
    return best


class Builder:
    """One try at a situation: the pitch, a seeded random source, and checks that throw Unfit."""

    def __init__(self, fmt: str, rng: random.Random):
        self.fmt, self.rng = fmt, rng
        self.pitch = formats()[fmt]
        self.length, self.width = self.pitch["length"], self.pitch["width"]
        self.depth = self.length / 2 + 5  # what the app shows by default
        self.goal = (0.0, self.width / 2)

    def on_view(self, p, margin=1.0):
        return margin <= p[0] <= self.depth - margin and margin <= p[1] <= self.width - margin

    def point(self, xs, ys):
        """A point at fractions of the shown depth (xs) and of the width (ys)."""
        return (round(self.rng.uniform(*xs) * self.depth, 1), round(self.rng.uniform(*ys) * self.width, 1))

    def around(self, centre, distance, towards_goal=None):
        """A point `distance` (a range) from `centre`, on the pitch shown; optionally kept up the pitch from it."""
        for _ in range(40):
            angle = self.rng.uniform(0, 2 * math.pi)
            d = self.rng.uniform(*distance)
            p = (round(centre[0] + d * math.cos(angle), 1), round(centre[1] + d * math.sin(angle), 1))
            if self.on_view(p) and (towards_goal is None or p[0] >= centre[0] - towards_goal):
                return p
        raise Unfit("no room")

    def goal_side(self, of, off):
        """A teammate `off` metres goal-side of an opponent, marking or pressing them."""
        length = _dist(of, self.goal)
        return (round(of[0] + (self.goal[0] - of[0]) * off / length, 1), round(of[1] + (self.goal[1] - of[1]) * off / length, 1))

    def start(self, ideal, avoid):
        """Where the player starts: in our half, well away from the best spot and clear of everyone."""
        for _ in range(60):
            p = self.point((0.12, 0.75), (0.1, 0.9))
            if _dist(p, ideal) >= 6 and all(_dist(p, q) >= SPACING for q in avoid):
                return p
        raise Unfit("no start")

    @staticmethod
    def spaced(people, pairs=()):
        """Everyone at least SPACING apart, except the given pairs (a marker and their attacker)."""
        close = {frozenset(pair) for pair in pairs}
        ids = list(people)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if frozenset((a, b)) not in close and _dist(people[a], people[b]) < SPACING:
                    raise Unfit("cramped")


def _ball_class(distance):
    return next((name for name, c in CLASSES.items() if c["ball"][0] <= distance <= c["ball"][1]), None)


def _mark_frame(b: Builder, mark, ball_at, holder, others, prompt=None, reason_key=None):
    """A marking frame: the best spot is goal-side of `mark`, by how far the ball is, shifted towards the ball.
    `others` are the other attackers, each with the teammate on them; `presser_of` is the attacker being pressed."""
    distance = _dist(ball_at, mark)
    kind = _ball_class(distance)
    if kind is None:
        raise Unfit("ball between classes")
    c = CLASSES[kind]
    # Tight, but not so tight they can spin you: and a touch deeper near goal, where being beaten means a shot.
    off = c["off"] + (0.5 if kind == "near" and _dist(mark, b.goal) < 20 and holder != "a1" else 0)
    line = _line_distance(mark, b.goal, ball_at)
    if 0.8 <= line <= 1.4:
        raise Unfit("ball too near the line to say which side")
    ball_side = line > 1.4
    ideal = goal_side_spot(mark, ball_at, b.goal, off, b.rng.uniform(0.6, 1.0) if ball_side else 0)
    ideal = (round(ideal[0], 2), round(ideal[1], 2))
    if not b.on_view(ideal):
        raise Unfit("best spot off the pitch shown")
    # Picking the right attacker must be clear: every other one is well further from the best spot.
    if any(_dist(ideal, o) < _dist(ideal, mark) + 2.0 for o, _ in others):
        raise Unfit("ambiguous mark")
    checks = ([{"check": "NEAREST_THREAT"}] if others else []) + [{"check": "GOAL_SIDE"}] + ([{"check": "BALL_SIDE"}] if ball_side else []) \
        + ([{"check": "DISTANCE_TIGHT"}] if kind == "near" else [{"check": "DISTANCE_DROP"}] if kind == "far" else [])
    key = reason_key or ("near_carrier" if holder == "a1" else kind)
    return ideal, kind, {
        "prompt": prompt or b.rng.choice(PROMPTS[key]), "mark": "a1",
        "target": {"zones": _zones(ideal, c["zones"]), "reasonCorrect": REASONS.get(key, REASONS[kind]), "checks": checks},
    }


def _zones(ideal, radii):
    return [{"type": "ellipse", "cx": ideal[0], "cy": ideal[1], "rx": r, "ry": r, "points": points} for r, points in zip(radii, (100, 60))]


def _player(pid, p, **extra):
    return {"id": pid, "x": round(p[0], 2), "y": round(p[1], 2), **extra}


def _stage_one(b: Builder):
    """Goal-side basics: one attacker to mark, the ball near, a little way off or far; any other attacker is marked."""
    a1 = b.point((0.3, 0.6), (0.2, 0.8))
    kind = b.rng.choice(list(CLASSES))
    with_a1 = kind == "near" and b.rng.random() < 0.4
    # The ball is never nearer our goal than the attacker to mark: one behind the ball is a job for covering (stage 4).
    holder_at = a1 if with_a1 else b.around(a1, CLASSES[kind]["ball"] if kind != "near" else (3.5, 6.5), towards_goal=0)
    opponents = {"a1": a1}
    team = {"gk": (1.5, b.width / 2)}
    pairs, others = [], []
    if not with_a1:
        opponents["a2"] = holder_at
        team["d1"] = b.goal_side(holder_at, 1.8)
        pairs.append(("a2", "d1"))
        others.append((holder_at, "d1"))
    if b.rng.random() < 0.6:
        a3 = b.around(a1, (8, 16), towards_goal=0)
        opponents["a3"], team["d2"] = a3, b.goal_side(a3, 1.5)
        pairs.append(("a3", "d2"))
        others.append((a3, "d2"))
    ideal, _, frame = _mark_frame(b, a1, holder_at, "a1" if with_a1 else "a2", others)
    team["you"] = b.start(ideal, list(opponents.values()) + list(team.values()))
    b.spaced({**opponents, **team}, pairs)
    holder = "a1" if with_a1 else "a2"
    return "MARK", _frame("f1", frame, opponents, team, holder, {"d1": "PRESS", "d2": "MARK"}), ideal


def _frame(fid, body, opponents, team, holder, actions):
    return {"id": fid, **body, "ball": {"x": round(opponents[holder][0], 2), "y": round(opponents[holder][1], 2), "with": holder},
            "opponents": [_player(k, v) for k, v in opponents.items()],
            "team": [_player(k, v, **({"action": actions[k]} if k in actions else {})) for k, v in team.items()]}


def _stage_two(b: Builder):
    """The ball moves: the same attacker to mark while the ball is passed between the others, so how close to be
    changes each time. A teammate presses whoever has the ball, and the others are marked, so the attacker to mark is
    always the only free one (a free attacker nearer the ball would be the danger instead)."""
    a1 = b.point((0.3, 0.55), (0.25, 0.75))
    near, far = b.around(a1, (4, 6.5), towards_goal=1), b.around(a1, (21.5, 28), towards_goal=0)
    mid = b.around(a1, (10, 17), towards_goal=0)
    order = b.rng.choice([("a2", "a3"), ("a3", "a2"), ("a4", "a2"), ("a2", "a4", "a3")])
    opponents = {"a1": a1, "a2": near, "a3": far, "a4": mid}
    frames, ideals = [], []
    start = None
    for n, holder in enumerate(order):
        others = [(opponents[k], None) for k in opponents if k != "a1"]
        ideal, _, body = _mark_frame(b, a1, opponents[holder], holder, others, prompt=None if n == 0 else b.rng.choice(PROMPTS["moved"]))
        team = {"gk": (1.5, b.width / 2), "d1": b.goal_side(opponents[holder], 1.8)}
        markers = {f"m{k[1:]}": b.goal_side(opponents[k], 1.5) for k in opponents if k not in ("a1", holder)}
        team.update(markers)
        if start is None:
            start = b.start(ideal, list(opponents.values()) + list(team.values()))
        team["you"] = start if n == 0 else ideals[-1]
        b.spaced({**opponents, **{k: v for k, v in team.items() if k != "you" or n == 0}}, [(holder, "d1"), *((f"a{m[1:]}", m) for m in markers)])
        if n and _dist(ideals[-1], ideal) < 2.2:
            raise Unfit("too little to change")
        frame = _frame(f"f{n + 1}", body, opponents, team, holder, {"d1": "PRESS", **{m: "MARK" for m in markers}})
        frames.append(frame)
        ideals.append(ideal)
    for this, following in zip(frames, frames[1:]):
        this["next"] = {"frame": following["id"]}
    return "MARK", frames, ideals[0]


def _stage_three(b: Builder):
    """Press or cover: a teammate presses the ball and you cover behind, towards the next threat; or you're the
    nearest, so you press."""
    carrier = b.point((0.45, 0.75), (0.2, 0.8))
    opponents = {"a1": carrier}
    if b.rng.random() < 0.65:
        # Cover: a teammate presses the carrier and another attacker is free. Cover both: deep enough to keep them in
        # front of you, near enough to step in if your partner is beaten.
        presser = b.goal_side(carrier, b.rng.uniform(1.6, 2.0))
        threat = b.around(carrier, (7, 12), towards_goal=4)
        if _line_distance(presser, b.goal, threat) < 2:
            raise Unfit("threat behind the presser")
        opponents["a2"] = threat
        ideal = balanced_cover(presser, carrier, threat, b.goal, b.depth)
        team = {"gk": (1.5, b.width / 2), "d1": presser}
        if ideal is None or not b.on_view(ideal) or min(_dist(ideal, q) for q in (threat, presser)) < SPACING:
            raise Unfit("no room to cover")
        team["you"] = b.start(ideal, list(opponents.values()) + list(team.values()))
        b.spaced({**opponents, **team}, [("a1", "d1")])
        body = {"prompt": b.rng.choice(PROMPTS["cover"]), "mark": "a2", "threats": ["a1", "a2"],
                "target": {"zones": _zones(ideal, (1.5, 3.0)), "reasonCorrect": REASONS["cover"], "checks": [{"check": "KEEP_IN_FRONT"}]}}
        return "COVER", _frame("f1", body, opponents, team, "a1", {"d1": "PRESS"}), ideal
    # You're nearest: your partner is marking someone further away.
    other = b.around(carrier, (13, 20), towards_goal=6)
    opponents["a2"] = other
    team = {"gk": (1.5, b.width / 2), "d1": b.goal_side(other, 1.5)}
    ideal = goal_side_spot(carrier, carrier, b.goal, 3.0, 0)
    ideal = (round(ideal[0], 2), round(ideal[1], 2))
    start = b.around(carrier, (7, 10), towards_goal=None)
    if _dist(start, carrier) >= _dist(team["d1"], carrier) - 3 or _dist(start, ideal) < 5:
        raise Unfit("not clearly nearest")
    team["you"] = start
    b.spaced({**opponents, **team}, [("a2", "d1")])
    body = {"prompt": b.rng.choice(PROMPTS["nearest"]), "mark": "a1",
            "target": {"zones": _zones(ideal, CLASSES["near"]["zones"]), "reasonCorrect": REASONS["nearest"],
                       "checks": [{"check": "GOAL_SIDE"}, {"check": "DISTANCE_TIGHT"}]}}
    return "PRESS", _frame("f1", body, opponents, team, "a1", {"d1": "MARK"}), ideal


def _stage_four(b: Builder):
    """Two attackers: one is marked by a teammate, the other is free. The ball is with a third, who is pressed. Who's
    the danger depends on where the free one is: nearer our goal than the ball, they are, so pick them up; level with
    the ball or further away, they aren't yet, so stay goal-side and cover the presser, turned towards them. You start
    between the two attackers, so you have to read it."""
    holder = b.point((0.5, 0.75), (0.2, 0.8))
    cover = b.rng.random() < 0.45
    for _ in range(40):
        free = b.around(holder, (9.5, 15))
        if (free[0] >= holder[0] - 1) if cover else (free[0] <= holder[0] - 3):
            break
    else:
        raise Unfit("no free attacker where wanted")
    marked = b.around(free, (8, 13), towards_goal=4)
    opponents = {"a1": free, "a2": marked, "a3": holder}
    presser = b.goal_side(holder, 1.8)
    team = {"gk": (1.5, b.width / 2), "d1": presser, "d2": b.goal_side(marked, 1.5)}
    if cover:
        ideal = cover_spot(presser, free, b.goal, b.rng.uniform(4.4, 5.0), b.rng.uniform(10, 20))
        ideal = (round(ideal[0], 2), round(ideal[1], 2))
        if not b.on_view(ideal) or min(_dist(ideal, p) for p in (*opponents.values(), team["d2"])) < SPACING:
            raise Unfit("no room to cover")
        body = {"prompt": b.rng.choice(PROMPTS["two"]), "mark": "a1",
                "target": {"zones": _zones(ideal, (1.5, 3.0)), "reasonCorrect": REASONS["two_cover"], "checks": [{"check": "BEHIND_PRESSER"}]}}
    else:
        ideal, _, body = _mark_frame(b, free, holder, "a3", [(marked, "d2"), (holder, "d1")], reason_key="two")
        body["prompt"] = b.rng.choice(PROMPTS["two"])
    # Start roughly as near the marked attacker as the free one, so reading the situation is the question.
    mid = ((free[0] + marked[0]) / 2 - 3, (free[1] + marked[1]) / 2)
    start = (round(mid[0] + b.rng.uniform(-1.5, 1.5), 1), round(mid[1] + b.rng.uniform(-1.5, 1.5), 1))
    if not b.on_view(start) or _dist(start, ideal) < 5:
        raise Unfit("no fair start")
    team["you"] = start
    b.spaced({**opponents, **team}, [("a2", "d2"), ("a3", "d1")])
    return ("COVER" if cover else "MARK"), _frame("f1", body, opponents, team, "a3", {"d1": "PRESS", "d2": "MARK"}), ideal


TEMPLATES = {("defending_off_ball", 1): _stage_one, ("defending_off_ball", 2): _stage_two,
             ("defending_off_ball", 3): _stage_three, ("defending_off_ball", 4): _stage_four}
CONCEPTS = {1: ["GOAL_SIDE", "BALL_SIDE", "DISTANCE_TIGHT", "DISTANCE_DROP"], 2: ["GOAL_SIDE", "BALL_SIDE", "DISTANCE_TIGHT", "DISTANCE_DROP"],
            3: ["PRESS", "COVER"], 4: ["NEAREST_THREAT", "COVER", "SCAN_MARKER"]}
SKILLS = {1: ["team_shape"], 2: ["team_shape"], 3: ["pressing", "team_shape"], 4: ["scanning", "team_shape"]}


def scenario_id(topic: str, stage: int, fmt: str, seed: int) -> str:
    code = next(c for c, t in TOPIC_CODES.items() if t == topic)
    return f"{VERSION}-{code}-s{stage}-{fmt}-{seed}"


def parse_id(sid: str):
    """(topic, stage, format, seed) for a generated scenario's id, or None."""
    parts = sid.split("-") if isinstance(sid, str) else []
    if len(parts) != 5 or parts[0] != VERSION or parts[1] not in TOPIC_CODES or not parts[2][1:].isdigit() or not parts[4].isdigit():
        return None
    topic, stage, fmt, seed = TOPIC_CODES[parts[1]], int(parts[2][1:]), parts[3], int(parts[4])
    return (topic, stage, fmt, seed) if (topic, stage) in TEMPLATES and fmt in formats() and seed < 10 ** 9 else None


@lru_cache(maxsize=512)
def generate(topic: str, stage: int, fmt: str, seed: int) -> dict:
    """The situation for this seed, as a scenario with its pitch. Raises KeyError for a stage with no template."""
    template = TEMPLATES[(topic, stage)]
    for attempt in range(TRIES):
        b = Builder(fmt, random.Random(seed * 1000 + attempt))
        try:
            role, frames, _ = template(b)
        except Unfit:
            continue
        frames = frames if isinstance(frames, list) else [frames]
        scenario = {"id": scenario_id(topic, stage, fmt, seed), "topic": topic, "stage": stage, "format": fmt, "ages": AGES[fmt],
                    "title": f"{practice.TOPICS[topic]['stages'][stage]}: a new situation", "role": role, "controlled": "you",
                    "concepts": CONCEPTS[stage], "skills": SKILLS[stage], "generated": True, "frames": frames}
        if practice.scenario_problems({k: v for k, v in scenario.items() if k != "generated"}, formats()):
            continue
        return {**scenario, "pitch": practice.pitch_for(scenario, formats())}
    raise RuntimeError(f"no situation for {topic} stage {stage} {fmt} seed {seed}")


def new_seed() -> int:
    return random.SystemRandom().randrange(1, 10 ** 9)


def samples(per: int) -> list[dict]:
    """`per` situations for every template and format, from fixed seeds."""
    return [generate(topic, stage, fmt, seed) for (topic, stage) in TEMPLATES for fmt in formats() for seed in range(1, per + 1)]


if __name__ == "__main__":
    if sys.argv[1:2] == ["--samples"]:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(samples(30), separators=(",", ":")) + "\n")
        print(f"wrote {FIXTURE}")
    elif sys.argv[1:2] == ["--sheet"]:
        print(json.dumps(samples(int(sys.argv[2]) if len(sys.argv) > 2 else 8)))
    else:
        sys.exit(__doc__)

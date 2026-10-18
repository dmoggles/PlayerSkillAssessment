"""Team training sessions: blocks of drills for a squad, built around a focus the coach confirms.

Like plans.py, the planner works on plain data, so it can be tested and replaced on its own.

Input:  {"length": 60,
         "focus": [tag_id, ...],                            # most important first
         "groups": [{"levels": [level or None per player]}], # one group in single mode, 2-3 in groups mode
         "drills": [{"slug", "title", "session_phase", "players": [min, ideal, max], "duration": [min, typical],
                     "tags": {tag_id: weight}, "ladder_tags": [tag_id],
                     "variations": [{"id", "kind", "title", "levels": [min, max]}],   # easiest first
                     "my_vote": -1/0/1, "net_votes": int}],
         "recent": {slug: sessions ago (1 = the team's last session)},
         "in_plans": {slug: players who have it at training in their plans}}
Output: {"planner": "sessions-v1",
         "blocks": [{"phase", "minutes", "drill": slug|None, "title", "together": bool,
                     "variations": [variation id per group, or one when together], "reasons": [text]}]}

Each block keeps to its session phase. A drill's score for a block, once hard filters pass (that phase, not
disliked by this coach, made for more than two players (drills for one or two are home practice), enough players
for each group and not more than two set-ups' worth, and not a goalkeeper drill unless the focus is a goalkeeping skill):
  focus      how strongly it trains the focus tags, the first tag counting most (warm-ups and cool-downs don't need to)
  time       how close its usual length is to the block's minutes
  preference this coach's like, other coaches' votes
  recency    drills from the team's last few sessions score lower, for variety
  plans      drills players already have at training in their own plans score a little higher
In groups mode the technical and opposed blocks run in the level groups; the warm-up, small-sided game and
cool-down run with everyone together. A drill is used once per session. Each group's version starts at the group's median level on the first focus
tag the drill's versions describe; otherwise at the base version. A phase with no fitting drill becomes the coach's
own block.
"""
from statistics import median
from .plans import start_index

PLANNER = "sessions-v1"
LENGTHS = (45, 60, 75, 90)
PHASES = ("warm_up", "technical", "opposed", "small_sided_game", "cool_down")
TEMPLATES = {
    45: {"warm_up": 8, "technical": 12, "opposed": 12, "small_sided_game": 10, "cool_down": 3},
    60: {"warm_up": 10, "technical": 15, "opposed": 15, "small_sided_game": 15, "cool_down": 5},
    75: {"warm_up": 10, "technical": 20, "opposed": 20, "small_sided_game": 20, "cool_down": 5},
    90: {"warm_up": 12, "technical": 20, "opposed": 25, "small_sided_game": 25, "cool_down": 8},
}
OWN_BLOCKS = {
    "warm_up": "Warm-up: jogging, mobility and short sprints, with a ball where you can",
    "technical": "Technical practice of your choice",
    "opposed": "Opposed practice of your choice",
    "small_sided_game": "Small-sided game",
    "cool_down": "Cool-down: a light jog and stretches",
}
TOGETHER = {"warm_up", "small_sided_game", "cool_down"}  # run with the whole squad, even in groups mode
FOCUS_WEIGHTS = (1.0, 0.6, 0.4)
RECENCY = {1: 4, 2: 2, 3: 1}


def focus_strength(focus: list[str], drill: dict) -> float:
    return sum(FOCUS_WEIGHTS[min(i, len(FOCUS_WEIGHTS) - 1)] * drill["tags"].get(tag, 0) for i, tag in enumerate(focus))


def setups(drill: dict, size: int) -> int | None:
    """How many set-ups of the drill a group of this size needs: 1, 2, or None if it can't run."""
    low, _, high = drill["players"]
    if size < low:
        return None
    if size <= high:
        return 1
    return 2 if size <= 2 * high else None


def block_groups(phase: str, groups: list[dict]) -> list[dict]:
    """Who runs a block: the level groups, or everyone together."""
    if phase in TOGETHER and len(groups) > 1:
        return [{"levels": [lv for g in groups for lv in g["levels"]]}]
    return groups


def assess(drill: dict, phase: str, minutes: int, data: dict) -> dict | None:
    """A candidate's score for this block with the notes that explain it, or None when it can't be used."""
    if drill["session_phase"] != phase or drill["my_vote"] < 0 or not drill["variations"]:
        return None
    # Drills for one or two players are home practice, not part of a team session, even for a small group.
    if drill["players"][2] <= 2:
        return None
    # Goalkeeper drills are for a goalkeeping focus, not a squad session's filler.
    if any(t.startswith("gk_") and w == 1.0 for t, w in drill["tags"].items()) and not any(t.startswith("gk_") for t in data["focus"]):
        return None
    counts = [setups(drill, len(g["levels"])) for g in block_groups(phase, data["groups"])]
    if any(c is None for c in counts):
        return None
    score, reasons = 0.0, []
    focus = focus_strength(data["focus"], drill)
    if focus:
        score += 4 * focus
        trained = [t for t in data["focus"] if drill["tags"].get(t)]
        reasons.append(f"Trains {', '.join(drill.get('tag_labels', {}).get(t, t) for t in trained)}.")
    elif phase not in ("warm_up", "cool_down"):
        reasons.append("Doesn't train the session's focus: the closest fit for this part of the session.")
    low, typical = drill["duration"]
    score -= abs(typical - minutes) / 5 + (2 if minutes < low else 0)
    if drill["my_vote"] > 0:
        score += 2
        reasons.append("You like this drill.")
    score += max(-1, min(1, drill["net_votes"] * 0.2))
    ago = data.get("recent", {}).get(drill["slug"])
    if ago:
        score -= RECENCY.get(ago, 0)
        reasons.append("Used in the last session." if ago == 1 else f"Used {ago} sessions ago.")
    in_plans = data.get("in_plans", {}).get(drill["slug"], 0)
    if in_plans:
        score += min(2, 0.5 * in_plans)
        reasons.append(f"{in_plans} {'player has' if in_plans == 1 else 'players have'} it in their plan.")
    if any(c == 2 for c in counts):
        reasons.append("Set up two of these side by side.")
    return {"drill": drill, "score": score, "reasons": reasons}


def ranked(phase: str, minutes: int, data: dict) -> list[dict]:
    """Candidates for a block, best first."""
    scored = [a for a in (assess(d, phase, minutes, data) for d in data["drills"]) if a]
    return sorted(scored, key=lambda a: (-a["score"], a["drill"]["title"]))


def group_versions(drill: dict, focus: list[str], groups: list[dict]) -> list[int]:
    """The starting version for each group: at the group's median level on the first focus tag the drill's
    versions describe, else the base version."""
    ladder = next((t for t in focus if t in drill["ladder_tags"]), None)
    out = []
    for group in groups:
        levels = [lv for lv in group["levels"] if lv is not None]
        level = round(median(levels)) if ladder and levels else None
        out.append(drill["variations"][start_index(drill["variations"], level)]["id"])
    return out


def build_block(phase: str, minutes: int, choice: dict | None, data: dict) -> dict:
    groups = block_groups(phase, data["groups"])
    together = len(data["groups"]) > 1 and len(groups) == 1
    if not choice:
        return {"phase": phase, "minutes": minutes, "drill": None, "title": OWN_BLOCKS[phase], "together": together, "variations": [],
                "reasons": ["No drill in the library fits this part of the session yet."]}
    drill = choice["drill"]
    return {"phase": phase, "minutes": minutes, "drill": drill["slug"], "title": drill["title"], "together": together,
            "variations": group_versions(drill, data["focus"], groups), "reasons": choice["reasons"]}


def plan(data: dict) -> dict:
    used, blocks = set(), []
    for phase, minutes in TEMPLATES[data["length"]].items():
        choice = next((c for c in ranked(phase, minutes, data) if c["drill"]["slug"] not in used), None)
        if choice:
            used.add(choice["drill"]["slug"])
        blocks.append(build_block(phase, minutes, choice, data))
    return {"planner": PLANNER, "blocks": blocks}


def split_groups(players: list[tuple[int, float | None]], count: int) -> list[list[int]]:
    """Players split into `count` groups of near-equal size by level, highest first. Unrated players go to the
    middle of the order, so they land in a middle group."""
    rated = sorted((p for p in players if p[1] is not None), key=lambda p: (-p[1], p[0]))
    unrated = [p for p in players if p[1] is None]
    middle = len(rated) // 2
    order = [pid for pid, _ in rated[:middle] + unrated + rated[middle:]]
    size, extra = divmod(len(order), count)
    groups, at = [], 0
    for i in range(count):
        n = size + (1 if i < extra else 0)
        groups.append(order[at:at + n])
        at += n
    return groups

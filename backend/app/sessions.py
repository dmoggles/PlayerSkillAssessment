"""Team training sessions: blocks of drills for a squad, built around a focus the coach confirms.

Like plans.py, the planner works on plain data, so it can be tested and replaced on its own.

Input:  {"length": 60,
         "minutes": {phase: minutes},                       # optional: a template's breakdown; else TEMPLATES[length]
         "focus": [tag_id, ...],                            # most important first
         "groups": [{"levels": [level or None per player]}], # one group in single mode, 2-3 in groups mode
         "drills": [{"slug", "title", "session_phase", "players": [min, ideal, max], "duration": [min, typical],
                     "tags": {tag_id: weight}, "ladder_tags": [tag_id],
                     "variations": [{"id", "kind", "title", "levels": [min, max]}],   # easiest first
                     "my_vote": -1/0/1, "net_votes": int, "team": bool}],  # team: the team's own drill
         "recent": {slug: sessions ago (1 = the team's last session)},
         "in_plans": {slug: players who have it at training in their plans}}
Output: {"planner": "sessions-v1",
         "blocks": [{"phase", "minutes", "drill": slug|None, "title", "together": bool,
                     "variations": [variation id per group, or one when together], "reasons": [text]}]}

The session has a block for each part in its breakdown, in PHASES order; a template may leave parts out. Each block
keeps to its session phase. A drill's score for a block, once hard filters pass (that phase, not
disliked by this coach, made for more than two players (drills for one or two are home practice), enough players
for each group and not more than two set-ups' worth, and not a goalkeeper drill unless the focus is a goalkeeping skill):
  focus      how strongly it trains the focus tags, the first tag counting most (warm-ups and cool-downs don't need to,
             and may have no tags at all)
  time       how close its usual length is to the block's minutes
  preference this coach's like, other coaches' votes
  recency    drills from the team's last few sessions score lower, for variety
  plans      drills players already have at training in their own plans score a little higher
In groups mode the technical and opposed blocks run in the level groups; the warm-up, games and cool-down run with
everyone together. A warm-up that needs longer than the breakdown allows (up to MAX_LONGER_WARM_UP more minutes, such
as a full injury-prevention programme) gets that time from the technical and opposed practices, as far as they have
it to give while keeping MIN_PRACTICE minutes each, so the session's length doesn't change. A drill is used once per session. Each group's version starts at the group's
median level on the first focus tag the drill's versions describe; otherwise at the base version. A phase with no
fitting drill becomes the coach's own block.
"""
from statistics import median
from .plans import start_index

PLANNER = "sessions-v1"
LENGTHS = (45, 60, 75, 90)
PHASES = ("warm_up", "technical", "opposed", "small_sided_game", "full_squad_game", "cool_down")
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
    "full_squad_game": "Full squad game: a match with everyone",
    "cool_down": "Cool-down: a light jog and stretches",
}
TOGETHER = {"warm_up", "small_sided_game", "full_squad_game", "cool_down"}  # run with the whole squad, even in groups mode
# A warm-up that needs longer than the template gives it (a full injury-prevention programme) may take up to this many
# minutes from the technical and opposed practices, so it is done properly.
MAX_LONGER_WARM_UP = 10
MIN_PRACTICE = 5  # a technical or opposed practice giving the warm-up time keeps at least this many minutes
GIVERS = ("technical", "opposed")  # the parts that give a longer warm-up its time
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


def assess(drill: dict, phase: str, minutes: int, data: dict, longer: int = 0) -> dict | None:
    """A candidate's score for this block with the notes that explain it, or None when it can't be used. A warm-up may
    run up to `longer` minutes past the block's minutes; the result's "minutes" says how long it takes."""
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
    elif not drill["tags"]:
        reasons.append(f"A general {'warm-up' if phase == 'warm_up' else 'cool-down'}, for any focus.")
    low, typical = drill["duration"]
    extended = longer and minutes < low <= minutes + longer
    if extended:
        minutes = low
        givers = data.get("givers", GIVERS)
        shorter = "technical and opposed practices are" if len(givers) > 1 else f"{givers[0]} practice is"
        reasons.append(f"Needs {low} minutes to be done properly, so the {shorter} a little shorter.")
    score -= abs(typical - minutes) / 5 + (2 if minutes < low else 0)
    if drill.get("team"):
        reasons.append("Your team's own drill.")
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
    return {"drill": drill, "score": score, "reasons": reasons, "minutes": minutes}


def ranked(phase: str, minutes: int, data: dict, longer: int = 0) -> list[dict]:
    """Candidates for a block, best first."""
    scored = [a for a in (assess(d, phase, minutes, data, longer) for d in data["drills"]) if a]
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


def breakdown(data: dict) -> dict[str, int]:
    """Minutes for each part the session has: the template's, or the default for its length."""
    minutes = data.get("minutes") or TEMPLATES[data["length"]]
    return {phase: minutes[phase] for phase in PHASES if minutes.get(phase)}


def take_minutes(minutes_for: dict[str, int], givers: list[str], extra: int):
    """Take `extra` minutes from the givers, as evenly as their spare time allows (the first gives the odd one)."""
    while extra > 0 and any(minutes_for[p] > MIN_PRACTICE for p in givers):
        for phase in givers:
            if extra and minutes_for[phase] > MIN_PRACTICE:
                minutes_for[phase] -= 1
                extra -= 1


def plan(data: dict) -> dict:
    """Blocks for every part of the session. `kept_phases` (when re-planning) are the parts a coach chose; the warm-up
    only takes time from the technical and opposed practices when the planner is choosing them all."""
    used, blocks = set(), []
    minutes_for = breakdown(data)
    givers = [p for p in GIVERS if p in minutes_for]
    can_lengthen = givers and not set(data.get("kept_phases", ())) & {"warm_up", *givers}
    spare = min(MAX_LONGER_WARM_UP, sum(minutes_for[p] - MIN_PRACTICE for p in givers)) if can_lengthen else 0
    data = {**data, "givers": givers}
    for phase in list(minutes_for):
        minutes = minutes_for[phase]
        longer = max(0, spare) if phase == "warm_up" else 0
        choice = next((c for c in ranked(phase, minutes, data, longer) if c["drill"]["slug"] not in used), None)
        if choice:
            used.add(choice["drill"]["slug"])
            extra = choice["minutes"] - minutes
            if extra > 0:
                take_minutes(minutes_for, givers, extra)
                minutes = choice["minutes"]
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


# Two teams for a full squad game. Balanced, in order of importance, on positions (goalkeepers most of all), age
# group and skill level. A position or age the coach hasn't recorded, or an unassessed player, counts as unknown:
# unknowns are shared out like any position, and left out of the averages.
POSITION_WEIGHTS = {"goalkeeper": 4.0}  # other positions 1 per player of imbalance
AGE_WEIGHT = 2.0  # per year of difference between the teams' average age groups
LEVEL_WEIGHT = 4.0  # per point of difference between average levels (1-5), so a quarter point costs as much as a position
UNRATED_WEIGHT = 0.5


def _imbalance(a: int, b: int) -> int:
    """How far two counts are from an even split; an odd total can't do better than one apart."""
    return abs(a - b) - (a + b) % 2


def _mean_gap(a: list[float], b: list[float]) -> float:
    return abs(sum(a) / len(a) - sum(b) / len(b)) if a and b else 0.0


def teams_cost(teams: list[list[dict]]) -> float:
    """How unbalanced two teams are; players are {"id", "position", "age", "level"}."""
    a, b = teams
    cost = 0.0
    for position in {p["position"] for p in a + b}:
        cost += POSITION_WEIGHTS.get(position, 1.0) * _imbalance(sum(p["position"] == position for p in a), sum(p["position"] == position for p in b))
    cost += AGE_WEIGHT * _mean_gap([p["age"] for p in a if p["age"] is not None], [p["age"] for p in b if p["age"] is not None])
    cost += LEVEL_WEIGHT * _mean_gap([p["level"] for p in a if p["level"] is not None], [p["level"] for p in b if p["level"] is not None])
    cost += UNRATED_WEIGHT * _imbalance(sum(p["level"] is None for p in a), sum(p["level"] is None for p in b))
    return cost


def balance_teams(players: list[dict], order: list[str]) -> list[list[int]]:
    """Two teams of near-equal size, as player ids. Players are dealt out by position (in `order`), strongest first,
    alternating ABBA, then pairs are swapped between the teams while that improves the balance."""
    rank = {p: i for i, p in enumerate(order)}
    dealt = sorted(players, key=lambda p: (rank.get(p["position"], len(order)), -(p["level"] if p["level"] is not None else 0), p["id"]))
    teams = [[], []]
    for i, p in enumerate(dealt):
        teams[0 if i % 4 in (0, 3) else 1].append(p)
    return [[p["id"] for p in team] for team in improve(teams)]


def improve(teams: list[list[dict]], rounds: int = 200) -> list[list[dict]]:
    """Make the best swap of one player each way, until no swap helps."""
    a, b = list(teams[0]), list(teams[1])
    best = teams_cost([a, b])
    for _ in range(rounds):
        swap = None
        for i in range(len(a)):
            for j in range(len(b)):
                a[i], b[j] = b[j], a[i]
                cost = teams_cost([a, b])
                a[i], b[j] = b[j], a[i]
                if cost < best - 1e-9:
                    best, swap = cost, (i, j)
        if not swap:
            break
        i, j = swap
        a[i], b[j] = b[j], a[i]
    return [a, b]


def add_to_teams(teams: list[list[dict]], joining: list[dict]) -> list[list[int]]:
    """Players joining teams the coach has set: each goes to the smaller team, or where they balance it best."""
    a, b = list(teams[0]), list(teams[1])
    for p in joining:
        if len(a) != len(b):
            (a if len(a) < len(b) else b).append(p)
        else:
            (a if teams_cost([a + [p], b]) <= teams_cost([a, b + [p]]) else b).append(p)
    return [[p["id"] for p in a], [p["id"] for p in b]]

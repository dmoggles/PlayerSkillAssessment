"""Development plans: a few weeks of club and home drills for a player's priorities.

The planner works on plain data only (the input and output below), so another planner, such as a decision
model ranking candidates, can be swapped in or compared on the same input. This is the rules-based planner.

Input:  {"weeks": 4,
         "priorities": [{"rank", "skill_id", "label", "level" (1-5 or None), "tags": {tag_id: weight}}],
         "drills": [{"slug", "title", "home_friendly", "duration": [min, typical], "tags": {tag_id: weight},
                     "tag_labels": {tag_id: label}, "ladder_tags": [tag_id],
                     "variations": [{"id", "kind", "title", "levels": [min, max]}],  # easiest first
                     "my_vote": -1/0/1, "net_votes": int}]}
Output: {"planner": "rules-v1", "weeks": n,
         "slots": [{"rank", "skill_id", "label", "slot": "club"|"home", "drill": slug, "title", "duration",
                    "weeks": [variation per week], "reasons": [text]}],
         "gaps": [{"rank", "skill_id", "label", "slot", "reason"}]}
"""

PLANNER = "rules-v1"
STEP_UP_WEEK = 3  # weeks before this use the starting version; from it on, the next one up


def start_index(variations: list[dict], level: int | None) -> int:
    """The hardest version whose level range includes the player's level; the base one when unrated."""
    if level is None:
        return next(i for i, v in enumerate(variations) if v["kind"] == "base")
    fitting = [i for i, v in enumerate(variations) if v["levels"][0] <= level <= v["levels"][1]]
    if fitting:
        return fitting[-1]
    return len(variations) - 1 if level > variations[-1]["levels"][1] else 0


def _candidates(priority: dict, drills: list[dict]) -> list[tuple[dict, float]]:
    """Drills that train this skill, best first: the coach's own like or dislike first, then match, then votes."""
    found = []
    for drill in drills:
        strength = sum(weight * drill["tags"].get(tag, 0) for tag, weight in priority["tags"].items())
        if strength and drill["my_vote"] != -1:
            found.append((drill, strength))
    return sorted(found, key=lambda m: (-m[0]["my_vote"], -m[1], -m[0]["net_votes"], m[0]["title"]))


def _pick(pool: list[tuple[dict, float]], taken: set[str]) -> tuple[dict, float, bool] | None:
    """The best drill nobody else has this slot; failing that the best one, shared."""
    for drill, strength in pool:
        if drill["slug"] not in taken:
            return drill, strength, False
    return (pool[0][0], pool[0][1], True) if pool else None


def _slot(priority: dict, slot: str, drill: dict, strength: float, shared: bool, weeks: int) -> dict:
    label, rank, level = priority["label"], priority["rank"], priority["level"]
    variations = drill["variations"]
    matched = [t for t in priority["tags"] if t in drill["tags"]]
    follows = bool(set(drill["ladder_tags"]) & set(matched))
    first = start_index(variations, level if follows else None)
    step_up = follows and first + 1 < len(variations)
    plan = [variations[first + 1] if step_up and week >= STEP_UP_WEEK else variations[first] for week in range(1, weeks + 1)]

    reasons = [f"{'Trains' if strength >= 1 else 'Partly trains'} {label} (priority {rank})."]
    if not follows:
        ladder = ", ".join(drill["tag_labels"][t] for t in drill["ladder_tags"])
        reasons.append(f"Base version throughout: this drill's versions follow {ladder}, not {label}.")
    elif level is None:
        reasons.append("Not rated, so it starts at the base version.")
    else:
        v = variations[first]
        reasons.append(f"Starts at “{v['title']}” (levels {v['levels'][0]}–{v['levels'][1]}) to match a rating of {level}.")
    if step_up:
        reasons.append(f"Steps up to “{variations[first + 1]['title']}” from week {STEP_UP_WEEK}.")
    elif follows:
        reasons.append("Already at the hardest version, so it stays there.")
    if shared:
        reasons.append("Also used for another priority: the library has no other drill for this yet.")
    return {"rank": rank, "skill_id": priority["skill_id"], "label": label, "slot": slot, "drill": drill["slug"],
            "title": drill["title"], "duration": drill["duration"], "weeks": plan, "reasons": reasons}


def plan(data: dict) -> dict:
    weeks = data.get("weeks", 4)
    slots, gaps = [], []
    taken = {"club": set(), "home": set()}
    for priority in sorted(data["priorities"], key=lambda p: p["rank"]):
        gap = lambda slot, reason: gaps.append({"rank": priority["rank"], "skill_id": priority["skill_id"],
                                                "label": priority["label"], "slot": slot, "reason": reason})
        if not priority["tags"]:
            gap("club", "This skill has no tags in the skill matrix, so no drills can be matched.")
            continue
        found = _candidates(priority, data["drills"])
        if not found:
            gap("club", "No drills for this skill in the library yet.")
            continue
        # At training, prefer drills made for the club; any drill can still fill the slot.
        club = _pick(sorted(found, key=lambda m: m[0]["home_friendly"]), taken["club"])
        slots.append(_slot(priority, "club", *club, weeks))
        taken["club"].add(club[0]["slug"])
        home_pool = [m for m in found if m[0]["home_friendly"] and m[0]["slug"] != club[0]["slug"]]
        home = _pick(home_pool, taken["home"])
        if home:
            slots.append(_slot(priority, "home", *home, weeks))
            taken["home"].add(home[0]["slug"])
        elif club[0]["home_friendly"]:
            # The training drill works at home too, and there is no other: practise it in both places.
            same = _slot(priority, "home", club[0], club[1], False, weeks)
            same["reasons"].append("Same drill as at training: there is no other home drill for this skill yet.")
            slots.append(same)
        else:
            gap("home", "No home drill for this skill yet.")
    return {"planner": PLANNER, "weeks": weeks, "slots": slots, "gaps": gaps}


def home_view(plan: dict) -> dict:
    """The plan as the player report shows it: home drills only. The saved plan keeps both sets; training drills are
    for the coach. A priority without a home drill says so."""
    home = [s for s in plan["slots"] if s["slot"] == "home"]
    covered = {s["rank"] for s in home}
    priorities = sorted({(i["rank"], i["skill_id"], i["label"]) for i in plan["slots"] + plan["gaps"]})
    gaps = [{"rank": rank, "skill_id": skill, "label": label, "slot": "home", "reason": "No home drill for this skill yet."}
            for rank, skill, label in priorities if rank not in covered]
    return {**plan, "slots": home, "gaps": gaps}

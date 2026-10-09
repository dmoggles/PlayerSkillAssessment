"""Development plans: a few weeks of club and home drills for a player's priorities.

The planner works on plain data only (the input and output below), so another planner, such as a decision
model ranking candidates, can be swapped in or compared on the same input. This is the rules-based planner.

Input:  {"weeks": 4,
         "priorities": [{"rank", "skill_id", "label", "level" (1-5 or None), "tags": {tag_id: weight}}],
         "drills": [{"slug", "title", "home_friendly", "duration": [min, typical], "tags": {tag_id: weight},
                     "tag_labels": {tag_id: label}, "ladder_tags": [tag_id],
                     "variations": [{"id", "kind", "title", "levels": [min, max]}],  # easiest first
                     "my_vote": -1/0/1, "net_votes": int}],      # candidates: the player's age group, published
         "catalog": {slug: drill},                                # optional: any drill a coach may pin
         "history": [{"drill", "skill_id", "slot", "cycles_ago": 1.., "last_index": int, "checkin": trend|None}],
         "squad": {skill_id: {slug: teammates using it at training}},
         "pins": [{"skill_id", "slot", "drill": slug|None (None = removed), "start_variation_id": int|None}]}
Output: {"planner": "rules-v2", "weeks": n,
         "slots": [{"rank", "skill_id", "label", "slot": "club"|"home", "drill": slug, "title", "duration",
                    "weeks": [variation per week], "reasons": [text], "chosen_by": "planner"|"coach",
                    "suggested": slug|None}],                   # the planner's pick, when the coach chose another
         "gaps": [{"rank", "skill_id", "label", "slot", "reason"}]}

How a drill is chosen for a slot, once hard filters have passed (trains the skill, right age group, not disliked
by this coach, home-friendly for the home slot):
  fit        how strongly it trains the skill, and whether its versions cover the player's level
  preference this coach's like (strong), other coaches' votes (light)
  recency    drills the player used recently score lower, fading with time: this is where variety comes from
  check-in   a drill whose last check-in for this skill was Better continues one version harder; if its hardest
             version is done, or the check-in was Same or Worse, another drill is tried
  squad      at training, a drill teammates already use for the same skill scores higher: one drill, one group
"""

PLANNER = "rules-v2"
STEP_UP_WEEK = 3  # weeks before this use the starting version; from it on, the next one up
RECENCY = {1: 6, 2: 4, 3: 3}  # score lost by a drill the player used this many cycles ago; older uses lose 2


def start_index(variations: list[dict], level: int | None) -> int:
    """The hardest version whose level range includes the player's level; the base one when unrated."""
    if level is None:
        return next(i for i, v in enumerate(variations) if v["kind"] == "base")
    fitting = [i for i, v in enumerate(variations) if v["levels"][0] <= level <= v["levels"][1]]
    if fitting:
        return fitting[-1]
    return len(variations) - 1 if level > variations[-1]["levels"][1] else 0


def strength(priority: dict, drill: dict) -> float:
    return sum(weight * drill["tags"].get(tag, 0) for tag, weight in priority["tags"].items())


def follows(priority: dict, drill: dict) -> bool:
    """Whether the drill's versions describe progress in this skill (a 1v1 attacking ladder does not, for defending)."""
    return bool(set(drill["ladder_tags"]) & {t for t in priority["tags"] if t in drill["tags"]})


def _last_use(history: list[dict], slug: str, skill_id: str | None = None, slot: str | None = None) -> dict | None:
    uses = [u for u in history if u["drill"] == slug and (skill_id is None or u["skill_id"] == skill_id) and (slot is None or u["slot"] == slot)]
    return min(uses, key=lambda u: u["cycles_ago"]) if uses else None


def assess(priority: dict, slot: str, drill: dict, data: dict) -> dict:
    """A candidate's score for this slot, with the notes that explain it."""
    history, notes = data.get("history", []), []
    s = strength(priority, drill)
    score = 10 * s + 3 * drill["my_vote"] + 0.2 * max(-5, min(5, drill["net_votes"]))
    if drill["my_vote"] == 1:
        notes.append("liked")
    if follows(priority, drill) and priority["level"] is not None:
        low, high = drill["variations"][0]["levels"][0], drill["variations"][-1]["levels"][1]
        score += 1 if low <= priority["level"] <= high else -1
    if slot == "club" and not drill["home_friendly"]:
        score += 4  # made for training with a group: outweighs a like, so a liked home drill stays at home
    used = _last_use(history, drill["slug"])
    continuation = None
    if used:
        score -= RECENCY.get(used["cycles_ago"], 2)
        same = _last_use(history, drill["slug"], priority["skill_id"], slot)
        top = len(drill["variations"]) - 1
        if same and same["checkin"] == "better" and same["last_index"] < top and follows(priority, drill):
            score += 12
            continuation = same["last_index"] + 1
            notes.append("last check-in Better: continue one version harder")
        elif same and same["checkin"] == "better":
            score -= 8
            notes.append("hardest version already done: try something new")
        elif same and same["checkin"] in ("same", "worse"):
            score -= 8
            notes.append(f"last check-in {same['checkin'].capitalize()}: try something else")
        else:
            notes.append("used last cycle" if used["cycles_ago"] == 1 else f"used {used['cycles_ago']} cycles ago")
    else:
        notes.append("new for this player")
    if slot == "club":
        mates = data.get("squad", {}).get(priority["skill_id"], {}).get(drill["slug"], 0)
        if mates:
            score += 2 * min(mates, 2)
            notes.append(f"{mates} {'teammate uses' if mates == 1 else 'teammates use'} it at training")
    return {"drill": drill, "strength": s, "score": round(score, 2), "notes": notes, "continue_from": continuation}


def ranked(priority: dict, slot: str, data: dict) -> list[dict]:
    """Candidates for one slot, best first. Hard filters: trains the skill, not disliked, home-friendly at home."""
    found = [assess(priority, slot, d, data) for d in data["drills"]
             if strength(priority, d) and d["my_vote"] != -1 and (slot == "club" or d["home_friendly"])]
    return sorted(found, key=lambda c: (-c["score"], c["drill"]["title"]))


def build_slot(priority: dict, slot: str, drill: dict, weeks: int, start: int | None = None, extra: list[str] = ()) -> dict:
    """A slot for this drill: versions week by week from the player's level (or a given start), and reasons."""
    label, rank, level = priority["label"], priority["rank"], priority["level"]
    variations = drill["variations"]
    on_ladder = follows(priority, drill)
    first = start if start is not None else start_index(variations, level if on_ladder else None)
    step_up = (on_ladder or start is not None) and first + 1 < len(variations)
    plan = [variations[first + 1] if step_up and week >= STEP_UP_WEEK else variations[first] for week in range(1, weeks + 1)]
    s = strength(priority, drill)
    reasons = [f"{'Trains' if s >= 1 else 'Partly trains' if s else 'Chosen for'} {label} (priority {rank})."]
    if start is not None:
        reasons.append(f"Starts at “{variations[first]['title']}”.")
    elif not on_ladder:
        ladder = ", ".join(drill["tag_labels"].get(t, t) for t in drill["ladder_tags"])
        reasons.append(f"Base version throughout: this drill's versions follow {ladder}, not {label}.")
    elif level is None:
        reasons.append("Not rated, so it starts at the base version.")
    else:
        v = variations[first]
        reasons.append(f"Starts at “{v['title']}” (levels {v['levels'][0]}–{v['levels'][1]}) to match a rating of {level}.")
    if step_up:
        reasons.append(f"Steps up to “{variations[first + 1]['title']}” from week {STEP_UP_WEEK}.")
    elif on_ladder:
        reasons.append("Already at the hardest version, so it stays there.")
    reasons.extend(extra)
    return {"rank": rank, "skill_id": priority["skill_id"], "label": label, "slot": slot, "drill": drill["slug"],
            "title": drill["title"], "duration": drill["duration"], "weeks": plan, "reasons": reasons,
            "chosen_by": "planner", "suggested": None}


def _choose(candidates: list[dict], taken: set[str]) -> tuple[dict | None, bool]:
    """The best candidate no other priority uses in this slot; failing that the best, shared."""
    for c in candidates:
        if c["drill"]["slug"] not in taken:
            return c, False
    return (candidates[0], True) if candidates else (None, False)


def _note_reasons(choice: dict, shared: bool) -> list[str]:
    reasons = [f"Why this drill: {', '.join(choice['notes'])}."] if choice["notes"] else []
    if shared:
        reasons.append("Also used for another priority: the library has no other drill for this yet.")
    return reasons


def plan(data: dict) -> dict:
    weeks = data.get("weeks", 4)
    catalog = {**{d["slug"]: d for d in data["drills"]}, **data.get("catalog", {})}
    pins = {(p["skill_id"], p["slot"]): p for p in data.get("pins", [])}
    slots, gaps = [], []
    taken = {"club": set(), "home": set()}
    for priority in sorted(data["priorities"], key=lambda p: p["rank"]):
        gap = lambda slot, reason: gaps.append({"rank": priority["rank"], "skill_id": priority["skill_id"],
                                                "label": priority["label"], "slot": slot, "reason": reason})
        club_drill, no_drills = None, False
        for slot in ("club", "home"):
            candidates = ranked(priority, slot, data) if priority["tags"] else []
            pick, shared = _choose([c for c in candidates if slot == "club" or c["drill"]["slug"] != club_drill], taken[slot])
            pin = pins.get((priority["skill_id"], slot))
            if pin and (pin["drill"] is None or pin["drill"] in catalog):
                suggested = pick["drill"]["slug"] if pick else None
                if pin["drill"] is None:
                    gap(slot, "Removed by the coach.")
                    continue
                drill = catalog[pin["drill"]]
                start = next((i for i, v in enumerate(drill["variations"]) if v["id"] == pin.get("start_variation_id")), None)
                extra = ["Chosen by the coach" + (f" (the planner suggested {catalog[suggested]['title']})." if suggested and suggested != drill["slug"] else ".")]
                chosen = build_slot(priority, slot, drill, weeks, start, extra)
                chosen.update(chosen_by="coach", suggested=suggested if suggested != drill["slug"] else None)
                slots.append(chosen)
                taken[slot].add(drill["slug"])
                club_drill = drill["slug"] if slot == "club" else club_drill
                continue
            if not priority["tags"]:
                if slot == "club":
                    gap("club", "This skill has no tags in the skill matrix, so no drills can be matched.")
                continue
            if pick:
                slots.append(build_slot(priority, slot, pick["drill"], weeks, pick["continue_from"], _note_reasons(pick, shared)))
                taken[slot].add(pick["drill"]["slug"])
                club_drill = pick["drill"]["slug"] if slot == "club" else club_drill
            elif slot == "home" and club_drill and catalog[club_drill]["home_friendly"]:
                # The training drill works at home too, and there is no other: practise it in both places.
                same = build_slot(priority, "home", catalog[club_drill], weeks)
                same["reasons"].append("Same drill as at training: there is no other home drill for this skill yet.")
                slots.append(same)
            elif slot == "club" and not candidates:
                gap("club", "No drills for this skill in the library yet.")
                no_drills = True
            elif no_drills:
                continue
            else:
                gap(slot, "No home drill for this skill yet." if slot == "home" else "No training drill for this skill yet.")
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

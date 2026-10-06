"""The rules-based development planner, on plain data (no database)."""
from app.plans import plan

LADDER = [{"id": 1, "kind": "regression", "title": "Easy", "levels": [1, 2]}, {"id": 2, "kind": "base", "title": "Base", "levels": [2, 3]},
          {"id": 3, "kind": "escalator", "title": "Hard", "levels": [3, 4]}, {"id": 4, "kind": "escalator", "title": "Hardest", "levels": [4, 5]}]


def drill(slug, tags, home=False, vote=0, net=0, ladder=None, labels=None):
    return {"slug": slug, "title": slug.title(), "home_friendly": home, "duration": [8, 10], "tags": tags,
            "tag_labels": labels or {t: t.title() for t in tags}, "ladder_tags": ladder if ladder is not None else list(tags),
            "variations": LADDER, "my_vote": vote, "net_votes": net}


def priority(rank, skill, tags, level=None):
    return {"rank": rank, "skill_id": skill, "label": skill.title(), "level": level, "tags": tags}


def titles(slot):
    return [v["title"] for v in slot["weeks"]]


def test_versions_start_at_the_players_level_and_step_up_in_week_3():
    out = plan({"priorities": [priority(1, "passing", {"passing": 1.0}, level=2)],
                "drills": [drill("rondo", {"passing": 1.0}), drill("wall", {"passing": 1.0}, home=True)]})
    club, home = out["slots"]
    assert (club["slot"], club["drill"], home["slot"], home["drill"]) == ("club", "rondo", "home", "wall")
    assert titles(club) == ["Base", "Base", "Hard", "Hard"]  # level 2 sits in two ranges: the harder one
    assert club["reasons"][1] == "Starts at “Base” (levels 2–3) to match a rating of 2." and "week 3" in club["reasons"][2]
    assert out["gaps"] == [] and out["planner"] == "rules-v1"
    top = plan({"priorities": [priority(1, "passing", {"passing": 1.0}, level=5)], "drills": [drill("rondo", {"passing": 1.0})]})
    assert titles(top["slots"][0]) == ["Hardest"] * 4 and "hardest version" in top["slots"][0]["reasons"][2]
    unrated = plan({"priorities": [priority(1, "passing", {"passing": 1.0})], "drills": [drill("rondo", {"passing": 1.0})]})
    assert titles(unrated["slots"][0]) == ["Base", "Base", "Hard", "Hard"]


def test_a_ladder_that_follows_another_skill_stays_at_the_base_version():
    one_v_one = drill("end-line", {"attacking": 1.0, "defending": 0.5}, ladder=["attacking"], labels={"attacking": "1v1 attacking", "defending": "1v1 defending"})
    out = plan({"priorities": [priority(1, "defending", {"defending": 1.0}, level=4)], "drills": [one_v_one]})
    slot = out["slots"][0]
    assert titles(slot) == ["Base"] * 4 and slot["reasons"][0] == "Partly trains Defending (priority 1)."
    assert slot["reasons"][1] == "Base version throughout: this drill's versions follow 1v1 attacking, not Defending."


def test_dislikes_are_left_out_likes_come_first_and_priorities_do_not_share_a_drill():
    drills = [drill("popular", {"passing": 1.0}, net=9), drill("liked", {"passing": 1.0}, vote=1), drill("disliked", {"passing": 1.0}, vote=-1)]
    out = plan({"priorities": [priority(1, "passing", {"passing": 1.0}), priority(2, "support", {"passing": 0.5})], "drills": drills})
    assert [(s["rank"], s["drill"]) for s in out["slots"]] == [(1, "liked"), (2, "popular")]
    shared = plan({"priorities": [priority(1, "passing", {"passing": 1.0}), priority(2, "support", {"passing": 0.5})],
                   "drills": [drill("rondo", {"passing": 1.0})]})
    assert [s["drill"] for s in shared["slots"]] == ["rondo", "rondo"] and "Also used for another priority" in shared["slots"][1]["reasons"][-1]


def test_club_slots_prefer_club_drills_and_gaps_are_reported_not_filled():
    out = plan({"priorities": [priority(1, "passing", {"passing": 1.0}), priority(2, "shooting", {"shooting": 1.0}), priority(3, "talk", {})],
                "drills": [drill("wall", {"passing": 1.0}, home=True, vote=1), drill("rondo", {"passing": 1.0})]})
    assert [(s["rank"], s["slot"], s["drill"]) for s in out["slots"]] == [(1, "club", "rondo"), (1, "home", "wall")]
    assert [(g["rank"], g["slot"], g["reason"]) for g in out["gaps"]] == [
        (2, "club", "No drills for this skill in the library yet."),
        (3, "club", "This skill has no tags in the skill matrix, so no drills can be matched.")]
    only_club = plan({"priorities": [priority(1, "passing", {"passing": 1.0})], "drills": [drill("rondo", {"passing": 1.0})]})
    assert only_club["gaps"] == [{"rank": 1, "skill_id": "passing", "label": "Passing", "slot": "home", "reason": "No home drill for this skill yet."}]


def test_a_home_drill_that_is_the_only_option_covers_training_and_home():
    out = plan({"priorities": [priority(1, "shooting", {"shooting": 1.0})], "drills": [drill("targets", {"shooting": 1.0}, home=True)]})
    assert [(s["slot"], s["drill"]) for s in out["slots"]] == [("club", "targets"), ("home", "targets")] and out["gaps"] == []
    assert out["slots"][1]["reasons"][-1] == "Same drill as at training: there is no other home drill for this skill yet."

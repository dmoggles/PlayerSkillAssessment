"""Team training sessions: the planner on fixed data, and the API."""
from app import sessions
from app.database import SessionLocal
from app.drills import DATA_DIR, load_file
from test_flows import clean_database, signed_in, starter_skills


def drill(slug, phase, players=(4, 8, 16), duration=(10, 15), tags=None, ladder=None, vote=0, levels=((1, 2), (2, 3), (3, 4), (4, 5))):
    tags = {"passing_short": 1.0} if tags is None else tags
    variations = [{"id": f"{slug}-{i}", "kind": ("regression", "base", "escalator", "escalator")[i], "title": f"v{i}", "levels": list(lv)}
                  for i, lv in enumerate(levels)]
    return {"slug": slug, "title": slug.title(), "session_phase": phase, "players": list(players), "duration": list(duration),
            "tags": tags, "tag_labels": {t: t.replace("_", " ") for t in tags}, "ladder_tags": ladder if ladder is not None else list(tags),
            "variations": variations, "my_vote": vote, "net_votes": 0}


def data(drills, groups=((3, 3, 3, 3, 3, 3, 3, 3),), length=60, **extra):
    return {"length": length, "focus": ["passing_short", "first_touch"], "groups": [{"levels": list(g)} for g in groups], "drills": drills, **extra}


def test_the_template_fills_each_phase_with_a_fitting_drill_or_the_coachs_own_block():
    drills = [drill("rondo", "technical"), drill("game", "small_sided_game", players=(6, 8, 12)), drill("press", "opposed", tags={"pressing": 1.0})]
    result = sessions.plan(data(drills))
    assert [b["phase"] for b in result["blocks"]] == ["warm_up", "technical", "opposed", "small_sided_game", "cool_down"]
    assert sum(b["minutes"] for b in result["blocks"]) == 60
    by_phase = {b["phase"]: b for b in result["blocks"]}
    assert by_phase["technical"]["drill"] == "rondo" and by_phase["technical"]["reasons"][0] == "Trains passing short."
    assert by_phase["opposed"]["drill"] == "press" and "Doesn't train the session's focus" in by_phase["opposed"]["reasons"][0]
    assert by_phase["warm_up"]["drill"] is None and by_phase["warm_up"]["title"].startswith("Warm-up")
    assert by_phase["cool_down"]["title"].startswith("Cool-down")
    for length in sessions.LENGTHS:
        assert sum(sessions.TEMPLATES[length].values()) == length


def test_drills_are_chosen_for_focus_size_votes_and_variety():
    focus_drill, other = drill("passing", "technical"), drill("touch", "technical", tags={"first_touch": 1.0})
    pick = lambda drills, **extra: sessions.plan(data(drills, **extra))["blocks"][1]["drill"]
    assert pick([other, focus_drill]) == "passing"  # the first focus tag counts most
    assert pick([focus_drill, {**drill("passing-two", "technical"), "my_vote": 1}]) == "passing-two"  # a like breaks a tie
    assert pick([{**focus_drill, "my_vote": -1}, other]) == "touch"  # disliked drills are never used
    assert pick([focus_drill, other], recent={"passing": 1}) == "touch"  # last session's drill gives way
    too_big = drill("big", "technical", players=(10, 12, 14))
    assert pick([too_big, other]) == "touch"  # 8 players can't run a drill that needs 10
    small = drill("pairs", "technical", players=(2, 2, 4))
    assert pick([small]) == "pairs" and "two of these side by side" in sessions.plan(data([small]))["blocks"][1]["reasons"][-1]
    assert pick([drill("tiny", "technical", players=(1, 1, 3))]) is None  # 8 is more than two set-ups
    # Drills for one or two players are home practice, even when a small group could run two of them.
    home = drill("wall-passes", "technical", players=(1, 1, 2))
    assert sessions.plan(data([home], groups=((3, 3, 3, 3),)))["blocks"][1]["drill"] is None
    keeper = drill("keeper", "technical", tags={"gk_shot_stopping": 1.0})
    assert pick([keeper]) is None  # not for an outfield focus
    assert sessions.plan({**data([keeper]), "focus": ["gk_shot_stopping"]})["blocks"][1]["drill"] == "keeper"
    # One drill per session, even when it fits two phases' worth of blocks.
    twice = sessions.plan(data([drill("rondo", "technical")], length=90))["blocks"]
    assert [b["drill"] for b in twice].count("rondo") == 1


def test_each_group_starts_at_its_own_version():
    groups = ((5, 5, 4), (3, 3, None), (1, 2, 1))
    block = sessions.plan(data([drill("rondo", "technical", players=(3, 4, 8))], groups=groups))["blocks"][1]
    assert block["variations"] == ["rondo-3", "rondo-2", "rondo-0"]
    # A drill whose versions don't describe the focus starts everyone at the base version.
    other = drill("rondo", "technical", players=(3, 4, 8), ladder=[])
    assert sessions.plan(data([other], groups=groups))["blocks"][1]["variations"] == ["rondo-1"] * 3


def test_in_groups_mode_the_warm_up_game_and_cool_down_run_together():
    groups = ((5, 5, 4), (3, 3, 2), (1, 2, 1))
    game = drill("game", "small_sided_game", players=(6, 8, 12))
    blocks = {b["phase"]: b for b in sessions.plan(data([drill("rondo", "technical", players=(3, 4, 8)), game], groups=groups))["blocks"]}
    assert blocks["technical"]["together"] is False and len(blocks["technical"]["variations"]) == 3
    assert blocks["small_sided_game"]["together"] is True and blocks["small_sided_game"]["variations"] == ["game-2"]  # 9 players at the median, 3
    assert blocks["cool_down"]["together"] is True and blocks["cool_down"]["drill"] is None


def test_players_split_into_balanced_level_groups():
    players = [(1, 4.5), (2, 1.0), (3, None), (4, 3.0), (5, 5.0), (6, 2.0), (7, None)]
    assert sessions.split_groups(players, 2) == [[5, 1, 3, 7], [4, 6, 2]]  # unrated players sit between the halves
    assert [len(g) for g in sessions.split_groups(players, 3)] == [3, 2, 2]


def test_coaches_plan_list_and_delete_team_sessions(monkeypatch):
    clean_database()
    with SessionLocal() as db:
        for name in ("drills_v1.json", "drills_v2.json", "drills_v3.json", "drills_v4.json", "drills_v5.json"):
            load_file(db, DATA_DIR / name)
    owner, csrf = signed_in("sessions-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Session squad"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    skills = starter_skills()
    ids = []
    for i, name in enumerate(("Ana", "Bea", "Cat", "Dee", "Eve", "Fay", "Gia", "Hal")):
        pid = owner.post(f"/teams/{team_id}/players", json={"name": name}, headers=headers).json()["id"]
        ids.append(pid)
        owner.put(f"/teams/{team_id}/players/{pid}/group", params={"period_id": period_id}, json={"age_group": 12}, headers=headers)
        body = {"player_id": pid, "period_id": period_id, "version": 0, "primary_position": "midfielder",
                "ratings": [{"skill_id": s, "score": 1 + (i % 5) if s == "passing_short" else 3} for s in skills]}
        assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200
        if i < 5:
            owner.put(f"/teams/{team_id}/priorities", params={"player_id": pid, "period_id": period_id},
                      json={"priorities": [{"skill_id": "passing_short", "rank": 1}]}, headers=headers)

    focus = owner.get(f"/teams/{team_id}/sessions/focus", params={"period_id": period_id}).json()
    assert focus[0] == {"tag_id": "passing_short", "label": focus[0]["label"], "players": 5}

    new = {"period_id": period_id, "date": "2026-10-20", "start_time": "18:30", "length": 60, "focus_tags": ["passing_short"], "player_ids": ids}
    made = owner.post(f"/teams/{team_id}/sessions", json=new, headers=headers)
    assert made.status_code == 201, made.text
    single = made.json()
    assert single["title"] == focus[0]["label"].capitalize() and single["versions"] == "single" and single["expected"] == 8
    assert [b["phase"] for b in single["blocks"]] == list(sessions.TEMPLATES[60])
    technical = next(b for b in single["blocks"] if b["phase"] == "technical")
    assert technical["drill"] and len(technical["versions"]) == 1 and technical["versions"][0]["title"]

    grouped = owner.post(f"/teams/{team_id}/sessions", json={**new, "date": "2026-10-22", "versions": "groups", "group_count": 2}, headers=headers).json()
    assert [len(g["players"]) for g in grouped["groups"]] == [4, 4]
    assert {p["name"] for p in grouped["groups"][0]["players"]} == {"Eve", "Dee", "Hal", "Cat"}  # highest passing ratings
    in_groups = [b for b in grouped["blocks"] if b["drill"] and not b["together"]]
    assert in_groups and all(len(b["versions"]) == 2 for b in in_groups)
    assert all(b["together"] for b in grouped["blocks"] if b["phase"] in ("warm_up", "small_sided_game", "cool_down"))

    for bad, words in (({**new, "length": 50}, "length of 45"), ({**new, "length": None}, "Choose a template"), ({**new, "player_ids": [999999]}, "active player"),
                       ({**new, "focus_tags": ["not_a_tag"]}, "focus"), ({**new, "player_ids": ids[:1], "versions": "groups"}, "at least 2")):
        refused = owner.post(f"/teams/{team_id}/sessions", json=bad, headers=headers)
        assert refused.status_code == 422 and words in refused.text, refused.text

    listed = owner.get(f"/teams/{team_id}/sessions").json()
    assert [s["date"] for s in listed] == ["2026-10-22", "2026-10-20"]
    patched = owner.patch(f"/teams/{team_id}/sessions/{single['id']}", json={"title": "Tuesday passing", "start_time": ""}, headers=headers).json()
    assert (patched["title"], patched["start_time"]) == ("Tuesday passing", None)

    # Deleting a player takes them out of every session; deleting the period takes its sessions.
    owner.post(f"/teams/{team_id}/players/{ids[4]}/archive", headers=headers)
    assert owner.request("DELETE", f"/teams/{team_id}/players/{ids[4]}", json={"confirm_name": "Eve"}, headers=headers).status_code == 200
    after = owner.get(f"/teams/{team_id}/sessions/{grouped['id']}").json()
    assert "Eve" not in {p["name"] for g in after["groups"] for p in g["players"]} and after["expected"] == 7
    assert owner.delete(f"/teams/{team_id}/sessions/{single['id']}", headers=headers).json()["message"] == "Session deleted."
    assert owner.get(f"/teams/{team_id}/sessions/{single['id']}").status_code == 404
    assert owner.delete(f"/teams/{team_id}/periods/{period_id}", headers=headers).status_code == 200
    assert owner.get(f"/teams/{team_id}/sessions").json() == []
    actions = [e["action"] for e in owner.get(f"/teams/{team_id}/audit").json()]
    assert actions.count("session_created") == 2 and "session_deleted" in actions


def test_coaches_edit_a_session(monkeypatch):
    clean_database()
    with SessionLocal() as db:
        for name in ("drills_v1.json", "drills_v2.json", "drills_v3.json", "drills_v4.json", "drills_v5.json"):
            load_file(db, DATA_DIR / name)
    owner, csrf = signed_in("sessions-editor@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Editors"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    skills = starter_skills()
    ids = []
    for i in range(10):
        pid = owner.post(f"/teams/{team_id}/players", json={"name": f"Player {i}"}, headers=headers).json()["id"]
        ids.append(pid)
        owner.put(f"/teams/{team_id}/players/{pid}/group", params={"period_id": period_id}, json={"age_group": 12}, headers=headers)
        owner.put(f"/teams/{team_id}/assessments/coach", headers=headers, json={"player_id": pid, "period_id": period_id, "version": 0, "primary_position": "midfielder",
                  "ratings": [{"skill_id": s, "score": 1 + (i % 5) if s == "passing_short" else 3} for s in skills]})
    url = f"/teams/{team_id}/sessions"
    session = owner.post(url, json={"period_id": period_id, "date": "2026-10-20", "length": 60, "focus_tags": ["passing_short"], "player_ids": ids,
                                    "versions": "groups", "group_count": 2}, headers=headers).json()
    url = f"{url}/{session['id']}"
    technical = next(b for b in session["blocks"] if b["phase"] == "technical")
    assert technical["drill"] and not technical["together"] and len(technical["drill_versions"]) >= 2

    # Alternatives, then a different drill: the coach's choice, at each group's version.
    options = owner.get(f"{url}/blocks/{technical['id']}/alternatives").json()
    other = next(o for o in options["ranked"] if o["slug"] != technical["drill"]["slug"])
    changed = owner.put(f"{url}/blocks/{technical['id']}", json={"drill": other["slug"], "minutes": 20}, headers=headers).json()
    block = next(b for b in changed["blocks"] if b["id"] == technical["id"])
    assert (block["drill"]["slug"], block["minutes"], block["chosen_by"], len(block["versions"])) == (other["slug"], 20, "coach", 2)
    # Versions chosen by hand must belong to the drill, one per group.
    easiest = block["drill_versions"][0]["id"]
    assert owner.put(f"{url}/blocks/{technical['id']}", json={"versions": [easiest]}, headers=headers).status_code == 422
    assert owner.put(f"{url}/blocks/{technical['id']}", json={"versions": [easiest, 999999]}, headers=headers).status_code == 422
    same = owner.put(f"{url}/blocks/{technical['id']}", json={"versions": [easiest, easiest]}, headers=headers).json()
    assert [v["variation_id"] for v in next(b for b in same["blocks"] if b["id"] == technical["id"])["versions"]] == [easiest, easiest]

    # The coach's own activity, added and turned into a block without a drill; blocks stay in phase order.
    added = owner.post(f"{url}/blocks", json={"phase": "warm_up", "minutes": 5, "title": "Rondo tag"}, headers=headers).json()
    assert [b["phase"] for b in added["blocks"]][:2] == ["warm_up", "warm_up"] and added["blocks"][1]["title"] == "Rondo tag"
    assert owner.post(f"{url}/blocks", json={"phase": "warm_up", "minutes": 5}, headers=headers).status_code == 422
    opposed = next(b for b in added["blocks"] if b["phase"] == "opposed")
    own = owner.put(f"{url}/blocks/{opposed['id']}", json={"drill": None, "title": "Match play"}, headers=headers).json()
    assert next(b for b in own["blocks"] if b["id"] == opposed["id"])["drill"] is None
    removed = owner.delete(f"{url}/blocks/{added['blocks'][1]['id']}", headers=headers).json()
    assert len(removed["blocks"]) == len(added["blocks"]) - 1

    # Moving players between groups: every expected player exactly once.
    a, b = [p["id"] for p in removed["groups"][0]["players"]], [p["id"] for p in removed["groups"][1]["players"]]
    assert owner.put(f"{url}/groups", json={"groups": [a, b[1:]]}, headers=headers).status_code == 422
    moved = owner.put(f"{url}/groups", json={"groups": [a + b[:1], b[1:]]}, headers=headers).json()
    assert [len(g["players"]) for g in moved["groups"]] == [6, 4]

    # A note doesn't make a block the coach's choice; other changes do.
    warm_up = next(b for b in moved["blocks"] if b["phase"] == "warm_up")
    noted = owner.put(f"{url}/blocks/{warm_up['id']}", json={"notes": "Went well"}, headers=headers).json()
    assert next(b for b in noted["blocks"] if b["id"] == warm_up["id"])["chosen_by"] == "planner"
    # Re-planning keeps the coach's choices and replans the rest.
    again = owner.post(f"{url}/regenerate", headers=headers).json()
    kept = {b["id"] for b in again["blocks"] if b["chosen_by"] == "coach"}
    assert technical["id"] in kept and opposed["id"] in kept
    assert [b["phase"] for b in again["blocks"]] == sorted((b["phase"] for b in again["blocks"]), key=sessions.PHASES.index)


def test_attendance_before_and_after_a_session(monkeypatch):
    clean_database()
    with SessionLocal() as db:
        for name in ("drills_v1.json", "drills_v2.json", "drills_v3.json", "drills_v4.json", "drills_v5.json"):
            load_file(db, DATA_DIR / name)
    owner, csrf = signed_in("sessions-register@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Register"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    ids = [owner.post(f"/teams/{team_id}/players", json={"name": f"P{i}"}, headers=headers).json()["id"] for i in range(7)]
    session = owner.post(f"/teams/{team_id}/sessions", json={"period_id": period_id, "date": "2026-10-20", "length": 45, "focus_tags": ["passing_short"],
                                                             "player_ids": ids[:6], "versions": "groups", "group_count": 2}, headers=headers).json()
    url = f"/teams/{team_id}/sessions/{session['id']}"
    # Before: one more player expected (joins the smaller group), one no longer.
    planned = owner.put(f"{url}/attendance", json={"players": [{"player_id": ids[6], "expected": True}, {"player_id": ids[0], "expected": False}]}, headers=headers).json()
    assert planned["expected"] == 6 and sorted(len(g["players"]) for g in planned["groups"]) == [3, 3]
    assert ids[0] not in {p["id"] for g in planned["groups"] for p in g["players"]} and ids[6] in {p["id"] for g in planned["groups"] for p in g["players"]}
    # After: who came, including someone who wasn't expected.
    done = owner.put(f"{url}/attendance", json={"players": [{"player_id": pid, "attended": True} for pid in ids[1:5]] + [{"player_id": ids[0], "attended": True}]}, headers=headers).json()
    assert done["attended"] == 5 and done["expected"] == 6
    assert owner.put(f"{url}/attendance", json={"players": [{"player_id": 999999, "attended": True}]}, headers=headers).status_code == 422
    # Notes on the session and a block; the player's export lists the session.
    owner.patch(url, json={"notes": "Good energy"}, headers=headers)
    block = done["blocks"][0]
    after = owner.put(f"{url}/blocks/{block['id']}", json={"notes": "Too long"}, headers=headers).json()
    assert after["notes"] == "Good energy" and after["blocks"][0]["notes"] == "Too long"
    exported = owner.get(f"/teams/{team_id}/players/{ids[0]}/export").json()["training_sessions"]
    assert exported == [{"date": "2026-10-20", "title": exported[0]["title"], "expected": False, "attended": True, "group": None}]


def test_warm_ups_and_cool_downs_may_train_no_particular_skill():
    import json
    from app.drills import drill_problems
    raw = next(d for d in json.loads((DATA_DIR / "drills_v5.json").read_text())["drills"] if d["session_phase"] == "warm_up")
    active = set(raw["tags"])
    assert drill_problems({**raw, "tags": {}, "ladder_tags": None}, active) == []
    assert drill_problems({**raw, "session_phase": "cool_down", "tags": {}, "ladder_tags": None}, active) == []
    assert "needs at least one Main (1.0) tag" in drill_problems({**raw, "session_phase": "technical", "tags": {}, "ladder_tags": None}, active)
    # A general warm-up fits any focus; a tagged one that trains the focus is still preferred.
    general = drill("jog-and-mobility", "warm_up", tags={}, ladder=[])
    block = sessions.plan(data([general]))["blocks"][0]
    assert block["drill"] == "jog-and-mobility" and block["reasons"] == ["A general warm-up, for any focus."]
    assert sessions.plan(data([general, drill("passing-warm-up", "warm_up")]))["blocks"][0]["drill"] == "passing-warm-up"


def test_a_long_warm_up_programme_takes_its_time_from_the_practices():
    programme = drill("injury-prevention", "warm_up", tags={"coordination_balance": 1.0}, duration=(15, 20))
    blocks = {b["phase"]: b for b in sessions.plan(data([programme], length=60))["blocks"]}
    assert blocks["warm_up"]["drill"] == "injury-prevention" and blocks["warm_up"]["minutes"] == 15
    assert (blocks["technical"]["minutes"], blocks["opposed"]["minutes"]) == (12, 13)  # 15 and 15, less 5 between them
    assert "technical and opposed practices are a little shorter" in blocks["warm_up"]["reasons"][-1]
    assert sum(b["minutes"] for b in blocks.values()) == 60
    # In 45 minutes the practices keep at least 8 minutes each.
    short = {b["phase"]: b["minutes"] for b in sessions.plan(data([programme], length=45))["blocks"]}
    assert short["warm_up"] == 15 and (short["technical"], short["opposed"]) == (8, 9) and sum(short.values()) == 45
    # A warm-up that fits needs no extra time, and re-planning around a coach's own practice doesn't lengthen it.
    general = drill("jog", "warm_up", tags={}, ladder=[], duration=(8, 10))
    assert sessions.plan(data([general]))["blocks"][0]["minutes"] == 10
    kept = sessions.plan({**data([programme]), "kept_phases": ["technical"]})["blocks"][0]
    assert kept["minutes"] == 10


def test_a_set_programme_starts_everyone_at_its_first_version():
    from app.plans import build_slot
    programme = drill("programme", "warm_up", tags={"coordination_balance": 1.0}, ladder=[])
    priority = {"rank": 1, "skill_id": "balance", "label": "Balance", "level": 5, "tags": {"coordination_balance": 1.0}}
    slot = build_slot(priority, "club", programme, weeks=4)
    assert {v["id"] for v in slot["weeks"]} == {"programme-1"}  # the base, even for a player rated 5
    assert "move up one version at a time" in slot["reasons"][1]
    block = sessions.plan({**data([programme]), "focus": ["coordination_balance"], "groups": [{"levels": [5, 5, 5, 5]}]})["blocks"][0]
    assert block["variations"] == ["programme-1"]


def test_a_template_plans_only_its_parts_in_session_order():
    drills = [drill("rondo", "technical"), drill("game", "small_sided_game", players=(6, 8, 12))]
    minutes = {"cool_down": 5, "full_squad_game": 25, "warm_up": 10, "small_sided_game": 20}
    result = sessions.plan(data(drills, length=60, minutes=minutes, groups=((1, 1, 1, 1), (4, 4, 4, 4))))
    blocks = {b["phase"]: b for b in result["blocks"]}
    assert list(blocks) == ["warm_up", "small_sided_game", "full_squad_game", "cool_down"]
    assert [b["minutes"] for b in result["blocks"]] == [10, 20, 25, 5]
    # No drill is a full squad game yet: the coach's own match, with everyone together even in groups mode.
    squad_game = blocks["full_squad_game"]
    assert squad_game["drill"] is None and squad_game["title"].startswith("Full squad game") and squad_game["together"]
    assert "rondo" not in {b["drill"] for b in result["blocks"]}


def test_a_long_warm_up_takes_its_time_from_the_practices_the_template_has():
    programme = drill("injury-prevention", "warm_up", tags={"coordination_balance": 1.0}, duration=(20, 20))
    plan = lambda minutes: {b["phase"]: b for b in sessions.plan(data([programme], length=sum(minutes.values()), minutes=minutes))["blocks"]}
    # Only an opposed practice: it gives all the extra time.
    blocks = plan({"warm_up": 10, "opposed": 25, "small_sided_game": 20, "cool_down": 5})
    assert (blocks["warm_up"]["minutes"], blocks["opposed"]["minutes"]) == (20, 15)
    assert "so the opposed practice is a little shorter" in blocks["warm_up"]["reasons"][-1]
    # A practice keeps at least MIN_PRACTICE minutes: down to that, the programme gets its time; past it, it doesn't.
    blocks = plan({"warm_up": 10, "technical": 10, "opposed": 10, "small_sided_game": 20})
    assert (blocks["warm_up"]["minutes"], blocks["technical"]["minutes"], blocks["opposed"]["minutes"]) == (20, 5, 5)
    blocks = plan({"warm_up": 10, "technical": 12, "small_sided_game": 20})
    assert (blocks["warm_up"]["minutes"], blocks["technical"]["minutes"]) == (10, 12)
    assert not any("shorter" in r for r in blocks["warm_up"]["reasons"])
    # Without technical or opposed practices, the warm-up keeps its minutes.
    blocks = plan({"warm_up": 15, "small_sided_game": 30, "cool_down": 5})
    assert blocks["warm_up"]["minutes"] == 15
    assert sum(b["minutes"] for b in plan({"warm_up": 10, "technical": 15, "opposed": 15, "cool_down": 5}).values()) == 45


def test_coaches_share_session_templates(monkeypatch):
    clean_database()
    with SessionLocal() as db:
        for name in sorted(p.name for p in DATA_DIR.glob("drills_v*.json")):
            load_file(db, DATA_DIR / name)
    owner, csrf = signed_in("templates-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Template squad"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    ids = [owner.post(f"/teams/{team_id}/players", json={"name": n}, headers=headers).json()["id"] for n in ("Ana", "Bea", "Cat", "Dee", "Eve", "Fay")]
    url = f"/teams/{team_id}/session-templates"
    match_prep = {"name": "Match prep", "length": 60, "minutes": {"cool_down": 5, "warm_up": 10, "opposed": 20, "full_squad_game": 25}}

    for bad, words in (({**match_prep, "length": 70}, "add up to 60 of 70"), ({**match_prep, "minutes": {"warm_up": 60, "juggling": 0}}, "Unknown part"),
                       ({**match_prep, "minutes": {}}, "minutes"), ({**match_prep, "name": "  "}, "name")):
        refused = owner.post(url, json=bad, headers=headers)
        assert refused.status_code == 422 and words in refused.text, refused.text
    made = owner.post(url, json=match_prep, headers=headers)
    assert made.status_code == 201, made.text
    template = made.json()
    assert list(template["minutes"]) == ["warm_up", "opposed", "full_squad_game", "cool_down"]  # stored in session order
    assert owner.post(url, json={**match_prep, "name": "match PREP"}, headers=headers).status_code == 409

    new = {"period_id": period_id, "date": "2026-10-20", "focus_tags": ["passing_short"], "player_ids": ids, "template_id": template["id"],
           "versions": "groups", "group_count": 2}
    session = owner.post(f"/teams/{team_id}/sessions", json=new, headers=headers).json()
    assert session["length"] == 60 and session["template"] == {"id": template["id"], "name": "Match prep"}
    assert [b["phase"] for b in session["blocks"]] == ["warm_up", "opposed", "full_squad_game", "cool_down"]
    assert sum(b["minutes"] for b in session["blocks"]) == 60
    assert next(b for b in session["blocks"] if b["phase"] == "full_squad_game")["together"]
    assert owner.get(url).json()[0]["used"] == 1

    # Editing the template leaves the planned session's breakdown alone, also when it is planned again.
    edited = owner.put(f"{url}/{template['id']}", json={**match_prep, "minutes": {"warm_up": 10, "small_sided_game": 50}}, headers=headers)
    assert edited.status_code == 200 and edited.json()["used"] == 1
    again = owner.post(f"/teams/{team_id}/sessions/{session['id']}/regenerate", headers=headers).json()
    assert [b["phase"] for b in again["blocks"]] == ["warm_up", "opposed", "full_squad_game", "cool_down"]
    # A coach can add a full squad game to any session.
    added = owner.post(f"/teams/{team_id}/sessions/{session['id']}/blocks", json={"phase": "full_squad_game", "minutes": 10, "title": "7v7"}, headers=headers)
    assert added.status_code == 201, added.text

    other = owner.post("/teams", json={"name": "Other squad"}, headers=headers).json()["id"]
    assert owner.post(f"/teams/{other}/sessions", json={**new, "period_id": period_id}, headers=headers).status_code in (404, 422)
    assert owner.put(f"/teams/{other}/session-templates/{template['id']}", json=match_prep, headers=headers).status_code == 404

    assert owner.delete(f"{url}/{template['id']}", headers=headers).json()["message"] == "Template deleted."
    kept = owner.get(f"/teams/{team_id}/sessions/{session['id']}").json()
    assert kept["template"] is None and len(kept["blocks"]) == 5
    assert owner.post(f"/teams/{team_id}/sessions", json=new, headers=headers).status_code == 404
    actions = [e["action"] for e in owner.get(f"/teams/{team_id}/audit").json()]
    assert "session_template_created" in actions and "session_template_deleted" in actions


ORDER = ["goalkeeper", "defender", "midfielder", "winger", "striker"]


def test_match_teams_balance_positions_then_ages_then_levels():
    def player(pid, position, age=10, level=3.0):
        return {"id": pid, "position": position, "age": age, "level": level}
    squad = [player(1, "goalkeeper", level=4.0), player(2, "goalkeeper", level=2.0),
             player(3, "defender", level=4.0), player(4, "defender", level=3.5), player(5, "defender", level=2.0), player(6, "defender", level=1.5),
             player(7, "midfielder", 9, 4.0), player(8, "midfielder", 9, 3.0), player(9, "midfielder", 11, 2.0), player(10, "midfielder", 11, 1.0),
             player(11, "striker", level=3.0), player(12, None, level=None), player(13, "striker", level=2.5)]
    a, b = sessions.balance_teams(squad, ORDER)
    by_id = {p["id"]: p for p in squad}
    teams = [[by_id[pid] for pid in a], [by_id[pid] for pid in b]]
    assert sorted(len(t) for t in teams) == [6, 7]
    for position in ("goalkeeper", "defender", "midfielder", "striker"):
        assert [sum(p["position"] == position for p in t) for t in teams] == [2 if position in ("defender", "midfielder") else 1] * 2
    ages = [sum(p["age"] for p in t) / len(t) for t in teams]
    assert abs(ages[0] - ages[1]) < 0.2
    levels = [[p["level"] for p in t if p["level"] is not None] for t in teams]
    assert abs(sum(levels[0]) / len(levels[0]) - sum(levels[1]) / len(levels[1])) <= 0.1
    assert sessions.teams_cost(teams) < 1

    # Newcomers to a coach's teams fill the smaller team, then go where they balance best.
    joined = sessions.add_to_teams([[by_id[1], by_id[3]], [by_id[2]]], [player(20, "defender"), player(21, "goalkeeper")])
    assert joined == [[1, 3, 21], [2, 20]]
    assert sessions.balance_teams([player(1, "defender")], ORDER) == [[1], []]


def test_a_full_squad_game_suggests_two_teams(monkeypatch):
    clean_database()
    with SessionLocal() as db:
        for name in sorted(p.name for p in DATA_DIR.glob("drills_v*.json")):
            load_file(db, DATA_DIR / name)
    owner, csrf = signed_in("match-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Match squad"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    skills = starter_skills()
    keeper_skills = starter_skills("goalkeeper")
    positions = ["goalkeeper", "goalkeeper", "defender", "defender", "midfielder", "midfielder", "striker", "striker"]
    ids = []
    for i, (name, position) in enumerate(zip(("Ana", "Bea", "Cat", "Dee", "Eve", "Fay", "Gia", "Hal"), positions)):
        pid = owner.post(f"/teams/{team_id}/players", json={"name": name}, headers=headers).json()["id"]
        ids.append(pid)
        owner.put(f"/teams/{team_id}/players/{pid}/group", params={"period_id": period_id}, json={"age_group": 10 + i % 2}, headers=headers)
        body = {"player_id": pid, "period_id": period_id, "version": 0, "primary_position": position,
                "ratings": [{"skill_id": s, "score": 1 + i % 4} for s in (keeper_skills if position == "goalkeeper" else skills)]}
        assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200
    late = owner.post(f"/teams/{team_id}/players", json={"name": "Ivy"}, headers=headers).json()["id"]
    template = owner.post(f"/teams/{team_id}/session-templates", headers=headers,
                          json={"name": "Match", "length": 45, "minutes": {"warm_up": 10, "full_squad_game": 30, "cool_down": 5}}).json()
    plain = owner.post(f"/teams/{team_id}/sessions", headers=headers, json={"period_id": period_id, "date": "2026-10-20", "length": 60,
                                                                           "focus_tags": ["passing_short"], "player_ids": ids}).json()
    assert plain["match_teams"] is None  # no full squad game

    session = owner.post(f"/teams/{team_id}/sessions", headers=headers, json={"period_id": period_id, "date": "2026-10-21", "template_id": template["id"],
                                                                             "focus_tags": ["passing_short"], "player_ids": ids}).json()
    match = session["match_teams"]
    assert match["by"] == "planner" and [t["name"] for t in match["teams"]] == ["Team 1", "Team 2"]
    for team in match["teams"]:
        assert [(p["label"], p["count"]) for p in team["positions"]] == [("Goalkeeper", 1), ("Defender", 1), ("Midfielder", 1), ("Striker", 1)]
        assert team["players"][0]["position_label"] == "Goalkeeper" and team["unrated"] == 0
    assert abs(match["teams"][0]["average_age_group"] - match["teams"][1]["average_age_group"]) <= 0.5
    assert abs(match["teams"][0]["average_level"] - match["teams"][1]["average_level"]) <= 0.5
    url = f"/teams/{team_id}/sessions/{session['id']}"

    # The coach moves players; their teams keep them, and a newcomer without an assessment joins the smaller team.
    first, second = [[p["id"] for p in t["players"]] for t in match["teams"]]
    mine = [first + second[:1], second[1:]]
    assert owner.put(f"{url}/match-teams", json={"teams": [first, second[1:]]}, headers=headers).status_code == 422
    moved = owner.put(f"{url}/match-teams", json={"teams": mine}, headers=headers).json()["match_teams"]
    assert moved["by"] == "coach" and [len(t["players"]) for t in moved["teams"]] == [5, 3]
    joined = owner.put(f"{url}/attendance", json={"players": [{"player_id": late, "expected": True}, {"player_id": first[0], "expected": False}]},
                       headers=headers).json()["match_teams"]
    assert [sorted(p["id"] for p in t["players"]) for t in joined["teams"]] == [sorted(mine[0][1:]), sorted(mine[1] + [late])]
    assert joined["teams"][1]["unrated"] == 1 and any(p["position"] is None for p in joined["teams"][1]["players"])

    # Suggesting again balances from scratch.
    again = owner.post(f"{url}/match-teams/suggest", headers=headers).json()["match_teams"]
    assert again["by"] == "planner" and sorted(len(t["players"]) for t in again["teams"]) == [4, 4]
    assert owner.post(f"/teams/{team_id}/sessions/{plain['id']}/match-teams/suggest", headers=headers).status_code == 409

    # A session planned before match teams existed gets them when it's opened.
    with SessionLocal() as db:
        from app.models import TrainingSession
        db.get(TrainingSession, session["id"]).match_teams = None
        db.commit()
    assert owner.get(url).json()["match_teams"]["by"] == "planner"

    # Removing the full squad game removes the teams.
    block = next(b for b in session["blocks"] if b["phase"] == "full_squad_game")
    assert owner.delete(f"{url}/blocks/{block['id']}", headers=headers).json()["match_teams"] is None

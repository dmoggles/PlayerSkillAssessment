"""Team training sessions: the planner on fixed data, and the API."""
from app import sessions
from app.database import SessionLocal
from app.drills import DATA_DIR, load_file
from test_flows import clean_database, signed_in, starter_skills


def drill(slug, phase, players=(4, 8, 16), duration=(10, 15), tags=None, ladder=None, vote=0, levels=((1, 2), (2, 3), (3, 4), (4, 5))):
    tags = tags or {"passing_short": 1.0}
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
    assert [b["phase"] for b in result["blocks"]] == list(sessions.PHASES)
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
    assert [b["phase"] for b in single["blocks"]] == list(sessions.PHASES)
    technical = next(b for b in single["blocks"] if b["phase"] == "technical")
    assert technical["drill"] and len(technical["versions"]) == 1 and technical["versions"][0]["title"]

    grouped = owner.post(f"/teams/{team_id}/sessions", json={**new, "date": "2026-10-22", "versions": "groups", "group_count": 2}, headers=headers).json()
    assert [len(g["players"]) for g in grouped["groups"]] == [4, 4]
    assert {p["name"] for p in grouped["groups"][0]["players"]} == {"Eve", "Dee", "Hal", "Cat"}  # highest passing ratings
    with_drill = [b for b in grouped["blocks"] if b["drill"]]
    assert with_drill and all(len(b["versions"]) == 2 for b in with_drill)

    for bad, words in (({**new, "length": 50}, "length"), ({**new, "player_ids": [999999]}, "active player"),
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

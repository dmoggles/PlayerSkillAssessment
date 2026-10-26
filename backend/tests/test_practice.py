"""Practice scenarios: every shipped scenario is well formed, and the checker catches the mistakes authors make."""
import copy
import json
from app import practice
from app.database import SessionLocal
from app.models import SkillTag
from test_flows import signed_in

DATA = json.loads(practice.DATA_FILE.read_text())


def test_every_shipped_scenario_is_well_formed_and_trains_real_skills():
    with SessionLocal() as db:
        tags = {t.id for t in db.query(SkillTag)}
    assert practice.file_problems(DATA, tags) == []
    for s in practice.scenarios():
        assert s["pitch"] == practice.pitch_for(s, DATA["formats"]) and set(s["pitch"]) == practice.FORMAT_KEYS


def test_the_checker_names_each_mistake():
    good = DATA["scenarios"][0]
    formats = DATA["formats"]

    def problems(change):
        bad = copy.deepcopy(good)
        change(bad)
        return practice.scenario_problems(bad, formats)

    frame = lambda s: s["frames"][0]
    assert problems(lambda s: None) == []
    assert any("format" in p for p in problems(lambda s: s.update(format="3v3")))
    assert any("ages" in p for p in problems(lambda s: s.update(ages=[12, 9])))
    assert any("controlled player" in p for p in problems(lambda s: s.update(controlled="nobody")))
    assert any("on the pitch" in p for p in problems(lambda s: frame(s)["opponents"][0].update(x=80)))
    assert any("mark must be an opponent" in p for p in problems(lambda s: frame(s).update(mark="you")))
    assert any("needs the frame's mark" in p for p in problems(lambda s: frame(s).pop("mark")))
    assert any("one zone scores 100" in p for p in problems(lambda s: frame(s)["target"]["zones"][0].update(points=90)))
    assert any("unknown check" in p for p in problems(lambda s: frame(s)["target"]["checks"].append({"check": "OFFSIDE"})))
    assert any("needs a teammate pressing" in p for p in problems(lambda s: frame(s)["target"]["checks"].append({"check": "BEHIND_PRESSER"})))
    assert any("at a2's feet" in p for p in problems(lambda s: frame(s)["ball"].update(x=25)))
    assert any("thresholds" in p for p in problems(lambda s: s.update(thresholds={"tightDistance": 4, "speed": 2})))
    assert any("unknown topic" in p for p in problems(lambda s: s.update(topic="juggling")))
    two = lambda s: s["frames"].append({**copy.deepcopy(frame(s)), "id": "f2"})
    assert any("every frame but the last needs next" in p for p in problems(two))
    # A scenario can use its own pitch measurements, for any format.
    own = copy.deepcopy(good)
    own["pitch"] = {"length": 60, "penaltyArea": {"depth": 10}}
    pitch = practice.pitch_for(own, formats)
    assert (pitch["length"], pitch["width"], pitch["penaltyArea"]) == (60, formats["7v7"]["width"], {"depth": 10, "width": formats["7v7"]["penaltyArea"]["width"]})


def test_coaches_get_the_library(monkeypatch):
    coach, _ = signed_in("practice-coach@example.com", monkeypatch)
    library = coach.get("/practice/scenarios").json()
    topic = library["topics"][0]
    assert topic["id"] == "defending_off_ball" and topic["stages"][0] == {"stage": 1, "label": "Goal-side basics"}
    assert len(library["scenarios"]) == len(DATA["scenarios"]) and all("length" in s["pitch"] for s in library["scenarios"])


def test_a_coach_sets_practice_and_a_player_does_it_through_their_link(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers import practice as routes
    from test_flows import clean_database
    clean_database()
    coach, csrf = signed_in("practice-owner@example.com", monkeypatch)
    other, other_csrf = signed_in("practice-other@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = coach.post("/teams", json={"name": "Practisers"}, headers=headers).json()["id"]
    player_id = coach.post(f"/teams/{team_id}/players", json={"name": "Isla Novak"}, headers=headers).json()["id"]
    url = f"/teams/{team_id}/players/{player_id}/practice"
    stage_one = [s for s in practice.scenarios() if s["topic"] == "defending_off_ball" and s["stage"] == 1]

    # Setting practice: a stage, or one scenario, with a date; nonsense is refused.
    assert coach.post(f"{url}/assignments", json={"topic": "defending_off_ball", "stage": 9}, headers=headers).status_code == 422
    assert coach.post(f"{url}/assignments", json={"scenario_id": "nope"}, headers=headers).status_code == 422
    state = coach.post(f"{url}/assignments", json={"topic": "defending_off_ball", "stage": 1, "due_on": "2026-11-01"}, headers=headers).json()
    assert state["assignments"][0]["label"] == "Off-ball defending, stage 1: Goal-side basics"
    assert state["assignments"][0]["scenario_ids"] == [s["id"] for s in stage_one] and state["link"] is None
    # Another team's coach can't see or set it.
    assert other.get(url).status_code == 404

    # The link: shown once, opens the player's practice with their first name only.
    issued = coach.post(f"{url}/link", headers=headers).json()
    token = issued["url"].rsplit("/", 1)[1]
    player = TestClient(app)
    mine = player.get(f"/practice/{token}").json()
    assert mine["name"] == "Isla" and "Novak" not in str(mine)
    assert [s["id"] for s in mine["assignments"][0]["scenarios"]] == [s["id"] for s in stage_one]
    assert mine["assignments"][0]["scenarios"][0]["progress"] == {"frames_done": 0, "frames": 1, "done": False, "stars": 0}
    assert coach.get(url).json()["link"]["opened_at"] is not None

    # Attempts: they must fit the frame.
    scenario = stage_one[0]
    frame = scenario["frames"][0]
    best = max(frame["target"]["zones"], key=lambda z: z["points"])
    attempt = {"scenario_id": scenario["id"], "frame_id": frame["id"], "attempt_no": 1, "x": 9.5, "y": 9.0, "points": 0, "zone_hit": None,
               "failed_checks": ["GOAL_SIDE"], "duration_ms": 4200}
    post = lambda body: player.post(f"/practice/{token}/attempts", json=body)
    assert post(attempt).status_code == 201
    assert post({**attempt, "points": 100}).status_code == 422, "points no zone gives"
    assert post({**attempt, "failed_checks": ["OFFSIDE"]}).status_code == 422
    assert post({**attempt, "x": 90}).status_code == 422, "off the pitch"
    assert post({**attempt, "frame_id": "f9"}).status_code == 422
    not_set = next(s for s in practice.scenarios() if s["stage"] == 3)
    assert post({**attempt, "scenario_id": not_set["id"]}).status_code == 404, "only what the coach set"
    assert post({**attempt, "attempt_no": 2, "x": best["cx"], "y": best["cy"], "points": 100, "zone_hit": frame["target"]["zones"].index(best), "failed_checks": []}).status_code == 201

    # The coach sees progress (stars from the first try), attempts this week, concepts and the most-missed check.
    state = coach.get(url).json()
    assert state["progress"][scenario["id"]] == {"frames_done": 1, "frames": 1, "done": True, "stars": 1}
    summary = state["summary"]
    assert summary["attempts"] == 2 and summary["weeks"][-1]["attempts"] == 2 and summary["weeks"][-1]["average"] == 0
    assert summary["missed"] == [{"check": "GOAL_SIDE", "count": 1}]
    assert {c["concept"] for c in summary["concepts"]} == set(scenario["concepts"])

    # Too many attempts in an hour are refused.
    monkeypatch.setattr(routes, "ATTEMPTS_PER_HOUR", 2)
    assert post(attempt).status_code == 429
    monkeypatch.setattr(routes, "ATTEMPTS_PER_HOUR", 300)

    # A new link replaces the old; revoking stops it at once.
    second = coach.post(f"{url}/link", headers=headers).json()["url"].rsplit("/", 1)[1]
    assert player.get(f"/practice/{token}").status_code == 404
    assert coach.request("DELETE", f"{url}/link", headers=headers).json()["link"] is None
    assert player.get(f"/practice/{second}").status_code == 404

    # Unsetting keeps the attempts; the export has it all; deleting the player removes it.
    assignment_id = state["assignments"][0]["id"]
    assert coach.request("DELETE", f"{url}/assignments/{assignment_id}", headers=headers).json()["summary"]["attempts"] == 2
    exported = coach.get(f"/teams/{team_id}/players/{player_id}/export").json()["practice"]
    assert len(exported["attempts"]) == 2 and exported["attempts"][0]["failed_checks"] == ["GOAL_SIDE"]
    assert coach.post(f"/teams/{team_id}/players/{player_id}/archive", headers=headers).status_code == 200
    assert coach.request("DELETE", f"/teams/{team_id}/players/{player_id}", json={"confirm_name": "Isla Novak"}, headers=headers).status_code == 200
    from app.models import PracticeAttempt
    with SessionLocal() as db:
        assert db.query(PracticeAttempt).filter_by(player_id=player_id).count() == 0

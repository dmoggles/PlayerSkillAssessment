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

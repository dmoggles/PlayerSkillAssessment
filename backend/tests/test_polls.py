"""Coaching polls: the shipped poll is well formed, anyone with the link can answer and change their answers, only
site admins see the results, and with polls switched off (production) nothing answers."""
from fastapi.testclient import TestClient
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import User
from app.routers import polls
from test_flows import clean_database, signed_in

POLL = "/polls/press-or-cover"
ME, YOU = "me-0123456789abcdef", "you-0123456789abcdef"


def test_every_poll_is_well_formed():
    assert polls.polls()
    for poll in polls.polls().values():
        assert polls.poll_problems(poll) == []
    assert len(polls.polls()["press-or-cover"]["scenarios"]) == 10


def test_anyone_with_the_link_answers_and_can_change_their_mind(monkeypatch):
    clean_database()
    client = TestClient(app)
    poll = client.get(POLL).json()
    first, second = poll["scenarios"][0]["id"], poll["scenarios"][1]["id"]
    assert "references" not in poll["scenarios"][0] and poll["answers"] == {}
    assert client.put(f"{POLL}/answers/{first}", json={"respondent": ME, "x": 15, "y": 18}).status_code == 200
    assert client.put(f"{POLL}/answers/{first}", json={"respondent": ME, "name": "  Sam   (U12) ", "x": 16.123, "y": 19}).status_code == 200
    assert client.put(f"{POLL}/answers/{second}", json={"respondent": ME, "x": 10, "y": 10}).status_code == 200
    mine = client.get(POLL, params={"respondent": ME}).json()
    assert mine["answers"] == {first: {"x": 16.12, "y": 19}, second: {"x": 10, "y": 10}} and mine["name"] is None
    # The name given last goes on all of a respondent's answers.
    client.put(f"{POLL}/answers/{second}", json={"respondent": ME, "name": "Sam (U12)", "x": 10, "y": 10})
    assert client.get(POLL, params={"respondent": ME}).json()["name"] == "Sam (U12)"
    assert client.get(POLL, params={"respondent": YOU}).json()["answers"] == {}

    assert client.put(f"{POLL}/answers/nope", json={"respondent": ME, "x": 1, "y": 1}).status_code == 404
    assert client.put(f"{POLL}/answers/{first}", json={"respondent": "short", "x": 1, "y": 1}).status_code == 422
    assert client.put(f"{POLL}/answers/{first}", json={"respondent": ME, "x": 1, "y": 150}).status_code == 422
    assert client.get("/polls/nope").status_code == 404


def test_admins_see_everyone_and_can_take_out_a_test_run(monkeypatch):
    clean_database()
    public = TestClient(app)
    for who, x in ((ME, 15), (YOU, 20)):
        public.put(f"{POLL}/answers/nearest-central", json={"respondent": who, "name": "Sam" if who == ME else None, "x": x, "y": 18})
    coach, _ = signed_in("poll-coach@example.com", monkeypatch)
    assert coach.get(f"{POLL}/results").status_code == 403
    admin, csrf = signed_in("poll-admin@example.com", monkeypatch)
    with SessionLocal() as db:
        db.query(User).filter_by(email="poll-admin@example.com").update({"is_admin": True})
        db.commit()
    results = admin.get(f"{POLL}/results").json()
    assert [r["name"] for r in results["respondents"]] == ["Sam", None]
    assert {a["x"] for a in results["answers"]} == {15, 20} and results["scenarios"][0]["references"]
    assert admin.delete(f"{POLL}/respondents/{YOU}", headers={"x-csrf-token": csrf}).status_code == 204
    assert [r["id"] for r in admin.get(f"{POLL}/results").json()["respondents"]] == [ME]


def test_polls_are_off_unless_switched_on(monkeypatch):
    monkeypatch.setattr(settings, "polls_enabled", False)
    client = TestClient(app)
    assert client.get(POLL).status_code == 404
    assert client.put(f"{POLL}/answers/nearest-central", json={"respondent": ME, "x": 1, "y": 1}).status_code == 404

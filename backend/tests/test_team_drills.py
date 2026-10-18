"""A team's own drills: written in a form, seen only by the team, and used by the planners."""
import json
import tempfile
from pathlib import Path
import pytest
from app.database import SessionLocal
from app.drills import DATA_DIR, DrillError, load_file
from app.models import DrillVariation
from test_flows import clean_database, signed_in

DRILL = {"title": "Four-corner passing", "summary": "Pass and follow round a square.", "session_phase": "technical", "format": "small_group",
         "players": [4, 8, 12], "ages": [8, 14], "duration": [10, 15], "intensity": "medium", "space": [15, 15],
         "equipment": [{"item": "cones", "quantity": 4}, {"item": "balls", "quantity": 2}], "setup": "A 15 m square, a cone at each corner.",
         "instructions": ["Pass to the next corner.", "Follow your pass.", " "], "coaching_points": ["Open your body."],
         "tags": {"passing_short": 1.0, "first_touch": 0.5}, "video_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}


def team(owner, csrf, name):
    return owner.post("/teams", json={"name": name}, headers={"x-csrf-token": csrf}).json()["id"]


def test_coaches_write_their_own_drills_and_only_their_team_sees_them(monkeypatch):
    clean_database()
    owner, csrf = signed_in("team-drills@example.com", monkeypatch)
    other, other_csrf = signed_in("other-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = team(owner, csrf, "Own drills")
    other_team = team(other, other_csrf, "Someone else")

    for bad, words in (({**DRILL, "tags": {}}, "mainly trains"), ({**DRILL, "players": [8, 4, 12]}, "Players:"),
                       ({**DRILL, "video_url": "https://example.com/v"}, "YouTube or Vimeo"), ({**DRILL, "format": "huge"}, "Format must be")):
        refused = owner.post(f"/teams/{team_id}/drills", json=bad, headers=headers)
        assert refused.status_code == 422 and words in refused.text, refused.text
    made = owner.post(f"/teams/{team_id}/drills", json=DRILL, headers=headers)
    assert made.status_code == 201, made.text
    drill = made.json()
    assert drill["slug"] == f"t{team_id}-four-corner-passing" and drill["team_id"] == team_id
    assert drill["instructions"] == ["Pass to the next corner.", "Follow your pass."]
    assert [(v["kind"], v["levels"]) for v in drill["variations"]] == [("base", [1, 5])]
    assert [m["kind"] for m in drill["media"]] == ["video"]
    # A warm-up needn't train a skill.
    assert owner.post(f"/teams/{team_id}/drills", json={**DRILL, "title": "Jog", "session_phase": "warm_up", "tags": {}}, headers=headers).status_code == 201
    again = owner.post(f"/teams/{team_id}/drills", json=DRILL, headers=headers).json()
    assert again["slug"] == f"t{team_id}-four-corner-passing-2"

    slug = drill["slug"]
    assert slug in {d["slug"] for d in owner.get("/drills", params={"team_id": team_id}).json()}
    assert slug not in {d["slug"] for d in owner.get("/drills").json()}, "without a team, only the library"
    assert len(owner.get(f"/teams/{team_id}/drills").json()) == 3
    assert owner.get(f"/drills/{slug}").status_code == 200
    # Another team's coach can't see, vote on, edit or suggest videos for it.
    assert other.get(f"/drills/{slug}").status_code == 404
    assert other.put(f"/drills/{slug}/vote", json={"vote": 1}, headers={"x-csrf-token": other_csrf}).status_code == 404
    assert other.get("/drills", params={"team_id": team_id}).status_code == 404
    assert other.put(f"/teams/{other_team}/drills/{slug}", json=DRILL, headers={"x-csrf-token": other_csrf}).status_code == 404
    assert owner.post(f"/drills/{slug}/video-suggestions", json={"url": "https://www.youtube.com/watch?v=bbbbbbbbbbb"}, headers=headers).status_code == 404
    assert owner.put(f"/drills/{slug}/vote", json={"vote": 1}, headers=headers).status_code == 200

    # Easier and harder versions come and go; each kind keeps its id, so sessions and plans stay pointed at it.
    base_id = drill["variations"][0]["id"]
    both = owner.put(f"/teams/{team_id}/drills/{slug}", json={**DRILL, "easier": {"title": "Two corners", "change": "Pass across a line."},
                                                               "harder": {"title": "One touch", "change": "One touch only."}}, headers=headers).json()
    assert [(v["kind"], v["levels"]) for v in both["variations"]] == [("regression", [1, 2]), ("base", [2, 4]), ("escalator", [4, 5])]
    assert both["variations"][1]["id"] == base_id
    harder_id = both["variations"][2]["id"]
    only_harder = owner.put(f"/teams/{team_id}/drills/{slug}", json={**DRILL, "harder": {"title": "One touch", "change": "One touch only."}}, headers=headers).json()
    assert [(v["id"], v["levels"]) for v in only_harder["variations"]] == [(base_id, [1, 4]), (harder_id, [4, 5])]

    # Deleting retires it: it leaves the lists but isn't removed.
    assert owner.delete(f"/teams/{team_id}/drills/{again['slug']}", headers=headers).json()["message"] == "Drill deleted."
    assert owner.get(f"/drills/{again['slug']}").status_code == 404
    assert len(owner.get(f"/teams/{team_id}/drills").json()) == 2
    actions = [e["action"] for e in owner.get(f"/teams/{team_id}/audit").json()]
    assert actions.count("team_drill_added") == 3 and "team_drill_deleted" in actions

    # The loader never takes over a team drill's slug.
    with SessionLocal() as db:
        path = Path(tempfile.mkdtemp()) / "drills_test.json"
        raw = json.loads((DATA_DIR / "drills_v1.json").read_text())
        row = {**raw["drills"][0], "slug": slug, "links": []}
        path.write_text(json.dumps({"source_version": "test_team_slug", "drills": [row]}))
        try:
            with pytest.raises(DrillError, match="belongs to a team's own drill"):
                load_file(db, path)
        finally:
            path.unlink()

    # Deleting the team deletes its drills.
    owner.request("DELETE", f"/teams/{team_id}", json={"confirm_name": "Own drills"}, headers=headers)
    with SessionLocal() as db:
        assert db.query(DrillVariation).filter_by(id=base_id).first() is None


def test_the_planners_use_the_teams_own_drills():
    from app import plans, sessions
    from test_sessions import data, drill
    own = {**drill("our-rondo", "technical"), "team": True}
    block = next(b for b in sessions.plan(data([own]))["blocks"] if b["phase"] == "technical")
    assert block["drill"] == "our-rondo" and "Your team's own drill." in block["reasons"]
    choice = plans.assess({"rank": 1, "skill_id": "p", "label": "P", "level": 3, "tags": {"passing_short": 1.0}}, "club", {**own, "home_friendly": False}, {})
    assert "your team's own drill" in choice["notes"]


def test_submitting_a_drill_to_the_library(monkeypatch):
    clean_database()
    owner, csrf = signed_in("submit-drill@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = team(owner, csrf, "Submitters")
    slug = owner.post(f"/teams/{team_id}/drills", json=DRILL, headers=headers).json()["slug"]
    assert owner.post(f"/teams/{team_id}/drills/{slug}/submit", json={"confirm_own": False}, headers=headers).status_code == 422
    submitted = owner.post(f"/teams/{team_id}/drills/{slug}/submit", json={"confirm_own": True, "note": "Works well with U10s"}, headers=headers)
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["submission"]["status"] == "pending"
    assert owner.post(f"/teams/{team_id}/drills/{slug}/submit", json={"confirm_own": True}, headers=headers).status_code == 409


def test_an_admin_accepts_a_drill_for_the_library_and_a_data_file_publishes_it(monkeypatch):
    from app.drills import drill_problems
    from app.models import SkillTag, User
    clean_database()
    owner, csrf = signed_in("offer-drill@example.com", monkeypatch)
    admin, admin_csrf = signed_in("drill-admin@example.com", monkeypatch)
    with SessionLocal() as db:
        db.query(User).filter_by(email="drill-admin@example.com").update({"is_admin": True})
        db.commit()
    headers, admin_headers = {"x-csrf-token": csrf}, {"x-csrf-token": admin_csrf}
    team_id = team(owner, csrf, "Offering")
    first = owner.post(f"/teams/{team_id}/drills", json={**DRILL, "harder": {"title": "One touch", "change": "One touch only."}}, headers=headers).json()["slug"]
    second = owner.post(f"/teams/{team_id}/drills", json={**DRILL, "title": "Gate dribbling"}, headers=headers).json()["slug"]
    for slug in (first, second):
        owner.post(f"/teams/{team_id}/drills/{slug}/submit", json={"confirm_own": True, "note": "Try it"}, headers=headers)

    assert owner.get("/admin/drill-submissions").status_code == 403
    queue = admin.get("/admin/drill-submissions").json()
    assert [q["drill"]["title"] for q in queue] == ["Four-corner passing", "Gate dribbling"] and queue[0]["team"] == "Offering"
    one, two = queue
    assert admin.get(f"/admin/drill-submissions/{one['id']}/row").status_code == 409  # accept first
    assert admin.post(f"/admin/drill-submissions/{one['id']}/accept", json={"library_slug": "t5-x"}, headers=admin_headers).status_code == 422
    accepted = admin.post(f"/admin/drill-submissions/{one['id']}/accept", json={}, headers=admin_headers).json()
    assert accepted["status"] == "accepted" and accepted["library_slug"] == "four-corner-passing"
    assert admin.post(f"/admin/drill-submissions/{two['id']}/accept", json={"library_slug": "four-corner-passing"}, headers=admin_headers).status_code == 409
    declined = admin.post(f"/admin/drill-submissions/{two['id']}/decline", json={"reason": "Very like Dribble gates"}, headers=admin_headers).json()
    assert declined["status"] == "declined"
    assert owner.get(f"/drills/{second}").json()["submission"] == {**owner.get(f"/drills/{second}").json()["submission"], "status": "declined", "reason": "Very like Dribble gates"}
    assert owner.get(f"/drills/{first}").json()["submission"]["status"] == "accepted"
    # Not in anyone else's library until a data file publishes it.
    assert "four-corner-passing" not in {d["slug"] for d in admin.get("/drills").json()}

    row = admin.get(f"/admin/drill-submissions/{one['id']}/row").json()
    assert row["slug"] == "four-corner-passing" and [v["kind"] for v in row["variations"]] == ["base", "escalator"]
    with SessionLocal() as db:
        assert drill_problems(row, {t.id for t in db.query(SkillTag).filter_by(active=True)}) == [], "the row loads as it is"
        path = Path(tempfile.mkdtemp()) / "drills_test.json"
        path.write_text(json.dumps({"source_version": "test_accepted", "drills": [row]}))
        load_file(db, path)
    mine = owner.get(f"/drills/{first}").json()["submission"]
    assert mine["status"] == "published" and mine["library"] == {"slug": "four-corner-passing", "title": "Four-corner passing"}
    assert "four-corner-passing" in {d["slug"] for d in admin.get("/drills").json()}

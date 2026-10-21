"""Coaches reporting a drill's video or link, and site admins hiding or keeping it."""
import pytest
from app import video_links
from app.database import SessionLocal
from app.drills import DATA_DIR, load_file
from app.models import DrillVideoSuggestion, User
from test_flows import clean_database, signed_in

VIDEO = "https://www.youtube.com/watch?v=c_nq0Ka_RWs"
REPORT = "/drills/rondo-4v1/link-reports"


@pytest.fixture
def library():
    clean_database()
    with SessionLocal() as db:
        load_file(db, DATA_DIR / "drills_v1.json")


def urls(client):
    drill = client.get("/drills/rondo-4v1").json()
    return [m["url"] for m in drill["media"] if m["kind"] != "diagram"] + [v["url"] for v in drill["suggested_videos"]]


def test_a_reported_link_is_hidden_or_kept_by_a_site_admin(monkeypatch, library, admin_emails):
    admin, admin_csrf = signed_in("link-admin@example.com", monkeypatch)
    with SessionLocal() as db:
        db.query(User).filter_by(email="link-admin@example.com").update({"is_admin": True})
        db.commit()
    coach, csrf = signed_in("link-coach@example.com", monkeypatch)
    other, other_csrf = signed_in("link-other@example.com", monkeypatch)
    report = lambda client, token, body: client.post(REPORT, json=body, headers={"x-csrf-token": token})
    queue = lambda status="open": admin.get("/admin/link-reports", params={"status": status}).json()
    act = lambda item, action: admin.post(f"/admin/link-reports/{item['id']}/{action}", headers={"x-csrf-token": admin_csrf})
    assert VIDEO in urls(coach)

    made = report(coach, csrf, {"url": VIDEO, "reason": "dead", "note": " Says unavailable "})
    assert made.status_code == 201, made.text
    to, subject, body = admin_emails[-1]
    assert (to, subject) == ("link-admin@example.com", "Link reported on 4v1 rondo")
    assert "link-coach@example.com says a link on 4v1 rondo doesn't work" in body and VIDEO in body and "Says unavailable" in body

    # A second report of the same link joins the first, without another email.
    assert report(coach, csrf, {"url": VIDEO, "reason": "dead"}).status_code == 409
    assert report(other, other_csrf, {"url": VIDEO, "reason": "inappropriate"}).status_code == 201
    assert [s for _, s, _ in admin_emails if s.startswith("Link")] == ["Link reported on 4v1 rondo"]
    assert report(coach, csrf, {"url": "https://example.com/not-here", "reason": "dead"}).status_code == 404
    assert report(coach, csrf, {"url": VIDEO, "reason": "boring"}).status_code == 422

    [item] = queue()
    assert (item["drill_title"], item["url"], item["kind"], item["suggested"], item["status"]) == ("4v1 rondo", VIDEO, "video", False, "open")
    assert [(r["reason"], r["note"], r["reported_by"]) for r in item["reports"]] == [
        ("dead", "Says unavailable", "link-coach@example.com"), ("inappropriate", "", "link-other@example.com")]

    # Hidden for everyone, and it stays hidden when the data file is loaded again.
    assert act(item, "hide").json()["status"] == "hidden"
    assert queue() == [] and [i["url"] for i in queue("hidden")] == [VIDEO]
    assert VIDEO not in urls(coach)
    with SessionLocal() as db:
        load_file(db, DATA_DIR / "drills_v1.json")
    assert VIDEO not in urls(other)
    assert report(coach, csrf, {"url": VIDEO, "reason": "dead"}).status_code == 404
    assert act(item, "hide").status_code == 409

    # Putting it back, and keeping a link that's fine.
    assert act(queue("hidden")[0], "restore").status_code == 200
    assert VIDEO in urls(coach) and queue("hidden") == []
    report(coach, csrf, {"url": VIDEO, "reason": "other", "note": "Wrong drill?"})
    assert act(queue()[0], "keep").json()["status"] == "dismissed"
    assert queue() == [] and VIDEO in urls(coach)


def test_hiding_a_suggested_video_marks_the_suggestion(monkeypatch, library, admin_emails):
    monkeypatch.setattr(video_links, "lookup", lambda link: video_links.VideoDetails("A rondo", "A channel", None))
    admin, admin_csrf = signed_in("link-admin2@example.com", monkeypatch)
    with SessionLocal() as db:
        db.query(User).filter_by(email="link-admin2@example.com").update({"is_admin": True})
        db.commit()
    headers = {"x-csrf-token": admin_csrf}
    sid = admin.post("/drills/rondo-4v1/video-suggestions", json={"url": "https://youtu.be/abcdefghijk"}, headers=headers).json()["id"]
    admin.post(f"/admin/video-suggestions/{sid}/approve", json={"caption": "Another rondo"}, headers=headers)
    coach, csrf = signed_in("link-coach2@example.com", monkeypatch)
    suggested = "https://www.youtube.com/watch?v=abcdefghijk"
    assert coach.post(REPORT, json={"url": suggested, "reason": "inappropriate"}, headers={"x-csrf-token": csrf}).status_code == 201

    [item] = admin.get("/admin/link-reports").json()
    assert (item["suggested"], item["caption"]) == (True, "Another rondo")
    admin.post(f"/admin/link-reports/{item['id']}/hide", headers=headers)
    with SessionLocal() as db:
        assert (db.get(DrillVideoSuggestion, sid).status, db.get(DrillVideoSuggestion, sid).reports) == ("hidden", 1)
    assert suggested not in urls(coach)
    admin.post(f"/admin/link-reports/{item['id']}/restore", headers=headers)
    assert suggested in urls(coach)


def test_team_drills_links_are_the_teams_to_change(monkeypatch, library):
    coach, csrf = signed_in("link-team@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = coach.post("/teams", json={"name": "Link FC"}, headers=headers).json()["id"]
    drill = {"title": "Passing square", "session_phase": "technical", "format": "small_group", "players": [4, 8, 12], "ages": [8, 14],
             "duration": [10, 15], "intensity": "medium", "setup": "A square.", "instructions": ["Pass."], "tags": {"passing_short": 1.0},
             "video_url": "https://www.youtube.com/watch?v=abcdefghijk"}
    made = coach.post(f"/teams/{team_id}/drills", json=drill, headers=headers)
    assert made.status_code == 201, made.text
    response = coach.post(f"/drills/{made.json()['slug']}/link-reports", json={"url": drill["video_url"], "reason": "dead"}, headers=headers)
    assert response.status_code == 422

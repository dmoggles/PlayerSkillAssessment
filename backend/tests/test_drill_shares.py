"""Sharing one drill, read-only and for a limited time, with a coach who isn't on the platform."""
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.database import SessionLocal, engine
from app.drills import DATA_DIR, load_file
from app.main import app
from test_flows import add_coach, clean_database, signed_in
from test_team_drills import DRILL, team


def token_of(share):
    return share["url"].split("/")[-1]


def test_a_shared_drill_opens_read_only_until_it_expires_or_is_revoked(monkeypatch):
    clean_database()
    with SessionLocal() as db:
        load_file(db, DATA_DIR / "drills_v1.json")
    coach, csrf = signed_in("share-drill@example.com", monkeypatch)
    other, other_csrf = signed_in("share-drill-other@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    slug = "rondo-4v1"
    coach.put(f"/drills/{slug}/vote", json={"vote": 1}, headers=headers)

    assert coach.post(f"/drills/{slug}/shares", json={"days": 3}, headers=headers).status_code == 422
    share = coach.post(f"/drills/{slug}/shares", json={"days": 7}, headers=headers).json()
    assert share["url"].startswith("http://testserver/drill/") and share["opened_at"] is None
    public = TestClient(app)
    opened = public.get(f"/shared-drills/{token_of(share)}")
    assert opened.status_code == 200, opened.text
    drill = opened.json()
    # The drill in full, with nothing that changes anything or leads elsewhere.
    assert drill["slug"] == slug and drill["variations"] and drill["instructions"]
    assert drill["votes"] is None and drill["links"] == [] and drill["team_versions"] == [] and drill["submission"] is None
    assert public.put(f"/drills/{slug}/vote", json={"vote": 1}).status_code == 401
    assert public.get("/shared-drills/not-a-real-token").status_code == 404

    # The coach sees their own open links, and when one was first opened; another coach sees none of them.
    mine = coach.get(f"/drills/{slug}/shares").json()
    assert [s["id"] for s in mine] == [share["id"]] and mine[0]["opened_at"] is not None and "url" not in mine[0]
    assert other.get(f"/drills/{slug}/shares").json() == []
    assert other.delete(f"/drills/{slug}/shares/{share['id']}", headers={"x-csrf-token": other_csrf}).status_code == 404

    with engine.begin() as conn:
        conn.execute(text("UPDATE drill_shares SET expires_at = now() - interval '1 minute'"))
    assert public.get(f"/shared-drills/{token_of(share)}").status_code == 410
    assert coach.get(f"/drills/{slug}/shares").json() == [], "expired links aren't listed"

    fresh = coach.post(f"/drills/{slug}/shares", json={"days": 1}, headers=headers).json()
    assert coach.delete(f"/drills/{slug}/shares/{fresh['id']}", headers=headers).status_code == 204
    assert public.get(f"/shared-drills/{token_of(fresh)}").status_code == 404

    # Deleting the account closes its links.
    last = coach.post(f"/drills/{slug}/shares", json={"days": 30}, headers=headers).json()
    assert coach.post("/auth/delete-account", json={"password": "secure-password-123"}, headers=headers).status_code == 200
    assert public.get(f"/shared-drills/{token_of(last)}").status_code == 404


def test_a_team_drill_link_closes_when_the_drill_or_the_coach_leaves(monkeypatch):
    clean_database()
    owner, csrf = signed_in("share-team-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("share-team-coach@example.com", monkeypatch)
    outsider, outsider_csrf = signed_in("share-team-outsider@example.com", monkeypatch)
    headers, coach_headers = {"x-csrf-token": csrf}, {"x-csrf-token": coach_csrf}
    team_id = team(owner, csrf, "Sharers")
    coach_id = add_coach(owner, csrf, team_id, coach, coach_csrf, "share-team-coach@example.com", monkeypatch)
    slug = owner.post(f"/teams/{team_id}/drills", json=DRILL, headers=headers).json()["slug"]

    # Only the team's coaches can share it.
    assert outsider.post(f"/drills/{slug}/shares", json={"days": 7}, headers={"x-csrf-token": outsider_csrf}).status_code == 404
    share = coach.post(f"/drills/{slug}/shares", json={"days": 7}, headers=coach_headers).json()
    public = TestClient(app)
    drill = public.get(f"/shared-drills/{token_of(share)}").json()
    assert drill["title"] == DRILL["title"] and drill["team_id"] is None and drill["shadows"] is None
    actions = [e["action"] for e in owner.get(f"/teams/{team_id}/audit").json()]
    assert "team_drill_shared" in actions

    # The coach who shared it leaves the team: the link closes.
    assert owner.delete(f"/teams/{team_id}/members/{coach_id}", headers=headers).status_code == 200
    assert public.get(f"/shared-drills/{token_of(share)}").status_code == 404

    # The drill is deleted: the link closes.
    own = owner.post(f"/drills/{slug}/shares", json={"days": 7}, headers=headers).json()
    assert public.get(f"/shared-drills/{token_of(own)}").status_code == 200
    owner.delete(f"/teams/{team_id}/drills/{slug}", headers=headers)
    assert public.get(f"/shared-drills/{token_of(own)}").status_code == 404

    # Deleting the team removes its drills and their links.
    owner.request("DELETE", f"/teams/{team_id}", json={"confirm_name": "Sharers"}, headers=headers)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM drill_shares")).scalar() == 0

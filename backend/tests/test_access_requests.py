"""Clubs asking for access from the public site, and site admins answering."""
import re
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import AccessRequest, User
from app.routers import access_requests, admin as admin_routes
from test_flows import clean_database, signed_in

BODY = {"name": "Sam Coach", "email": "Sam@Example.com", "club": "Riverside Juniors", "teams": 4, "message": "Two girls' teams too"}


def test_clubs_request_access_and_admins_invite_or_decline(monkeypatch):
    clean_database()
    admin, csrf = signed_in("access-admin@example.com", monkeypatch)
    with SessionLocal() as db:
        db.query(User).filter_by(email="access-admin@example.com").update({"is_admin": True})
        db.commit()
    sent = []
    monkeypatch.setattr(access_requests, "send_email", lambda to, subject, body: sent.append((to, subject)))
    monkeypatch.setattr(admin_routes, "send_email", lambda to, subject, body: sent.append((to, body)))
    public = TestClient(app)

    made = public.post("/access-requests", json=BODY)
    assert made.status_code == 201 and made.json()["message"].startswith("Thanks")
    assert sent == [("access-admin@example.com", "Access request from Riverside Juniors")]
    # Asking again updates the waiting request rather than adding another; a bot filling the hidden field is ignored.
    assert public.post("/access-requests", json={**BODY, "club": "Riverside Juniors FC", "message": ""}).status_code == 201
    assert public.post("/access-requests", json={**BODY, "email": "bot@example.com", "website": "http://spam"}).json()["message"].startswith("Thanks")
    assert public.post("/access-requests", json={**BODY, "email": "not an email"}).status_code == 422
    with SessionLocal() as db:
        rows = db.query(AccessRequest).all()
        assert [(r.email, r.club, r.message) for r in rows] == [("sam@example.com", "Riverside Juniors FC", "Two girls' teams too")]

    headers = {"x-csrf-token": csrf}
    waiting = admin.get("/admin/access-requests").json()
    assert [(w["name"], w["email"], w["teams"], w["status"], w["has_account"]) for w in waiting] == [("Sam Coach", "sam@example.com", 4, "pending", False)]
    invite = admin.post(f"/admin/access-requests/{waiting[0]['id']}/invite", headers=headers)
    assert invite.status_code == 200 and invite.json()["email"] == "sam@example.com" and invite.json()["emailed"] is True
    assert re.search(r"/invite/\S+", sent[-1][1])
    assert admin.post(f"/admin/access-requests/{waiting[0]['id']}/invite", headers=headers).status_code == 409
    assert admin.get("/admin/access-requests").json() == []
    assert [r["email"] for r in admin.get("/admin/access-requests", params={"status": "invited"}).json()] == ["sam@example.com"]

    # Someone who already has an account: the admin sees that, and declines instead.
    public.post("/access-requests", json={**BODY, "email": "access-admin@example.com"})
    other = admin.get("/admin/access-requests").json()[0]
    assert other["has_account"] is True
    assert admin.post(f"/admin/access-requests/{other['id']}/invite", headers=headers).status_code == 409
    assert admin.post(f"/admin/access-requests/{other['id']}/decline", headers=headers).json()["message"] == "Declined the request from Riverside Juniors."

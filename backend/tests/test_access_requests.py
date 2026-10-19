"""Clubs asking for access from the public site, and site admins answering."""
import re
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import AccessRequest, User
from app.routers import admin as admin_routes
from test_flows import clean_database, signed_in

BODY = {"name": "Sam Coach", "email": "Sam@Example.com", "club": "Riverside Juniors", "teams": 4, "message": "Two girls' teams too"}


def test_clubs_request_access_and_admins_invite_or_decline(monkeypatch, admin_emails):
    clean_database()
    admin, csrf = signed_in("access-admin@example.com", monkeypatch)
    with SessionLocal() as db:
        db.query(User).filter_by(email="access-admin@example.com").update({"is_admin": True})
        db.commit()
    sent = []
    monkeypatch.setattr(admin_routes, "send_email", lambda to, subject, body: sent.append((to, body)))
    public = TestClient(app)

    made = public.post("/access-requests", json=BODY)
    assert made.status_code == 201 and made.json()["message"].startswith("Thanks")
    [(to, subject, text)] = admin_emails
    assert (to, subject) == ("access-admin@example.com", "Access request from Riverside Juniors")
    assert "Sam Coach (sam@example.com)" in text and "Teams: 4" in text and "Two girls' teams too" in text and "/app/settings" in text
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
    token = re.search(r"/invite/(\S+)", sent[-1][1]).group(1)
    # Once they've made their account from it, admins hear they're in.
    assert public.post("/auth/register", json={"email": "sam@example.com", "password": "secure-password-123", "invite": token}).status_code == 201
    to, subject, text = admin_emails[-1]
    assert subject == "New TapLine IDP account: sam@example.com"
    assert text.startswith("Sam Coach (sam@example.com) from Riverside Juniors FC has created their TapLine IDP account.")
    assert admin.post(f"/admin/access-requests/{waiting[0]['id']}/invite", headers=headers).status_code == 409
    assert admin.get("/admin/access-requests").json() == []
    assert [(r["email"], r["has_account"]) for r in admin.get("/admin/access-requests", params={"status": "invited"}).json()] == [("sam@example.com", True)]

    # Someone who already has an account: the admin sees that, and declines instead.
    public.post("/access-requests", json={**BODY, "email": "access-admin@example.com"})
    other = admin.get("/admin/access-requests").json()[0]
    assert other["has_account"] is True
    assert admin.post(f"/admin/access-requests/{other['id']}/invite", headers=headers).status_code == 409
    assert admin.post(f"/admin/access-requests/{other['id']}/decline", headers=headers).json()["message"] == "Declined the request from Riverside Juniors."


def test_admins_hear_about_new_accounts_they_let_in(monkeypatch, admin_emails):
    clean_database()
    signed_in("first-admin@example.com", monkeypatch)
    with SessionLocal() as db:
        db.query(User).filter_by(email="first-admin@example.com").update({"is_admin": True})
        db.commit()
    admin_emails.clear()
    # Open sign-up: once the address is verified, not before.
    from app.routers import accounts
    messages = []
    monkeypatch.setattr(accounts, "send_email", lambda to, subject, body: messages.append(body))
    client = TestClient(app)
    assert client.post("/auth/register", json={"email": "open@example.com", "password": "secure-password-123"}).status_code == 201
    assert admin_emails == []
    token = re.search(r"/verify/(\S+)", messages[-1]).group(1)
    assert client.post("/auth/verify", json={"token": token}).status_code == 200
    assert [(to, subject) for to, subject, _ in admin_emails] == [("first-admin@example.com", "New TapLine IDP account: open@example.com")]
    assert admin_emails[0][2].startswith("open@example.com has created their TapLine IDP account.")

    # A coach a team invited is the team's business, not the site admins'.
    admin_emails.clear()
    owner, csrf = signed_in("owner@example.com", monkeypatch)
    admin_emails.clear()
    from app.routers import teams
    invites = []
    monkeypatch.setattr(teams, "send_email", lambda to, subject, body: invites.append(body))
    team_id = owner.post("/teams", json={"name": "North"}, headers={"x-csrf-token": csrf}).json()["id"]
    owner.post(f"/teams/{team_id}/invites", json={"email": "team-coach@example.com"}, headers={"x-csrf-token": csrf})
    invite = re.search(r"/invite/(\S+)", invites[-1]).group(1)
    assert TestClient(app).post("/auth/register", json={"email": "team-coach@example.com", "password": "secure-password-123", "invite": invite}).status_code == 201
    # Signing up without the link, then verifying, is still a team invitation.
    owner.post(f"/teams/{team_id}/invites", json={"email": "no-link@example.com"}, headers={"x-csrf-token": csrf})
    monkeypatch.setattr(accounts, "send_email", lambda to, subject, body: messages.append(body))
    no_link = TestClient(app)
    assert no_link.post("/auth/register", json={"email": "no-link@example.com", "password": "secure-password-123"}).status_code == 201
    assert no_link.post("/auth/verify", json={"token": re.search(r"/verify/(\S+)", messages[-1]).group(1)}).status_code == 200
    assert admin_emails == []

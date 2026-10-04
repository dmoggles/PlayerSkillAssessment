from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app
from app.routers import accounts, assessments, teams


def clean_database():
    if not engine.url.database or not engine.url.database.endswith("_test"):
        raise RuntimeError("Refusing to clear a database without a _test suffix")
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


def signed_in(email, monkeypatch):
    messages = []
    monkeypatch.setattr(accounts, "send_email", lambda to, subject, body: messages.append(body))
    client = TestClient(app)
    assert client.post("/auth/register", json={"email": email, "password": "secure-password-123"}).status_code == 201
    token = messages[-1].split("/")[-1]
    assert client.post("/auth/verify", json={"token": token}).status_code == 200
    response = client.post("/auth/login", json={"email": email, "password": "secure-password-123"})
    assert response.status_code == 200
    return client, response.json()["csrf_token"]


def test_team_isolation_invite_and_role(monkeypatch):
    clean_database()
    owner, csrf = signed_in("owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "North"}, headers=headers).json()["id"]
    other_id = owner.post("/teams", json={"name": "South"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Alex"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    assert coach.get(f"/teams/{team_id}/players").status_code == 404
    assert owner.get(f"/teams/{other_id}/assessments/compare", params={"player_id": player_id, "period_id": period_id}).status_code == 404
    invites = []
    monkeypatch.setattr(teams, "send_email", lambda to, subject, body: invites.append(body))
    assert owner.post(f"/teams/{team_id}/invites", json={"email": "coach@example.com"}, headers=headers).status_code == 200
    token = invites[-1].split("/")[-1]
    assert coach.post("/invites/accept", json={"token": token}, headers={"x-csrf-token": coach_csrf}).status_code == 200
    assert len(coach.get(f"/teams/{team_id}/players").json()) == 1
    assert coach.patch(f"/teams/{team_id}", json={"name": "Changed", "self_assessment_enabled": True}, headers={"x-csrf-token": coach_csrf}).status_code == 404
    assert coach.get(f"/teams/{other_id}/players").status_code == 404
    coach_user_id = next(m["user_id"] for m in owner.get(f"/teams/{team_id}/members").json() if m["role"] == "coach")
    assert owner.delete(f"/teams/{team_id}/members/{coach_user_id}", headers=headers).status_code == 200
    assert coach.get(f"/teams/{team_id}/players").status_code == 404


def add_coach(owner, owner_csrf, team_id, coach, coach_csrf, email, monkeypatch):
    invites = []
    monkeypatch.setattr(teams, "send_email", lambda to, subject, body: invites.append(body))
    assert owner.post(f"/teams/{team_id}/invites", json={"email": email}, headers={"x-csrf-token": owner_csrf}).status_code == 200
    assert coach.post("/invites/accept", json={"token": invites[-1].split("/")[-1]}, headers={"x-csrf-token": coach_csrf}).status_code == 200
    return next(m["user_id"] for m in owner.get(f"/teams/{team_id}/members").json() if m["email"] == email)


def test_member_roles_keep_at_least_one_owner(monkeypatch):
    clean_database()
    owner, csrf = signed_in("roles-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("roles-coach@example.com", monkeypatch)
    headers, coach_headers = {"x-csrf-token": csrf}, {"x-csrf-token": coach_csrf}
    team_id = owner.post("/teams", json={"name": "Roles"}, headers=headers).json()["id"]
    owner_id = owner.get(f"/teams/{team_id}/members").json()[0]["user_id"]
    coach_id = add_coach(owner, csrf, team_id, coach, coach_csrf, "roles-coach@example.com", monkeypatch)
    assert coach.patch(f"/teams/{team_id}/members/{coach_id}", json={"role": "owner"}, headers=coach_headers).status_code == 404
    assert coach.delete(f"/teams/{team_id}/members/{owner_id}", headers=coach_headers).status_code == 404
    # A coach can leave on their own, then be invited back.
    assert coach.delete(f"/teams/{team_id}/members/{coach_id}", headers=coach_headers).status_code == 200
    assert coach.get("/teams").json() == []
    coach_id = add_coach(owner, csrf, team_id, coach, coach_csrf, "roles-coach@example.com", monkeypatch)
    assert owner.patch(f"/teams/{team_id}/members/{owner_id}", json={"role": "coach"}, headers=headers).status_code == 409
    assert owner.delete(f"/teams/{team_id}/members/{owner_id}", headers=headers).status_code == 409
    assert owner.patch(f"/teams/{team_id}/members/{coach_id}", json={"role": "admin"}, headers=headers).status_code == 422
    # Transfer ownership: promote the coach, then step down.
    assert owner.patch(f"/teams/{team_id}/members/{coach_id}", json={"role": "owner"}, headers=headers).json()["role"] == "owner"
    assert owner.patch(f"/teams/{team_id}/members/{owner_id}", json={"role": "coach"}, headers=headers).status_code == 200
    assert owner.patch(f"/teams/{team_id}", json={"name": "Taken", "self_assessment_enabled": False}, headers=headers).status_code == 404
    assert {t["role"] for t in coach.get("/teams").json()} == {"owner"}
    assert coach.delete(f"/teams/{team_id}/members/{owner_id}", headers=coach_headers).status_code == 200
    assert owner.get(f"/teams/{team_id}/players").status_code == 404


def test_restore_players_and_manage_periods(monkeypatch):
    clean_database()
    owner, csrf = signed_in("periods-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("periods-coach@example.com", monkeypatch)
    headers, coach_headers = {"x-csrf-token": csrf}, {"x-csrf-token": coach_csrf}
    team_id = owner.post("/teams", json={"name": "Periods"}, headers=headers).json()["id"]
    add_coach(owner, csrf, team_id, coach, coach_csrf, "periods-coach@example.com", monkeypatch)
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Kai"}, headers=headers).json()["id"]

    autumn = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    winter = owner.post(f"/teams/{team_id}/periods", json={"label": "Winter"}, headers=headers).json()["id"]
    assert coach.patch(f"/teams/{team_id}/periods/{winter}", json={"label": "Autumn"}, headers=coach_headers).status_code == 409
    assert coach.patch(f"/teams/{team_id}/periods/{winter}", json={"label": "  "}, headers=coach_headers).status_code == 422
    assert coach.patch(f"/teams/{team_id}/periods/{winter}", json={"label": "Winter term"}, headers=coach_headers).json()["label"] == "Winter term"

    body = {"player_id": player_id, "period_id": winter, "version": 0, "primary_position": "defender",
            "ratings": [{"skill_id": "first_touch_body_shape", "score": 3}]}
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200
    assert coach.delete(f"/teams/{team_id}/periods/{winter}", headers=coach_headers).status_code == 404
    assert owner.delete(f"/teams/{team_id}/periods/{winter}", headers=headers).status_code == 200
    periods = owner.get(f"/teams/{team_id}/periods").json()
    assert [(p["id"], p["is_active"]) for p in periods] == [(autumn, True)]
    assert owner.get(f"/teams/{team_id}/players/{player_id}/history").json() == []


def test_archived_players_are_read_only_until_restored(monkeypatch):
    clean_database()
    owner, csrf = signed_in("archive-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("archive-coach@example.com", monkeypatch)
    headers, coach_headers = {"x-csrf-token": csrf}, {"x-csrf-token": coach_csrf}
    team_id = owner.post("/teams", json={"name": "Archive"}, headers=headers).json()["id"]
    add_coach(owner, csrf, team_id, coach, coach_csrf, "archive-coach@example.com", monkeypatch)
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Kai"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    skill_ids = sorted(assessments.SKILLS["outfield"])
    body = {"player_id": player_id, "period_id": period_id, "version": 0, "primary_position": "defender",
            "ratings": [{"skill_id": skill_id, "score": 3} for skill_id in skill_ids]}
    priority_params = {"player_id": player_id, "period_id": period_id}
    priorities = {"priorities": [{"skill_id": skill_ids[0], "rank": 1}]}
    saved = owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).json()
    assert owner.put(f"/teams/{team_id}/priorities", params=priority_params, json=priorities, headers=headers).status_code == 200

    assert coach.post(f"/teams/{team_id}/players/{player_id}/archive", headers=coach_headers).json()["active"] is False
    body["version"] = saved["version"]
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 409
    assert owner.put(f"/teams/{team_id}/priorities", params=priority_params, json={"priorities": []}, headers=headers).status_code == 409
    # History stays readable while archived.
    assert owner.get(f"/teams/{team_id}/assessments/coach", params=priority_params).json()["version"] == saved["version"]
    assert len(owner.get(f"/teams/{team_id}/priorities", params=priority_params).json()) == 1
    assert len(owner.get(f"/teams/{team_id}/players/{player_id}/history").json()) == 1

    assert coach.post(f"/teams/{team_id}/players/{player_id}/restore", headers=coach_headers).json()["active"] is True
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200


def test_delete_team_requires_owner_and_exact_name(monkeypatch):
    clean_database()
    owner, csrf = signed_in("delete-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("delete-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Doomed"}, headers=headers).json()["id"]
    keep_id = owner.post("/teams", json={"name": "Kept"}, headers=headers).json()["id"]
    add_coach(owner, csrf, team_id, coach, coach_csrf, "delete-coach@example.com", monkeypatch)
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Lee"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    skill_ids = sorted(assessments.SKILLS["outfield"])
    body = {"player_id": player_id, "period_id": period_id, "version": 0, "primary_position": "defender",
            "ratings": [{"skill_id": skill_id, "score": 3} for skill_id in skill_ids]}
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200
    owner.patch(f"/teams/{team_id}", json={"name": "Doomed", "self_assessment_enabled": True}, headers=headers)
    assert owner.post(f"/teams/{team_id}/players/{player_id}/periods/{period_id}/self-link", headers=headers).status_code == 200
    assert owner.put(f"/teams/{team_id}/priorities", params={"player_id": player_id, "period_id": period_id},
                     json={"priorities": [{"skill_id": skill_ids[0], "rank": 1}]}, headers=headers).status_code == 200

    assert coach.request("DELETE", f"/teams/{team_id}", json={"confirm_name": "Doomed"}, headers={"x-csrf-token": coach_csrf}).status_code == 404
    assert owner.request("DELETE", f"/teams/{team_id}", json={"confirm_name": "doomed"}, headers=headers).status_code == 422
    assert owner.request("DELETE", f"/teams/{team_id}", json={"confirm_name": "Doomed"}, headers=headers).status_code == 200
    assert [t["id"] for t in owner.get("/teams").json()] == [keep_id]
    assert coach.get("/teams").json() == []
    assert owner.get(f"/teams/{team_id}/players").status_code == 404


def test_assessment_versions_history_and_self_link(monkeypatch):
    clean_database()
    owner, csrf = signed_in("owner2@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "West"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Sam"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    body = {"player_id": player_id, "period_id": period_id, "version": 0, "primary_position": "defender", "ratings": [{"skill_id": "first_touch_body_shape", "score": 3}]}
    first = owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 409
    body["version"] = 1
    body["ratings"][0]["score"] = 4
    second = owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2
    assert len(owner.get(f"/teams/{team_id}/assessments/{first.json()['id']}/revisions").json()) == 2
    period_2 = owner.post(f"/teams/{team_id}/periods", json={"label": "Winter"}, headers=headers).json()["id"]
    history = owner.get(f"/teams/{team_id}/players/{player_id}/history").json()
    assert history[0]["assessments"]["coach"]["ratings"][0]["score"] == 4
    assert len(history) == 1
    assert owner.post(f"/teams/{team_id}/players/{player_id}/periods/{period_2}/self-link", headers=headers).status_code == 409
    owner.patch(f"/teams/{team_id}", json={"name": "West", "self_assessment_enabled": True}, headers=headers)
    link = owner.post(f"/teams/{team_id}/players/{player_id}/periods/{period_2}/self-link", headers=headers)
    assert link.status_code == 200, link.text
    token = link.json()["url"].split("/")[-1]
    public = TestClient(app)
    assert public.get(f"/self/{token}").json()["player"] == "Sam"
    owner.patch(f"/teams/{team_id}", json={"name": "West", "self_assessment_enabled": False}, headers=headers)
    assert public.get(f"/self/{token}").status_code == 404
    owner.patch(f"/teams/{team_id}", json={"name": "West", "self_assessment_enabled": True}, headers=headers)
    token = owner.post(f"/teams/{team_id}/players/{player_id}/periods/{period_2}/self-link", headers=headers).json()["url"].split("/")[-1]
    submitted = public.post(f"/self/{token}", json={"position": "outfield", "ratings": [{"skill_id": "first_touch_body_shape", "score": 2}]})
    assert submitted.status_code == 201, submitted.text
    assert public.post(f"/self/{token}", json={"position": "outfield", "ratings": []}).status_code == 410


def test_session_csrf_and_password_reset(monkeypatch):
    clean_database()
    client, csrf = signed_in("reset@example.com", monkeypatch)
    assert client.post("/teams", json={"name": "Team"}).status_code == 403
    assert client.post("/teams", json={"name": "Team"}, headers={"x-csrf-token": csrf, "origin": "https://other.example"}).status_code == 403
    assert client.post("/teams", json={"name": "Team"}, headers={"x-csrf-token": csrf}).status_code == 201
    messages = []
    monkeypatch.setattr(accounts, "send_email", lambda to, subject, body: messages.append(body))
    assert client.post("/auth/forgot-password", json={"email": "reset@example.com"}).status_code == 200
    assert client.post("/auth/forgot-password", json={"email": "reset@example.com"}).status_code == 200
    older_token = messages[-2].split("/")[-1]
    token = messages[-1].split("/")[-1]
    assert client.post("/auth/reset-password", json={"token": token, "password": "new-secure-password"}).status_code == 200
    assert client.post("/auth/reset-password", json={"token": older_token, "password": "another-password-123"}).status_code == 400
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": "reset@example.com", "password": "new-secure-password"}).status_code == 200


def test_owner_and_coach_can_change_own_password(monkeypatch):
    clean_database()
    owner, owner_csrf = signed_in("owner-password@example.com", monkeypatch)
    coach, coach_csrf = signed_in("coach-password@example.com", monkeypatch)
    team_id = owner.post("/teams", json={"name": "Password team"}, headers={"x-csrf-token": owner_csrf}).json()["id"]
    invites = []
    monkeypatch.setattr(teams, "send_email", lambda to, subject, body: invites.append(body))
    assert owner.post(f"/teams/{team_id}/invites", json={"email": "coach-password@example.com"}, headers={"x-csrf-token": owner_csrf}).status_code == 200
    assert coach.post("/invites/accept", json={"token": invites[-1].split("/")[-1]}, headers={"x-csrf-token": coach_csrf}).status_code == 200

    for client, csrf, email in ((owner, owner_csrf, "owner-password@example.com"),
                                (coach, coach_csrf, "coach-password@example.com")):
        other_session = TestClient(app)
        assert other_session.post("/auth/login", json={"email": email, "password": "secure-password-123"}).status_code == 200
        headers = {"x-csrf-token": csrf}
        endpoint = "/auth/change-password"
        assert client.post(endpoint, json={"current_password": "wrong", "new_password": "different-password-123"}, headers=headers).status_code == 400
        assert client.post(endpoint, json={"current_password": "secure-password-123", "new_password": "secure-password-123"}, headers=headers).status_code == 400
        assert client.post(endpoint, json={"current_password": "secure-password-123", "new_password": "short"}, headers=headers).status_code == 422
        assert client.post(endpoint, json={"current_password": "secure-password-123", "new_password": "different-password-123"}).status_code == 403
        assert client.post(endpoint, json={"current_password": "secure-password-123", "new_password": "different-password-123"}, headers=headers).status_code == 200
        assert client.get("/auth/me").status_code == 200
        assert other_session.get("/auth/me").status_code == 401
        assert TestClient(app).post("/auth/login", json={"email": email, "password": "secure-password-123"}).status_code == 401
        assert TestClient(app).post("/auth/login", json={"email": email, "password": "different-password-123"}).status_code == 200


def test_resend_verification_replaces_old_link(monkeypatch):
    clean_database()
    messages = []
    monkeypatch.setattr(accounts, "send_email", lambda to, subject, body: messages.append(body))
    client = TestClient(app)
    assert client.post("/auth/register", json={"email": "new@example.com", "password": "secure-password-123"}).status_code == 201
    old_token = messages[-1].split("/")[-1]
    response = client.post("/auth/resend-verification", json={"email": "new@example.com"})
    assert response.status_code == 200
    assert "new link has been sent" in response.json()["message"]
    new_token = messages[-1].split("/")[-1]
    assert client.post("/auth/verify", json={"token": old_token}).status_code == 400
    assert client.post("/auth/verify", json={"token": new_token}).status_code == 200


def test_email_delivery_message_only_mentions_test_inbox_for_mailpit(monkeypatch):
    monkeypatch.setattr(accounts.settings, "smtp_host", "mailpit")
    assert "test inbox" in accounts.delivery_message("Check your email.")
    monkeypatch.setattr(accounts.settings, "smtp_host", "localhost")
    assert accounts.delivery_message("Check your email.") == "Check your email."

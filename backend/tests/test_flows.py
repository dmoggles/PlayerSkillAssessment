import re
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.database import Base, engine
from app import main
from app.main import app
from app.routers import accounts, teams


# Reference data loaded by migrations: kept between tests (team-owned matrices are removed).
REFERENCE_TABLES = {"skill_tags", "skill_matrices", "matrix_versions", "matrix_skill_tags"}


def clean_database():
    if not engine.url.database or not engine.url.database.endswith("_test"):
        raise RuntimeError("Refusing to clear a database without a _test suffix")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM matrix_skill_tags WHERE matrix_version_id IN (SELECT v.id FROM matrix_versions v JOIN skill_matrices m ON m.id = v.matrix_id WHERE m.team_id IS NOT NULL)"))
        for table in reversed(Base.metadata.sorted_tables):
            if table.name == "matrix_versions":
                conn.execute(text("DELETE FROM matrix_versions WHERE matrix_id IN (SELECT id FROM skill_matrices WHERE team_id IS NOT NULL)"))
            elif table.name == "skill_matrices":
                conn.execute(text("DELETE FROM skill_matrices WHERE team_id IS NOT NULL"))
            elif table.name not in REFERENCE_TABLES:
                conn.execute(table.delete())


def starter_skills(kind="outfield"):
    """Skill ids of the starter matrix for 'outfield' or 'goalkeeper' players, sorted."""
    from app.database import SessionLocal
    from app.matrix import document, skill_set, starter_version
    with SessionLocal() as db:
        return sorted(skill_set(document(db, starter_version(db).id), kind))


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
    skill_ids = starter_skills()
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


def test_squad_self_assessment_links_and_status_board(monkeypatch):
    clean_database()
    owner, csrf = signed_in("squad-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Squad"}, headers=headers).json()["id"]
    ids = {name: owner.post(f"/teams/{team_id}/players", json={"name": name}, headers=headers).json()["id"]
           for name in ("Ana", "Ben", "Cal", "Dee")}
    owner.post(f"/teams/{team_id}/players/{ids['Dee']}/archive", headers=headers)
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    links_url = f"/teams/{team_id}/periods/{period_id}/self-links"
    assert owner.post(links_url, json={}, headers=headers).status_code == 409  # self-assessment disabled
    owner.patch(f"/teams/{team_id}", json={"name": "Squad", "self_assessment_enabled": True}, headers=headers)

    board = owner.get(links_url).json()
    assert [(r["player_name"], r["status"]) for r in board] == [("Ana", "not_sent"), ("Ben", "not_sent"), ("Cal", "not_sent")]
    issued = owner.post(links_url, json={}, headers=headers).json()["links"]
    assert [link["player_name"] for link in issued] == ["Ana", "Ben", "Cal"]
    tokens = {link["player_name"]: link["url"].split("/")[-1] for link in issued}
    # A second bulk issue skips players who already hold a live link.
    assert owner.post(links_url, json={}, headers=headers).json()["links"] == []

    public = TestClient(app)
    assert public.get(f"/self/{tokens['Ben']}").status_code == 200
    assert public.post(f"/self/{tokens['Cal']}", json={"position": "outfield", "ratings": [{"skill_id": "first_touch_body_shape", "score": 2}]}).status_code == 201
    with engine.begin() as conn:
        conn.execute(text("UPDATE self_links SET expires_at = now() - interval '1 day' WHERE player_id = :p"), {"p": ids["Ana"]})
    statuses = {r["player_name"]: r["status"] for r in owner.get(links_url).json()}
    assert statuses == {"Ana": "expired", "Ben": "opened", "Cal": "submitted"}

    # Bulk issue now covers only the expired link; explicit reissue revokes the old token.
    assert [link["player_name"] for link in owner.post(links_url, json={}, headers=headers).json()["links"]] == ["Ana"]
    assert owner.post(links_url, json={"player_ids": [ids["Cal"]]}, headers=headers).status_code == 409
    assert owner.post(links_url, json={"player_ids": [ids["Dee"]]}, headers=headers).status_code == 404
    assert owner.post(links_url, json={"player_ids": [ids["Ben"]]}, headers=headers).status_code == 200
    assert public.get(f"/self/{tokens['Ben']}").status_code == 404
    assert {r["player_name"]: r["status"] for r in owner.get(links_url).json()}["Ben"] == "sent"


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
    skill_ids = starter_skills()
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


def test_health_reports_build_version(monkeypatch):
    monkeypatch.setattr(main.settings, "app_version", "v1.2.3")
    assert TestClient(app).get("/health").json() == {"status": "ok", "version": "v1.2.3"}


def test_membership_changes_are_audited_for_owners(monkeypatch):
    clean_database()
    owner, csrf = signed_in("audit-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("audit-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Audit"}, headers=headers).json()["id"]
    coach_id = add_coach(owner, csrf, team_id, coach, coach_csrf, "audit-coach@example.com", monkeypatch)
    owner.patch(f"/teams/{team_id}/members/{coach_id}", json={"role": "owner"}, headers=headers)
    owner.patch(f"/teams/{team_id}/members/{coach_id}", json={"role": "coach"}, headers=headers)
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    owner.delete(f"/teams/{team_id}/periods/{period_id}", headers=headers)
    assert coach.get(f"/teams/{team_id}/audit").status_code == 404
    coach.delete(f"/teams/{team_id}/members/{coach_id}", headers={"x-csrf-token": coach_csrf})
    events = [(e["action"], e["actor_email"], e["target_email"], e["details"]) for e in reversed(owner.get(f"/teams/{team_id}/audit").json())]
    assert events == [
        ("team_created", "audit-owner@example.com", None, {"name": "Audit"}),
        ("invite_sent", "audit-owner@example.com", "audit-coach@example.com", {}),
        ("invite_accepted", "audit-coach@example.com", None, {}),
        ("role_changed", "audit-owner@example.com", "audit-coach@example.com", {"from": "coach", "to": "owner"}),
        ("role_changed", "audit-owner@example.com", "audit-coach@example.com", {"from": "owner", "to": "coach"}),
        ("period_deleted", "audit-owner@example.com", None, {"label": "Autumn"}),
        ("member_left", "audit-coach@example.com", None, {"role": "coach"}),
    ]


def test_cleanup_removes_only_expired_auth_records(monkeypatch):
    clean_database()
    client, csrf = signed_in("cleanup@example.com", monkeypatch)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sessions (user_id, token_hash, csrf_token, expires_at) SELECT id, 'old', 'x', now() - interval '1 day' FROM users"))
        conn.execute(text("INSERT INTO auth_tokens (email, purpose, token_hash, expires_at) VALUES ('a@example.com', 'reset', 'expired', now() - interval '1 hour'), ('a@example.com', 'reset', 'live', now() + interval '1 hour')"))
        conn.execute(text("INSERT INTO login_attempts (key, failures, window_started) VALUES ('stale', 3, now() - interval '2 days'), ('recent', 3, now())"))
    from app.database import SessionLocal
    from app.maintenance import purge_expired
    with SessionLocal() as db:
        assert purge_expired(db) == {"sessions": 1, "auth_tokens": 1, "login_attempts": 1}
    assert client.get("/auth/me").status_code == 200
    with engine.begin() as conn:
        assert conn.execute(text("SELECT token_hash FROM auth_tokens")).scalars().all() == ["live"]
        assert "recent" in conn.execute(text("SELECT key FROM login_attempts")).scalars().all()


def test_coach_notes_are_saved_trimmed_and_versioned(monkeypatch):
    clean_database()
    owner, csrf = signed_in("notes-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Notes"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Ash"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    body = {"player_id": player_id, "period_id": period_id, "version": 0, "primary_position": "defender",
            "note": "  Strong week overall  ",
            "ratings": [{"skill_id": "first_touch_body_shape", "score": 2, "note": " Heavy touch under a press "},
                        {"skill_id": "switching_play", "score": 3, "note": "   "}]}
    saved = owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).json()
    assert saved["note"] == "Strong week overall"
    notes = {r["skill_id"]: r["note"] for r in saved["ratings"]}
    assert notes == {"first_touch_body_shape": "Heavy touch under a press", "switching_play": None}
    body.update(version=1, note=None)
    body["ratings"][0]["note"] = "x" * 501
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 422
    body["ratings"][0]["note"] = None
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).json()["note"] is None
    snapshots = [r["snapshot"] for r in owner.get(f"/teams/{team_id}/assessments/{saved['id']}/revisions").json()]
    assert snapshots[0]["note"] == "Strong week overall" and snapshots[0]["ratings"][0]["note"] == "Heavy touch under a press"
    assert snapshots[1]["note"] is None and snapshots[1]["ratings"][0]["note"] is None

    owner.patch(f"/teams/{team_id}", json={"name": "Notes", "self_assessment_enabled": True}, headers=headers)
    token = owner.post(f"/teams/{team_id}/players/{player_id}/periods/{period_id}/self-link", headers=headers).json()["url"].split("/")[-1]
    submitted = TestClient(app).post(f"/self/{token}", json={"position": "outfield", "ratings": [
        {"skill_id": "first_touch_body_shape", "score": 4, "note": "players cannot leave notes"}]}).json()
    assert submitted["ratings"][0]["note"] is None


def test_dev_seed_varies_players_and_demos_priority_follow_up(capsys):
    from app import seed_dev
    clean_database()

    def snapshot():
        with engine.begin() as conn:
            ratings = conn.execute(text(
                "SELECT pl.name, pe.label, r.skill_id, r.score FROM ratings r JOIN assessments a ON a.id = r.assessment_id "
                "JOIN players pl ON pl.id = a.player_id JOIN periods pe ON pe.id = a.period_id WHERE a.assessor = 'coach' "
                "ORDER BY 1, 2, 3")).all()
            priorities = conn.execute(text(
                "SELECT pe.label, count(*) FROM priority_confirmations pc JOIN periods pe ON pe.id = pc.period_id GROUP BY 1")).all()
        return ratings, dict(priorities)

    seed_dev.seed()
    ratings, priorities = snapshot()
    by_player = {}
    for name, label, skill_id, score in ratings:
        if label == "Autumn 2026":
            by_player.setdefault(name, []).append(score)
    outfield = [scores for name, scores in by_player.items() if len(scores) == len(starter_skills())]
    assert len({tuple(scores) for scores in outfield}) == len(outfield), "demo players should not share identical ratings"
    # Earlier periods have priorities for every assessed player; the current period only for some.
    assert priorities["Autumn 2025"] == 10 * 3
    assert 0 < priorities["Autumn 2026"] < 10 * 3
    seed_dev.seed()
    assert snapshot() == (ratings, priorities), "reruns should regenerate the same demo data"
    assert "dev-owner@example.com" in capsys.readouterr().out


def test_player_report_is_player_safe_and_limited_to_earlier_periods(monkeypatch):
    clean_database()
    owner, csrf = signed_in("report-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Reports"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Rae"}, headers=headers).json()["id"]
    skill_ids = starter_skills()
    period_ids = [owner.post(f"/teams/{team_id}/periods", json={"label": label}, headers=headers).json()["id"]
                  for label in ("Autumn", "Spring", "Summer")]
    for period_id in period_ids:
        body = {"player_id": player_id, "period_id": period_id, "version": 0, "primary_position": "winger",
                "note": "Private overall note",
                "ratings": [{"skill_id": s, "score": 3, "note": "Private rating note"} for s in skill_ids]}
        assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200
    params = {"player_id": player_id, "period_id": period_ids[0]}
    owner.put(f"/teams/{team_id}/priorities", params=params, headers=headers,
              json={"priorities": [{"skill_id": skill_ids[0], "rank": 1, "coach_note": "Shared priority note"}]})
    owner.patch(f"/teams/{team_id}", json={"name": "Reports", "self_assessment_enabled": True}, headers=headers)
    owner.post(f"/teams/{team_id}/periods/{period_ids[1]}/activate", headers=headers)  # links need the active period
    token = owner.post(f"/teams/{team_id}/players/{player_id}/periods/{period_ids[1]}/self-link", headers=headers).json()["url"].split("/")[-1]
    TestClient(app).post(f"/self/{token}", json={"position": "outfield", "ratings": [{"skill_id": skill_ids[0], "score": 5}]})

    url = f"/teams/{team_id}/players/{player_id}/periods/{period_ids[1]}/report"
    assert owner.put(url, json={"message": "  Great season, keep going  "}, headers=headers).json()["message"] == "Great season, keep going"
    report = owner.get(url).json()
    assert (report["player"], report["team"], report["period"]) == ("Rae", "Reports", "Spring")
    assert [row["label"] for row in report["history"]] == ["Autumn", "Spring"]  # nothing after the report's period
    assert report["history"][0]["priorities"] == [{"skill_id": skill_ids[0], "rank": 1, "coach_note": "Shared priority note"}]
    assert list(report["history"][1]["assessments"]) == ["coach"]  # self-assessment excluded
    text_dump = str(report)
    assert "Private" not in text_dump
    assert owner.put(url, json={"message": "x" * 1001}, headers=headers).status_code == 422
    owner.post(f"/teams/{team_id}/players/{player_id}/archive", headers=headers)
    assert owner.put(url, json={"message": "Changed"}, headers=headers).status_code == 409
    assert owner.get(url).status_code == 200
    owner.post(f"/teams/{team_id}/players/{player_id}/restore", headers=headers)
    assert owner.delete(f"/teams/{team_id}/periods/{period_ids[1]}", headers=headers).status_code == 200


def test_report_share_link_is_read_only_expiring_and_revocable(monkeypatch):
    clean_database()
    owner, csrf = signed_in("share-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Share"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Max"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    base = f"/teams/{team_id}/players/{player_id}/periods/{period_id}/report"
    owner.put(base, json={"message": "Well played"}, headers=headers)
    assert owner.get(base).json()["share"] is None

    first = owner.post(f"{base}/share", headers=headers).json()
    assert first["url"].startswith("http://testserver/report/")
    public = TestClient(app)
    shared = public.get("/report/" + first["url"].split("/")[-1])
    assert shared.status_code == 200
    assert shared.json()["message"] == "Well played" and "share" not in shared.json()
    status = owner.get(base).json()["share"]
    assert status["opened_at"] is not None and status["expired"] is False

    # A new link replaces the old one and resets the opened time.
    second = owner.post(f"{base}/share", headers=headers).json()
    assert public.get("/report/" + first["url"].split("/")[-1]).status_code == 404
    assert owner.get(base).json()["share"]["opened_at"] is None
    token = second["url"].split("/")[-1]
    with engine.begin() as conn:
        conn.execute(text("UPDATE player_reports SET share_expires_at = now() - interval '1 minute'"))
    assert public.get(f"/report/{token}").status_code == 410
    assert owner.get(base).json()["share"]["expired"] is True

    third = owner.post(f"{base}/share", headers=headers).json()["url"].split("/")[-1]
    assert owner.delete(f"{base}/share", headers=headers).status_code == 200
    assert public.get(f"/report/{third}").status_code == 404
    assert owner.get(base).json()["share"] is None
    events = owner.get(f"/teams/{team_id}/audit").json()
    actions = [e["action"] for e in events]
    assert actions.count("report_shared") == 3 and actions.count("report_share_revoked") == 1
    # Only the second link replaced a live one; the third followed an expired link.
    assert [e["details"].get("replaced", False) for e in reversed(events) if e["action"] == "report_shared"] == [False, True, False]
    # Deleting the period removes the report and its link.
    fourth = owner.post(f"{base}/share", headers=headers).json()["url"].split("/")[-1]
    owner.delete(f"/teams/{team_id}/periods/{period_id}", headers=headers)
    assert public.get(f"/report/{fourth}").status_code == 404


def test_periods_pin_matrix_versions_and_tag_levels_follow_the_mapping(monkeypatch):
    from app.database import SessionLocal
    from app.matrix import tag_levels
    clean_database()
    owner, csrf = signed_in("matrix-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Matrix"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Ivy"}, headers=headers).json()["id"]
    period = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()
    version_id = period["matrix_version_id"]
    doc = owner.get(f"/teams/{team_id}/matrix-versions/{version_id}").json()
    assert doc["version_id"] == version_id and doc["meta"]["scale"]["points"] == [1, 2, 3, 4, 5]
    assert {s["id"] for section in doc["sections"] for s in section["skills"] if "goalkeeper" not in section["applies_to"]} == set(starter_skills())
    assert owner.get(f"/teams/{team_id}/matrix-versions/999999").status_code == 404
    assert TestClient(app).get("/skill-matrix").json()["sections"] == doc["sections"]

    scores = {skill_id: 3 for skill_id in starter_skills()}
    scores.update(first_touch_body_shape=1, shape_awareness=4, pressing_unit=2)
    body = {"player_id": player_id, "period_id": period["id"], "version": 0, "primary_position": "defender",
            "ratings": [{"skill_id": s, "score": v} for s, v in scores.items()]}
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200
    with SessionLocal() as db:
        levels = tag_levels(db, player_id, period["id"])
    assert levels["first_touch"] == 1.0
    assert levels["scanning"] == 2.5             # first touch 1 (weight 0.5) and shape awareness 4 (weight 0.5)
    assert levels["team_shape"] == round((4 * 1.0 + 2 * 0.5) / 1.5, 2)
    assert "gk_shot_stopping" not in levels      # goalkeeper skills were not rated

    owner.patch(f"/teams/{team_id}", json={"name": "Matrix", "self_assessment_enabled": True}, headers=headers)
    token = owner.post(f"/teams/{team_id}/players/{player_id}/periods/{period['id']}/self-link", headers=headers).json()["url"].split("/")[-1]
    assert TestClient(app).get(f"/self/{token}").json()["matrix"]["sections"] == doc["sections"]
    report = owner.get(f"/teams/{team_id}/players/{player_id}/periods/{period['id']}/report").json()
    assert report["matrix"]["sections"] == doc["sections"]
    unknown = {**body, "version": 1, "ratings": [{"skill_id": "not_a_skill", "score": 3}]}
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=unknown, headers=headers).status_code == 422


def test_every_starter_skill_maps_to_known_tags():
    with engine.begin() as conn:
        mapped = set(conn.execute(text("SELECT DISTINCT skill_id FROM matrix_skill_tags WHERE matrix_version_id = 1")).scalars())
        unknown = conn.execute(text("SELECT count(*) FROM matrix_skill_tags m LEFT JOIN skill_tags t ON t.id = m.tag_id WHERE t.id IS NULL")).scalar()
        tag_count = conn.execute(text("SELECT count(*) FROM skill_tags WHERE level_1 <> '' AND level_3 <> '' AND level_5 <> ''")).scalar()
    assert mapped == set(starter_skills("outfield")) | set(starter_skills("goalkeeper"))
    assert unknown == 0 and tag_count == 30


def test_pronoun_placeholders_render_for_each_team_gender(monkeypatch):
    from app.wording import gendered_words, render
    assert render("where {they} {is|are} or what {they} {wants|want}", "girls") == "where she is or what she wants"
    assert render("where {they} {is|are} or what {they} {wants|want}", "mixed") == "where they are or what they want"
    assert render("{They} set {their} position, making {themself} big", "boys") == "He set his position, making himself big"
    assert render("making {themself} big", "mixed") == "making themselves big"
    assert render("so {they}{'s|'re} free", "boys") == "so he's free" and render("so {they}{'s|'re} free", "mixed") == "so they're free"
    assert gendered_words("She sets her position") == ["She", "her"] and gendered_words("Theirs, not hers") == ["hers"]

    clean_database()
    owner, csrf = signed_in("gender-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("gender-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team = owner.post("/teams", json={"name": "Wording"}, headers=headers).json()
    assert team["player_gender"] == "mixed"
    add_coach(owner, csrf, team["id"], coach, coach_csrf, "gender-coach@example.com", monkeypatch)
    period = owner.post(f"/teams/{team['id']}/periods", json={"label": "Autumn"}, headers=headers).json()
    url = f"/teams/{team['id']}/matrix-versions/{period['matrix_version_id']}"

    def communication_level_1(client):
        doc = client.get(url).json()
        return next(s for section in doc["sections"] for s in section["skills"] if s["id"] == "communication")["descriptors"]["1"]

    assert communication_level_1(owner).endswith("where they are or what they want")
    settings = {"name": "Wording", "self_assessment_enabled": False}
    assert coach.patch(f"/teams/{team['id']}", json={**settings, "player_gender": "girls"}, headers={"x-csrf-token": coach_csrf}).status_code == 404
    assert owner.patch(f"/teams/{team['id']}", json={**settings, "player_gender": "other"}, headers=headers).status_code == 422
    assert owner.patch(f"/teams/{team['id']}", json={**settings, "player_gender": "girls"}, headers=headers).json()["player_gender"] == "girls"
    assert communication_level_1(coach).endswith("where she is or what she wants")
    # Omitting the field leaves the setting unchanged.
    assert owner.patch(f"/teams/{team['id']}", json=settings, headers=headers).json()["player_gender"] == "girls"
    owner.patch(f"/teams/{team['id']}", json={**settings, "player_gender": "boys"}, headers=headers)
    assert communication_level_1(owner).endswith("where he is or what he wants")
    gender_events = [e["details"] for e in owner.get(f"/teams/{team['id']}/audit").json() if e["action"] == "player_gender_changed"]
    assert gender_events == [{"from": "girls", "to": "boys"}, {"from": "mixed", "to": "girls"}]

    # Age group: unset at first, omitted leaves it alone, null clears it.
    assert team["age_group"] is None
    assert owner.patch(f"/teams/{team['id']}", json={**settings, "age_group": 4}, headers=headers).status_code == 422
    assert owner.patch(f"/teams/{team['id']}", json={**settings, "age_group": 12}, headers=headers).json()["age_group"] == 12
    assert owner.patch(f"/teams/{team['id']}", json=settings, headers=headers).json()["age_group"] == 12
    assert owner.patch(f"/teams/{team['id']}", json={**settings, "age_group": None}, headers=headers).json()["age_group"] is None
    age_events = [e["details"] for e in owner.get(f"/teams/{team['id']}/audit").json() if e["action"] == "age_group_changed"]
    assert age_events == [{"from": 12, "to": None}, {"from": None, "to": 12}]


def test_starter_matrix_has_no_hard_coded_gendered_words():
    from app.database import SessionLocal
    from app.matrix import document, starter_version
    from app.wording import gendered_words
    with SessionLocal() as db:
        doc = document(db, starter_version(db).id)
    texts = [skill["label"] for section in doc["sections"] for skill in section["skills"]]
    texts += [text for section in doc["sections"] for skill in section["skills"] for text in skill["descriptors"].values()]
    assert [t for t in texts if gendered_words(t)] == []
    # Neutral pronouns must be placeholders too, or they would not follow the team's setting.
    literal = re.compile(r"\b(they|them|their|theirs|themselves|themself)\b", re.IGNORECASE)
    assert [t for t in texts if literal.search(re.sub(r"\{[^{}]*\}", "", t))] == []
    assert TestClient(app).get("/skill-matrix").json()["sections"][2]["skills"][0]["descriptors"]["3"] == "Holds most shots at their body cleanly; diving stops still developing"


def test_matrix_editor_drafts_classify_changes_and_publish_new_versions(monkeypatch):
    import copy
    clean_database()
    owner, csrf = signed_in("editor-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Editors"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Lou"}, headers=headers).json()["id"]
    autumn = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()
    starter_id = autumn["matrix_version_id"]
    url = f"/teams/{team_id}/matrix/draft"

    state = owner.get(url).json()
    assert state["draft"] is False and state["revision"] == 0 and state["problems"] == [] and not any(state["changes"].values())
    assert state["current"] == {"name": "Starter: U12 7-a-side", "version": 1, "own": False} and "restarts" in state["base_skill_ids"]
    doc = state["document"]
    technical = next(s for s in doc["sections"] if s["id"] == "technical")
    assert next(k for k in technical["skills"] if k["id"] == "passing_short")["tags"] == {"passing_short": 1.0}
    assert "{they}" in str(doc)  # editors work on raw text with placeholders

    # Add a skill without an id: the server assigns a permanent one.
    weights = {p: "MED" for p in ("goalkeeper", "defender", "midfielder", "winger", "striker")}
    technical["skills"].append({"_key": "tmp-1", "label": "Weak foot", "descriptors": {"1": "Avoids it", "3": "Uses it when unpressed", "5": "Two-footed"},
                                "position_weights": weights, "tags": {}})
    state = owner.put(url, json={"revision": 0, "document": doc}, headers=headers).json()
    assert state["revision"] == 1 and state["changes"]["addition"] == ["Added Weak foot to Technical Skills"]
    assert "Weak foot needs at least one skill tag" in state["problems"]
    doc = state["document"]
    weak = next(k for s in doc["sections"] for k in s["skills"] if k["label"] == "Weak foot")
    assert weak["id"] == "weak_foot"
    assert owner.put(url, json={"revision": 0, "document": doc}, headers=headers).status_code == 409  # stale autosave
    fixed = copy.deepcopy(doc); fixed["priority"]["top_n"] = 5
    assert owner.put(url, json={"revision": 1, "document": fixed}, headers=headers).status_code == 422
    flipped = copy.deepcopy(doc); flipped["sections"][0]["applies_to"] = ["goalkeeper"]
    assert owner.put(url, json={"revision": 1, "document": flipped}, headers=headers).status_code == 422

    # Tag the new skill, reword one, retire one, and write a plain pronoun.
    weak["tags"] = {"passing_short": 1.0, "first_touch": 0.5}
    for section in doc["sections"]:
        section["skills"] = [k for k in section["skills"] if k["id"] != "restarts"]
        for k in section["skills"]:
            if k["id"] == "communication":
                k["descriptors"]["5"] = "Organises her teammates constantly"
    state = owner.put(url, json={"revision": 1, "document": doc}, headers=headers).json()
    assert state["problems"] == []
    assert state["warnings"] == ['Communication, level 5: use placeholders instead of "her"']
    assert state["changes"]["wording"] == ["Changed the level 5 description of Communication"]
    assert state["changes"]["breaking"] == ["Retired Restarts (Throw-ins / Kick-ins & Free Kicks)"]

    publish = f"/teams/{team_id}/matrix/publish"
    refused = owner.post(publish, json={"revision": 2}, headers=headers)
    assert refused.status_code == 409 and "Confirm" in refused.json()["detail"]
    published = owner.post(publish, json={"revision": 2, "acknowledge": True}, headers=headers).json()
    assert published["version"] == 1 and published["applied_to_period"] is None
    assert owner.get(url).json()["draft"] is False

    # Existing periods keep the starter; new periods use the team's version.
    periods = {p["label"]: p for p in owner.get(f"/teams/{team_id}/periods").json()}
    assert periods["Autumn"]["matrix_version_id"] == starter_id
    spring = owner.post(f"/teams/{team_id}/periods", json={"label": "Spring"}, headers=headers).json()
    assert spring["matrix_version_id"] == published["version_id"]
    new_doc = owner.get(f"/teams/{team_id}/matrix-versions/{published['version_id']}").json()
    skill_ids = {k["id"] for s in new_doc["sections"] for k in s["skills"]}
    assert "weak_foot" in skill_ids and "restarts" not in skill_ids
    assert "tags" not in str(new_doc["sections"])  # tags live in matrix_skill_tags, not the document
    assert "_key" not in str(new_doc)  # editor-only keys are not published
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT tag_id, weight FROM matrix_skill_tags WHERE matrix_version_id = :v AND skill_id = 'weak_foot' ORDER BY tag_id"),
                            {"v": published["version_id"]}).all()
    assert [tuple(r) for r in rows] == [("first_touch", 0.5), ("passing_short", 1.0)]
    ratings = [{"skill_id": s, "score": 3} for s in sorted(skill_ids - {"handling_shot_stopping", "distribution_short", "distribution_long", "commanding_area", "positioning_angles"})]
    body = {"player_id": player_id, "period_id": spring["id"], "version": 0, "primary_position": "winger", "ratings": ratings}
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200
    retired = {**body, "version": 1, "ratings": [{"skill_id": "restarts", "score": 3}]}
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=retired, headers=headers).status_code == 422

    # History flags what changed between the periods' matrix versions, keeping names of retired skills.
    autumn_body = {"player_id": player_id, "period_id": autumn["id"], "version": 0, "primary_position": "winger",
                   "ratings": [{"skill_id": k, "score": 2} for k in starter_skills()]}
    assert owner.put(f"/teams/{team_id}/assessments/coach", json=autumn_body, headers=headers).status_code == 200
    history = owner.get(f"/teams/{team_id}/players/{player_id}/history").json()
    assert [(row["label"], row["matrix_version_id"]) for row in history] == [("Autumn", starter_id), ("Spring", published["version_id"])]
    assert history[0]["skill_changes"] == {}
    assert history[1]["skill_changes"] == {"communication": "reworded", "weak_foot": "added", "restarts": "retired"}
    assert history[1]["skill_labels"]["restarts"].startswith("Restarts") and history[1]["skill_labels"]["weak_foot"] == "Weak foot"
    assert history[1]["skill_sections"]["weak_foot"] == "technical"
    report = owner.get(f"/teams/{team_id}/players/{player_id}/periods/{spring['id']}/report").json()
    assert report["history"][1]["skill_changes"] == history[1]["skill_changes"]

    # A retired id is never reused; reordering alone needs no confirmation; the unassessed current period can adopt a new version.
    state = owner.get(url).json()
    doc = state["document"]
    doc["sections"][0]["skills"].append({**copy.deepcopy(weak), "id": None, "label": "Restarts", "tags": {"set_pieces": 1.0}})
    doc["sections"][0]["skills"] = [k for k in doc["sections"][0]["skills"] if k["id"] != "weak_foot"]
    state = owner.put(url, json={"revision": 0, "document": doc}, headers=headers).json()
    assert any(k["id"] == "restarts_2" for s in state["document"]["sections"] for k in s["skills"])
    owner.delete(url, headers=headers)
    doc = owner.get(url).json()["document"]
    doc["sections"] = list(reversed(doc["sections"]))
    state = owner.put(url, json={"revision": 0, "document": doc}, headers=headers).json()
    assert state["changes"]["layout"] == ["Changed the order of sections or skills"] and not state["changes"]["breaking"]
    summer = owner.post(f"/teams/{team_id}/periods", json={"label": "Summer"}, headers=headers).json()
    assert owner.get(url).json()["current_period"] == {"label": "Summer", "assessed": False}
    applied = owner.post(publish, json={"revision": 1, "apply_to_current_period": True}, headers=headers).json()
    assert applied["version"] == 2 and applied["applied_to_period"] == "Summer"
    assert next(p for p in owner.get(f"/teams/{team_id}/periods").json() if p["id"] == summer["id"])["matrix_version_id"] == applied["version_id"]
    labels = {p["label"]: p["matrix_label"] for p in owner.get(f"/teams/{team_id}/periods").json()}
    assert labels == {"Autumn": "Starter v1", "Spring": "Editors matrix v1", "Summer": "Editors matrix v2"}
    events = [e for e in owner.get(f"/teams/{team_id}/audit").json() if e["action"] == "matrix_published"]
    assert [e["details"]["version"] for e in events] == [2, 1]
    assert owner.request("DELETE", f"/teams/{team_id}", json={"confirm_name": "Editors"}, headers=headers).status_code == 200


def test_skill_tag_ids_are_never_removed():
    """Tag ids are permanent: they can be retired (active = false) but not deleted or renamed. See TAXONOMY.md."""
    import json
    from pathlib import Path
    files = sorted((Path(__file__).parents[1] / "migrations" / "data").glob("skill_tags_v*.json"))
    ever_defined = {row["id"] for f in files for row in json.loads(f.read_text())}
    with engine.begin() as conn:
        in_database = set(conn.execute(text("SELECT id FROM skill_tags")).scalars())
    assert ever_defined - in_database == set()


def test_team_insights_average_players_group_priorities_by_tag_and_split_positions(monkeypatch):
    clean_database()
    owner, csrf = signed_in("insights-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    team_id = owner.post("/teams", json={"name": "Insights"}, headers=headers).json()["id"]
    ids = {n: owner.post(f"/teams/{team_id}/players", json={"name": n}, headers=headers).json()["id"] for n in ("Ada", "Bea", "Cy")}
    p1 = owner.post(f"/teams/{team_id}/periods", json={"label": "P1"}, headers=headers).json()["id"]

    def assess(player, period, position, kind, score):
        body = {"player_id": ids[player], "period_id": period, "version": 0, "primary_position": position,
                "ratings": [{"skill_id": s, "score": score} for s in starter_skills(kind)]}
        assert owner.put(f"/teams/{team_id}/assessments/coach", json=body, headers=headers).status_code == 200

    assess("Ada", p1, "defender", "outfield", 2)
    assess("Bea", p1, "winger", "outfield", 4)
    assess("Cy", p1, "goalkeeper", "goalkeeper", 3)
    for player, picks in (("Ada", ["first_touch_body_shape", "passing_short"]), ("Bea", ["first_touch_body_shape"])):
        assert owner.put(f"/teams/{team_id}/priorities", params={"player_id": ids[player], "period_id": p1}, headers=headers,
                         json={"priorities": [{"skill_id": s, "rank": i + 1} for i, s in enumerate(picks)]}).status_code == 200
    p2 = owner.post(f"/teams/{team_id}/periods", json={"label": "P2"}, headers=headers).json()["id"]
    assess("Ada", p2, "defender", "outfield", 3)

    data = owner.get(f"/teams/{team_id}/insights", params={"period_id": p1}).json()
    first, second = data["trend"]
    assert (first["label"], first["players"], second["label"], second["players"]) == ("P1", 3, "P2", 1)
    assert first["sections"]["technical"] == {"average": 3.0, "players": 2}      # Ada 2 and Bea 4
    assert first["sections"]["goalkeeper"] == {"average": 3.0, "players": 1}     # Cy only
    assert first["tags"]["first_touch"] == {"average": 3.0, "players": 2}
    assert second["sections"]["technical"] == {"average": 3.0, "players": 1} and second["changed_sections"] == []
    assert data["tags"]["first_touch"] == {"label": "First touch", "area": "technical"}

    period = data["period"]
    assert (period["assessed"], period["priority_players"]) == (3, 2)
    assert [(p["skill_id"], [x["player"] for x in p["players"]]) for p in period["priorities"]] == [
        ("first_touch_body_shape", ["Ada", "Bea"]), ("passing_short", ["Ada"])]
    # Main tags only: first touch counts once per player; the partial scanning tag is not counted.
    assert [(t["tag_id"], len(t["players"])) for t in period["priority_tags"]] == [("first_touch", 2), ("passing_short", 1)]
    assert [(g["position"], g["players"]) for g in period["positions"]] == [("goalkeeper", 1), ("defender", 1), ("winger", 1)]
    assert next(g for g in period["positions"] if g["position"] == "winger")["sections"]["tactical"] == {"average": 4.0, "players": 1}
    assert owner.get(f"/teams/{team_id}/insights").json()["period"] is None

    # Position filter: trends and priorities cover one primary position; the position breakdown stays whole-squad.
    defenders = owner.get(f"/teams/{team_id}/insights", params={"period_id": p1, "position": "defender"}).json()
    assert [(row["label"], row["players"]) for row in defenders["trend"]] == [("P1", 1), ("P2", 1)]
    assert defenders["trend"][0]["sections"]["technical"] == {"average": 2.0, "players": 1}     # Ada only
    assert "goalkeeper" not in defenders["trend"][0]["sections"]
    assert (defenders["period"]["assessed"], defenders["period"]["priority_players"]) == (1, 1)
    assert [(t["tag_id"], [p["player"] for p in t["players"]]) for t in defenders["period"]["priority_tags"]] == [("first_touch", ["Ada"]), ("passing_short", ["Ada"])]
    assert len(defenders["period"]["positions"]) == 3
    strikers = owner.get(f"/teams/{team_id}/insights", params={"period_id": p1, "position": "striker"}).json()
    assert strikers["trend"] == [] and strikers["period"]["priorities"] == [] and strikers["period"]["assessed"] == 0
    assert owner.get(f"/teams/{team_id}/insights", params={"position": "sweeper"}).status_code == 422


def test_drill_library_loads_checks_and_serves_drills(monkeypatch, tmp_path):
    import json
    from app.database import SessionLocal
    from app.drills import DATA_DIR, DrillError, diagram_problems, load_file
    clean_database()
    client, csrf = signed_in("drills-coach@example.com", monkeypatch)
    with SessionLocal() as db:
        assert load_file(db, DATA_DIR / "drills_v1.json") == {"added": 5, "updated": 0, "retired": 0}
        assert load_file(db, DATA_DIR / "drills_v1.json") == {"added": 0, "updated": 5, "retired": 0}  # safe to re-run

    drills = {d["slug"]: d for d in client.get("/drills").json()}
    assert len(drills) == 5
    rondo = drills["rondo-4v1"]
    assert rondo["levels"] == [1, 5] and rondo["votes"] == {"likes": 0, "dislikes": 0, "mine": 0, "reason": None}
    assert rondo["equipment_items"] == ["balls", "bibs", "cones"]
    assert [(t["id"], t["weight"]) for t in rondo["tags"]][0] == ("passing_short", 1.0)
    detail = client.get("/drills/receive-and-turn").json()
    assert [v["kind"] for v in detail["variations"]] == ["regression", "base", "escalator", "escalator"]
    second_diagram = detail["media"][1]["id"]
    assert detail["variations"][2]["diagram_media_id"] == second_diagram
    assert detail["media"][0]["diagram"]["steps"][1]["actions"] == [{"pass": {"from": "S", "to": "R"}}]
    # Variations override only what they change; null means "same as the drill".
    rondo_detail = client.get("/drills/rondo-4v1").json()
    base, two_touch, four_v_two = rondo_detail["variations"][1], rondo_detail["variations"][2], rondo_detail["variations"][3]
    assert base["players"] is None and base["setup"] is None and base["coaching_points"] is None
    assert two_touch["coaching_points"][0] == "Decide where the ball goes before it arrives." and two_touch["setup"] is None
    assert four_v_two["players"] == [6, 6, 18] and four_v_two["equipment"][1] == {"item": "bibs", "quantity": 2}
    assert four_v_two["diagram_media_id"] == rondo_detail["media"][1]["id"]
    assert rondo_detail["variations"][0]["diagram_media_id"] == rondo_detail["media"][3]["id"]  # 5v1 has its own
    assert client.get("/drills/one-v-one-end-line").json()["variations"][3]["space"] == [6.0, 15.0]
    keeper = client.get("/drills/gk-catch-and-hold").json()
    videos = {m["url"]: m["id"] for m in keeper["media"] if m["kind"] == "video"}
    angled = next(v for v in keeper["variations"] if v["title"] == "Angled strikes")
    assert angled["video_media_id"] == videos["https://www.youtube.com/shorts/SbMUr6HNJOQ"]
    assert all(v["video_media_id"] is None for v in keeper["variations"] if v["title"] != "Angled strikes")
    with engine.begin() as conn:  # "no override" is SQL NULL, not a JSON null value
        assert conn.execute(text("SELECT count(*) FROM drill_variations WHERE kind = 'base' AND (equipment IS NOT NULL OR instructions IS NOT NULL OR coaching_points IS NOT NULL)")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM drill_media WHERE kind = 'diagram' AND diagram IS NULL")).scalar() == 0
    assert client.get("/drills/no-such-drill").status_code == 404
    assert TestClient(app).get("/drills").status_code == 401

    # Votes: one per coach per drill, totals shared, a reason only with a dislike.
    other, other_csrf = signed_in("drills-other@example.com", monkeypatch)
    vote = lambda c, token, body, slug="rondo-4v1": c.put(f"/drills/{slug}/vote", json=body, headers={"x-csrf-token": token})
    assert vote(client, csrf, {"vote": 1}).json() == {"likes": 1, "dislikes": 0, "mine": 1, "reason": None}
    assert vote(other, other_csrf, {"vote": -1, "reason": "too_advanced"}).json() == {"likes": 1, "dislikes": 1, "mine": -1, "reason": "too_advanced"}
    assert vote(client, csrf, {"vote": -1}).json() == {"likes": 0, "dislikes": 2, "mine": -1, "reason": None}  # changing a vote replaces it
    assert vote(client, csrf, {"vote": 0}).json() == {"likes": 0, "dislikes": 1, "mine": 0, "reason": None}
    assert vote(client, csrf, {"vote": 0}).status_code == 200  # clearing twice is harmless
    assert vote(client, csrf, {"vote": 1, "reason": "unclear"}).status_code == 422
    assert vote(client, csrf, {"vote": -1, "reason": "boring"}).status_code == 422
    assert vote(client, csrf, {"vote": 2}).status_code == 422
    assert vote(client, csrf, {"vote": 1}, slug="no-such-drill").status_code == 404
    assert client.put("/drills/rondo-4v1/vote", json={"vote": 1}).status_code == 403  # CSRF token required
    listed = next(d for d in other.get("/drills").json() if d["slug"] == "rondo-4v1")
    assert listed["votes"] == {"likes": 0, "dislikes": 1, "mine": -1, "reason": "too_advanced"}

    # Bad diagrams are caught by replaying them.
    base = {"pitch": {"width": 10, "length": 10}, "objects": {"A": {"type": "player", "team": "A", "at": [1, 1]},
            "B": {"type": "player", "team": "B", "at": [5, 5]}, "ball": {"type": "ball", "with": "A"}}}
    assert diagram_problems({**base, "steps": [{"label": "ok", "actions": [{"pass": {"from": "A", "to": "B"}}]}]}) == []
    assert diagram_problems({**base, "steps": [{"label": "x", "actions": [{"pass": {"from": "B", "to": "A"}}]}]}) == ["step 1: B passes without the ball"]
    assert diagram_problems({**base, "steps": [{"label": "x", "actions": [{"run": {"who": "A", "to": [12, 3]}}]}]}) == ["step 1: run target is off the pitch"]
    assert diagram_problems({**base, "steps": [{"label": "x", "actions": [{"shot": {"who": "A", "to": "goal"}}]}]}) == ["step 1: shot at unknown goal goal"]

    # A bad file changes nothing; a drill dropped from its file is retired, not deleted.
    data = json.loads((DATA_DIR / "drills_v1.json").read_text())
    data["drills"][0]["variations"][0]["levels"] = [4, 5]  # gap before the base variation and out of order
    data["drills"][1]["tags"] = {"not_a_tag": 1.0}
    data["drills"][3]["ladder_tags"] = ["dribbling"]
    data["drills"][2]["variations"][3]["players"] = [7, 6, 18]
    data["drills"][2]["variations"][3]["equipment"] = [{"item": "trampoline", "quantity": 1}]
    data["drills"][2]["variations"][1]["video"] = 0  # media 0 of the rondo is a diagram, not a video
    bad = tmp_path / "drills_v1.json"
    bad.write_text(json.dumps(data))
    with SessionLocal() as db:
        try:
            load_file(db, bad)
            raise AssertionError("expected rejection")
        except DrillError as error:
            assert "unknown or retired tag 'not_a_tag'" in str(error) and "without a gap" in str(error)
            assert "players must be [min, ideal, max]" in str(error) and "unknown equipment 'trampoline'" in str(error)
            assert "video must point at one of this drill's videos" in str(error)
            assert "ladder_tags must be a non-empty list of this drill's tags" in str(error)
    data = json.loads((DATA_DIR / "drills_v1.json").read_text())
    data["drills"] = [d for d in data["drills"] if d["slug"] != "rondo-4v1"]
    smaller = tmp_path / "smaller.json"
    smaller.write_text(json.dumps(data))
    with SessionLocal() as db:
        assert load_file(db, smaller)["retired"] == 1
    assert "rondo-4v1" not in {d["slug"] for d in client.get("/drills").json()}
    assert client.get("/drills/rondo-4v1").status_code == 404


def test_drill_suggestions_match_priority_skills_at_the_players_level(monkeypatch):
    from app.database import SessionLocal
    from app.drills import DATA_DIR, load_file
    clean_database()
    owner, csrf = signed_in("suggest-owner@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    with SessionLocal() as db:
        load_file(db, DATA_DIR / "drills_v1.json")
    team_id = owner.post("/teams", json={"name": "Suggest"}, headers=headers).json()["id"]
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Kit"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    scores = {s: 3 for s in starter_skills()} | {"passing_short": 1, "first_touch_body_shape": 5}
    owner.put(f"/teams/{team_id}/assessments/coach", json={"player_id": player_id, "period_id": period_id, "version": 0,
              "primary_position": "defender", "ratings": [{"skill_id": s, "score": v} for s, v in scores.items()]}, headers=headers)
    url = f"/teams/{team_id}/players/{player_id}/drill-suggestions"

    def suggest(*skills):
        return owner.get(url, params={"period_id": period_id, "skills": list(skills)}).json()

    out = suggest("passing_short", "first_touch_body_shape", "decision_making_open_play", "shooting", "no_such_skill")
    passing = out["passing_short"]
    assert passing["tagged"] and passing["level"] == 1 and [d["slug"] for d in passing["drills"]] == ["rondo-4v1"]
    assert passing["drills"][0]["variation"]["title"] == "5v1 in a bigger square"  # level 1: the easiest rung
    assert [t["id"] for t in passing["drills"][0]["tags"]] == ["passing_short"]  # only the tags that matched
    assert out["first_touch_body_shape"]["drills"][0]["slug"] == "receive-and-turn"
    assert out["first_touch_body_shape"]["drills"][0]["variation"]["levels"][1] == 5  # level 5: the hardest rung
    # Level 3 sits in two rungs' ranges; the harder one stretches the player.
    assert out["decision_making_open_play"]["drills"][0]["variation"]["title"] == "Two-touch limit"
    # The 1v1 drill escalates for the attacker: a defending priority gets its base version, not a rung.
    defending = suggest("1v1_defending")["1v1_defending"]["drills"][0]
    assert defending["variation"]["kind"] == "base" and defending["variation"]["level_matched"] is False
    assert defending["ladder_for"] == ["1v1 attacking"]
    attacking = suggest("1v1_attacking")["1v1_attacking"]["drills"][0]
    assert attacking["variation"]["title"] == "Five-second limit" and attacking["ladder_for"] == []
    assert out["shooting"] == {"tagged": True, "level": 3, "matches": 0, "drills": []}  # no shooting drills yet
    assert out["no_such_skill"]["tagged"] is False

    # The coach's own dislike removes a drill from their suggestions only.
    owner.put("/drills/rondo-4v1/vote", json={"vote": -1}, headers=headers)
    assert suggest("passing_short")["passing_short"]["drills"] == []
    owner.put("/drills/rondo-4v1/vote", json={"vote": 0}, headers=headers)
    # Drills outside the team's age group are left out.
    owner.patch(f"/teams/{team_id}", json={"name": "Suggest", "self_assessment_enabled": False, "age_group": 7}, headers=headers)
    assert suggest("passing_short")["passing_short"]["drills"] == []
    assert suggest("dribbling_carrying")["dribbling_carrying"]["drills"][0]["slug"] == "cone-slalom-dribble"

    assert owner.get(url, params={"period_id": 999999, "skills": "passing_short"}).status_code == 404
    outsider, _ = signed_in("suggest-outsider@example.com", monkeypatch)
    assert outsider.get(url, params={"period_id": period_id}).status_code == 404

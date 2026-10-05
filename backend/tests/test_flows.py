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

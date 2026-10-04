from fastapi.testclient import TestClient
from sqlalchemy import text
from app.database import Base, engine
from app import main
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

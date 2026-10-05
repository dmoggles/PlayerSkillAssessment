"""Every API route must declare who may call it, and outsiders, anonymous users and
coaches are checked against that declaration. Adding a route without listing it here fails."""
from fastapi.testclient import TestClient
from app.main import app
from app.routers import teams
from test_flows import add_coach, clean_database, signed_in, starter_skills

PUBLIC, SIGNED_IN, MEMBER, OWNER = "public", "signed_in", "member", "owner"
PP = {"player_id": "{player_id}", "period_id": "{period_id}"}

# (method, path) -> (who may call it, json body, query params)
ACCESS = {
    ("POST", "/auth/register"): (PUBLIC, None, None),
    ("POST", "/auth/resend-verification"): (PUBLIC, None, None),
    ("POST", "/auth/verify"): (PUBLIC, None, None),
    ("POST", "/auth/login"): (PUBLIC, None, None),
    ("POST", "/auth/forgot-password"): (PUBLIC, None, None),
    ("POST", "/auth/reset-password"): (PUBLIC, None, None),
    ("GET", "/skill-matrix"): (PUBLIC, None, None),
    ("GET", "/teams/{team_id}/matrix-versions/{version_id}"): (MEMBER, None, None),
    ("GET", "/skill-tags"): (SIGNED_IN, None, None),
    ("GET", "/teams/{team_id}/matrix/draft"): (OWNER, None, None),
    ("PUT", "/teams/{team_id}/matrix/draft"): (OWNER, {"revision": 0, "document": {}}, None),
    ("DELETE", "/teams/{team_id}/matrix/draft"): (OWNER, None, None),
    ("POST", "/teams/{team_id}/matrix/publish"): (OWNER, {"revision": 1}, None),
    ("GET", "/health"): (PUBLIC, None, None),
    ("GET", "/self/{token}"): (PUBLIC, None, None),
    ("GET", "/report/{token}"): (PUBLIC, None, None),
    ("POST", "/self/{token}"): (PUBLIC, None, None),
    ("GET", "/auth/me"): (SIGNED_IN, None, None),
    ("POST", "/auth/logout"): (SIGNED_IN, None, None),
    ("POST", "/auth/change-password"): (SIGNED_IN, {"current_password": "x" * 12, "new_password": "y" * 12}, None),
    ("GET", "/teams"): (SIGNED_IN, None, None),
    ("POST", "/teams"): (SIGNED_IN, {"name": "Another"}, None),
    ("POST", "/invites/accept"): (SIGNED_IN, {"token": "unknown"}, None),
    ("PATCH", "/teams/{team_id}"): (OWNER, {"name": "Renamed", "self_assessment_enabled": True}, None),
    ("DELETE", "/teams/{team_id}"): (OWNER, {"confirm_name": "Perms"}, None),
    ("GET", "/teams/{team_id}/audit"): (OWNER, None, None),
    ("GET", "/teams/{team_id}/members"): (MEMBER, None, None),
    ("PATCH", "/teams/{team_id}/members/{member_user_id}"): (OWNER, {"role": "coach"}, None),
    # Members may remove themselves; removing anyone else needs an owner. Checked with the owner as target.
    ("DELETE", "/teams/{team_id}/members/{member_user_id}"): (OWNER, None, None),
    ("POST", "/teams/{team_id}/invites"): (OWNER, {"email": "new-coach@example.com"}, None),
    ("GET", "/teams/{team_id}/players"): (MEMBER, None, None),
    ("POST", "/teams/{team_id}/players"): (MEMBER, {"name": "Newcomer"}, None),
    ("PATCH", "/teams/{team_id}/players/{player_id}"): (MEMBER, {"name": "Renamed player"}, None),
    ("POST", "/teams/{team_id}/players/{player_id}/archive"): (MEMBER, None, None),
    ("POST", "/teams/{team_id}/players/{player_id}/restore"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/periods"): (MEMBER, None, None),
    ("POST", "/teams/{team_id}/periods"): (MEMBER, {"label": "Spring"}, None),
    ("POST", "/teams/{team_id}/periods/{period_id}/activate"): (MEMBER, None, None),
    ("PATCH", "/teams/{team_id}/periods/{period_id}"): (MEMBER, {"label": "Autumn term"}, None),
    ("DELETE", "/teams/{team_id}/periods/{period_id}"): (OWNER, None, None),
    ("PUT", "/teams/{team_id}/assessments/coach"): (MEMBER, "assessment", None),
    ("GET", "/teams/{team_id}/assessments/coach"): (MEMBER, None, PP),
    ("GET", "/teams/{team_id}/assessments/compare"): (MEMBER, None, PP),
    ("GET", "/teams/{team_id}/assessments/period/{period_id}"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/players/{player_id}/history"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/assessments/{assessment_id}/revisions"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/priorities"): (MEMBER, None, PP),
    ("PUT", "/teams/{team_id}/priorities"): (MEMBER, {"priorities": []}, PP),
    ("POST", "/teams/{team_id}/players/{player_id}/periods/{period_id}/self-link"): (MEMBER, None, None),
    ("DELETE", "/teams/{team_id}/players/{player_id}/periods/{period_id}/self-link"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/periods/{period_id}/self-links"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/players/{player_id}/periods/{period_id}/report"): (MEMBER, None, None),
    ("PUT", "/teams/{team_id}/players/{player_id}/periods/{period_id}/report"): (MEMBER, {"message": "Well done"}, None),
    ("POST", "/teams/{team_id}/players/{player_id}/periods/{period_id}/report/share"): (MEMBER, None, None),
    ("DELETE", "/teams/{team_id}/players/{player_id}/periods/{period_id}/report/share"): (MEMBER, None, None),
    ("POST", "/teams/{team_id}/periods/{period_id}/self-links"): (MEMBER, {}, None),
}


def api_routes():
    return {(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops}


def test_every_route_declares_its_access_level():
    routes = api_routes()
    assert routes - ACCESS.keys() == set(), "New routes need an entry in ACCESS"
    assert ACCESS.keys() - routes == set(), "ACCESS lists routes that no longer exist"


def test_routes_reject_callers_below_their_access_level(monkeypatch):
    clean_database()
    monkeypatch.setattr(teams, "send_email", lambda *args: None)
    owner, owner_csrf = signed_in("perm-owner@example.com", monkeypatch)
    coach, coach_csrf = signed_in("perm-coach@example.com", monkeypatch)
    outsider, outsider_csrf = signed_in("perm-outsider@example.com", monkeypatch)
    headers = {"x-csrf-token": owner_csrf}
    team_id = owner.post("/teams", json={"name": "Perms"}, headers=headers).json()["id"]
    owner_id = owner.get(f"/teams/{team_id}/members").json()[0]["user_id"]
    add_coach(owner, owner_csrf, team_id, coach, coach_csrf, "perm-coach@example.com", monkeypatch)
    player_id = owner.post(f"/teams/{team_id}/players", json={"name": "Kit"}, headers=headers).json()["id"]
    period_id = owner.post(f"/teams/{team_id}/periods", json={"label": "Autumn"}, headers=headers).json()["id"]
    owner.patch(f"/teams/{team_id}", json={"name": "Perms", "self_assessment_enabled": True}, headers=headers)
    assessment = {"player_id": player_id, "period_id": period_id, "version": 0, "primary_position": "defender",
                  "ratings": [{"skill_id": s, "score": 3} for s in starter_skills()]}
    assessment_id = owner.put(f"/teams/{team_id}/assessments/coach", json=assessment, headers=headers).json()["id"]
    ids = {"team_id": team_id, "player_id": player_id, "period_id": period_id,
           "assessment_id": assessment_id, "member_user_id": owner_id,
           "version_id": owner.get(f"/teams/{team_id}/periods").json()[0]["matrix_version_id"]}

    def call(client, csrf, method, path, body, query):
        url = path.format(**ids)
        params = {k: v.format(**ids) for k, v in query.items()} if query else None
        json_body = {**assessment, "version": 1} if body == "assessment" else body
        return client.request(method, url, json=json_body, params=params, headers={"x-csrf-token": csrf} if csrf else {})

    anonymous = TestClient(app)
    failures = []
    for (method, path), (level, body, query) in ACCESS.items():
        if level == PUBLIC:
            continue
        expected = [(anonymous, None, 401)]
        if level in (MEMBER, OWNER):
            expected.append((outsider, outsider_csrf, 404))
        if level == OWNER:
            expected.append((coach, coach_csrf, 404))
        for client, csrf, status in expected:
            got = call(client, csrf, method, path, body, query).status_code
            if got != status:
                failures.append(f"{method} {path}: expected {status}, got {got}")
    assert failures == []

    # Members can use member routes. Run last: some of these change data (archive, revoke, new period).
    for (method, path), (level, body, query) in ACCESS.items():
        if level == MEMBER:
            got = call(coach, coach_csrf, method, path, body, query).status_code
            if got in (401, 403, 404):
                failures.append(f"{method} {path}: coach got {got}")
    assert failures == []


def test_api_docs_are_hidden_unless_enabled():
    client = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404

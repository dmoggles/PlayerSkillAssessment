"""Every API route must declare who may call it, and outsiders, anonymous users and
coaches are checked against that declaration. Adding a route without listing it here fails."""
from fastapi.testclient import TestClient
from app.main import app
from app.routers import teams
from test_flows import add_coach, clean_database, signed_in, starter_skills

PUBLIC, SIGNED_IN, MEMBER, OWNER, ADMIN = "public", "signed_in", "member", "owner", "admin"
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
    ("GET", "/drills"): (SIGNED_IN, None, None),
    ("GET", "/practice/scenarios"): (SIGNED_IN, None, None),
    ("GET", "/practice/generate"): (SIGNED_IN, None, {"topic": "defending_off_ball", "stage": "1"}),
    ("GET", "/practice/{token}"): (PUBLIC, None, None),
    ("GET", "/practice/{token}/generate"): (PUBLIC, None, None),
    ("POST", "/practice/{token}/attempts"): (PUBLIC, None, None),
    ("GET", "/teams/{team_id}/players/{player_id}/practice"): (MEMBER, None, None),
    ("GET", "/polls/{poll_id}"): (PUBLIC, None, None),
    ("PUT", "/polls/{poll_id}/answers/{scenario_id}"): (PUBLIC, None, None),
    ("GET", "/polls/{poll_id}/results"): (ADMIN, None, None),
    ("DELETE", "/polls/{poll_id}/respondents/{respondent}"): (ADMIN, None, None),
    ("DELETE", "/polls/{poll_id}/answers"): (ADMIN, None, None),
    ("POST", "/teams/{team_id}/players/{player_id}/practice/assignments"): (MEMBER, {"topic": "defending_off_ball", "stage": 1}, None),
    ("DELETE", "/teams/{team_id}/players/{player_id}/practice/assignments/{assignment_id}"): (MEMBER, None, None),
    ("POST", "/teams/{team_id}/players/{player_id}/practice/link"): (MEMBER, None, None),
    ("DELETE", "/teams/{team_id}/players/{player_id}/practice/link"): (MEMBER, None, None),
    ("GET", "/drills/{slug}"): (SIGNED_IN, None, None),
    ("PUT", "/drills/{slug}/vote"): (SIGNED_IN, {"vote": 1}, None),
    ("POST", "/drills/{slug}/video-suggestions"): (SIGNED_IN, {"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}, None),
    ("GET", "/me/video-suggestions"): (SIGNED_IN, None, None),
    ("POST", "/drills/{slug}/link-reports"): (SIGNED_IN, {"url": "https://example.com", "reason": "dead"}, None),
    ("GET", "/admin/link-reports"): (ADMIN, None, None),
    ("POST", "/admin/link-reports/{report_id}/hide"): (ADMIN, None, None),
    ("POST", "/admin/link-reports/{report_id}/keep"): (ADMIN, None, None),
    ("POST", "/admin/link-reports/{report_id}/restore"): (ADMIN, None, None),
    ("GET", "/admin/video-suggestions"): (ADMIN, None, None),
    ("POST", "/admin/video-suggestions/{suggestion_id}/approve"): (ADMIN, {"caption": "A video"}, None),
    ("POST", "/admin/video-suggestions/{suggestion_id}/reject"): (ADMIN, {"reason": "quality"}, None),
    ("GET", "/teams/{team_id}/players/{player_id}/drill-suggestions"): (MEMBER, None, {"period_id": "{period_id}", "skills": "passing"}),
    ("GET", "/teams/{team_id}/players/{player_id}/plan"): (MEMBER, None, {"period_id": "{period_id}"}),
    ("POST", "/teams/{team_id}/players/{player_id}/plan"): (MEMBER, "plan", None),
    ("GET", "/teams/{team_id}/players/{player_id}/cycles"): (MEMBER, None, {"period_id": "{period_id}"}),
    ("POST", "/teams/{team_id}/players/{player_id}/cycles"): (MEMBER, "plan", None),
    ("GET", "/teams/{team_id}/players/{player_id}/plan/alternatives"): (MEMBER, None, {"period_id": "{period_id}", "skill_id": "passing_short", "slot": "club"}),
    ("PUT", "/teams/{team_id}/players/{player_id}/plan/slot"): (MEMBER, "slot", None),
    ("POST", "/teams/{team_id}/plans/generate"): (MEMBER, "plan", None),
    ("GET", "/report/{token}/drills/{slug}"): (PUBLIC, None, None),
    ("GET", "/teams/{team_id}/matrix/draft"): (OWNER, None, None),
    ("PUT", "/teams/{team_id}/matrix/draft"): (OWNER, {"revision": 0, "document": {}}, None),
    ("DELETE", "/teams/{team_id}/matrix/draft"): (OWNER, None, None),
    ("POST", "/teams/{team_id}/matrix/publish"): (OWNER, {"revision": 1}, None),
    ("GET", "/health"): (PUBLIC, None, None),
    ("POST", "/access-requests"): (PUBLIC, None, None),
    ("GET", "/admin/access-requests"): (ADMIN, None, None),
    ("POST", "/admin/access-requests/{request_id}/invite"): (ADMIN, None, None),
    ("POST", "/admin/access-requests/{request_id}/decline"): (ADMIN, None, None),
    ("GET", "/self/{token}"): (PUBLIC, None, None),
    ("GET", "/report/{token}"): (PUBLIC, None, None),
    ("POST", "/self/{token}"): (PUBLIC, None, None),
    ("GET", "/auth/me"): (SIGNED_IN, None, None),
    ("POST", "/auth/logout"): (SIGNED_IN, None, None),
    ("POST", "/auth/change-password"): (SIGNED_IN, {"current_password": "x" * 12, "new_password": "y" * 12}, None),
    ("POST", "/auth/delete-account"): (SIGNED_IN, {"password": "wrong-password"}, None),
    ("GET", "/teams"): (SIGNED_IN, None, None),
    ("POST", "/teams"): (SIGNED_IN, {"name": "Another"}, None),
    ("POST", "/invites/accept"): (SIGNED_IN, {"token": "unknown"}, None),
    ("GET", "/invites/{token}"): (PUBLIC, None, None),
    ("GET", "/admin/invites"): (ADMIN, None, None),
    ("POST", "/admin/invites"): (ADMIN, {"email": "new-club@example.com"}, None),
    ("DELETE", "/admin/invites/{invite_id}"): (ADMIN, None, None),
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
    ("DELETE", "/teams/{team_id}/players/{player_id}"): (OWNER, {"confirm_name": "Kit"}, None),
    ("GET", "/teams/{team_id}/players/{player_id}/export"): (OWNER, None, None),
    ("GET", "/teams/{team_id}/periods"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/periods/{period_id}/groups"): (MEMBER, None, None),
    ("PUT", "/teams/{team_id}/players/{player_id}/group"): (MEMBER, {"age_group": 11}, {"period_id": "{period_id}"}),
    ("POST", "/teams/{team_id}/periods"): (MEMBER, {"label": "Spring"}, None),
    ("POST", "/teams/{team_id}/periods/{period_id}/activate"): (MEMBER, None, None),
    ("PATCH", "/teams/{team_id}/periods/{period_id}"): (MEMBER, {"label": "Autumn term"}, None),
    ("DELETE", "/teams/{team_id}/periods/{period_id}"): (OWNER, None, None),
    ("PUT", "/teams/{team_id}/assessments/coach"): (MEMBER, "assessment", None),
    ("GET", "/teams/{team_id}/assessments/coach"): (MEMBER, None, PP),
    ("GET", "/teams/{team_id}/assessments/compare"): (MEMBER, None, PP),
    ("GET", "/teams/{team_id}/assessments/period/{period_id}"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/insights"): (MEMBER, None, {"period_id": "{period_id}"}),
    ("GET", "/teams/{team_id}/players/{player_id}/history"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/players/{player_id}/profile"): (MEMBER, None, {"period_id": "{period_id}"}),
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
    ("POST", "/teams/{team_id}/players/{player_id}/periods/{period_id}/report/share/extend"): (MEMBER, {"weeks": 1}, None),
    ("POST", "/teams/{team_id}/periods/{period_id}/self-links"): (MEMBER, {}, None),
    ("GET", "/teams/{team_id}/sessions"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/sessions/focus"): (MEMBER, None, {"period_id": "{period_id}"}),
    ("POST", "/teams/{team_id}/sessions"): (MEMBER, "session", None),
    ("GET", "/teams/{team_id}/sessions/{session_id}"): (MEMBER, None, None),
    ("PATCH", "/teams/{team_id}/sessions/{session_id}"): (MEMBER, {"title": "Renamed"}, None),
    # Ordered so the coach's run (last test below) uses the block and session before deleting them.
    ("POST", "/teams/{team_id}/sessions/{session_id}/blocks"): (MEMBER, {"phase": "cool_down", "minutes": 5, "title": "Stretches"}, None),
    ("POST", "/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/groups"): (MEMBER, None, None),
    ("PUT", "/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/groups"): (MEMBER, {"groups": [[1], [2]]}, None),
    ("DELETE", "/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/groups"): (MEMBER, None, None),
    ("PUT", "/teams/{team_id}/sessions/{session_id}/blocks/{block_id}"): (MEMBER, {"minutes": 12}, None),
    ("GET", "/teams/{team_id}/sessions/{session_id}/blocks/{block_id}/alternatives"): (MEMBER, None, None),
    ("DELETE", "/teams/{team_id}/sessions/{session_id}/blocks/{block_id}"): (MEMBER, None, None),
    ("PUT", "/teams/{team_id}/sessions/{session_id}/groups"): (MEMBER, {"groups": [[1], [2]]}, None),
    ("POST", "/teams/{team_id}/sessions/{session_id}/regenerate"): (MEMBER, None, None),
    ("PUT", "/teams/{team_id}/sessions/{session_id}/match-teams"): (MEMBER, {"teams": [[1], [2]]}, None),
    ("POST", "/teams/{team_id}/sessions/{session_id}/match-teams/suggest"): (MEMBER, None, None),
    ("PUT", "/teams/{team_id}/sessions/{session_id}/attendance"): (MEMBER, "attendance", None),
    ("DELETE", "/teams/{team_id}/sessions/{session_id}"): (MEMBER, None, None),
    ("GET", "/teams/{team_id}/drills"): (MEMBER, None, None),
    ("POST", "/teams/{team_id}/drills"): (MEMBER, "team_drill", None),
    ("PUT", "/teams/{team_id}/drills/{slug}"): (MEMBER, "team_drill", None),
    ("POST", "/teams/{team_id}/drills/{slug}/submit"): (MEMBER, {"confirm_own": True}, None),
    ("POST", "/teams/{team_id}/drills/{slug}/unlink"): (MEMBER, None, None),
    ("DELETE", "/teams/{team_id}/drills/{slug}"): (MEMBER, None, None),
    ("GET", "/admin/drill-submissions"): (ADMIN, None, None),
    ("POST", "/admin/drill-submissions/{submission_id}/accept"): (ADMIN, {}, None),
    ("POST", "/admin/drill-submissions/{submission_id}/decline"): (ADMIN, {"reason": "Duplicate"}, None),
    ("GET", "/admin/drill-submissions/{submission_id}/row"): (ADMIN, None, None),
    ("GET", "/teams/{team_id}/session-templates"): (MEMBER, None, None),
    ("POST", "/teams/{team_id}/session-templates"): (MEMBER, "template", None),
    ("PUT", "/teams/{team_id}/session-templates/{template_id}"): (MEMBER, "template", None),
    ("DELETE", "/teams/{team_id}/session-templates/{template_id}"): (MEMBER, None, None),
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
    session = owner.post(f"/teams/{team_id}/sessions", json={"period_id": period_id, "date": "2026-10-20", "length": 60,
                         "focus_tags": ["passing_short"], "player_ids": [player_id]}, headers=headers).json()
    template = {"name": "Short", "length": 30, "minutes": {"warm_up": 10, "small_sided_game": 20}}
    template_id = owner.post(f"/teams/{team_id}/session-templates", json=template, headers=headers).json()["id"]
    team_drill = {"title": "Passing square", "session_phase": "technical", "format": "small_group", "players": [4, 8, 12], "ages": [8, 14],
                  "duration": [10, 15], "intensity": "medium", "setup": "A square.", "instructions": ["Pass."], "tags": {"passing_short": 1.0}}
    drill_slug = owner.post(f"/teams/{team_id}/drills", json=team_drill, headers=headers).json()["slug"]
    practice = owner.post(f"/teams/{team_id}/players/{player_id}/practice/assignments", json={"topic": "defending_off_ball", "stage": 1}, headers=headers).json()
    ids = {"team_id": team_id, "template_id": template_id, "player_id": player_id, "period_id": period_id, "session_id": session["id"], "block_id": session["blocks"][-1]["id"],
           "assessment_id": assessment_id, "member_user_id": owner_id,
           "version_id": owner.get(f"/teams/{team_id}/periods").json()[0]["matrix_version_id"], "slug": drill_slug,
           "invite_id": 0, "suggestion_id": 0, "request_id": 0, "submission_id": 0, "report_id": 0,
           "assignment_id": practice["assignments"][0]["id"], "poll_id": "press-or-cover", "scenario_id": "byline-in-box", "respondent": "r" * 20}

    def call(client, csrf, method, path, body, query):
        url = path.format(**ids)
        params = {k: v.format(**ids) for k, v in query.items()} if query else None
        json_body = ({**assessment, "version": 1} if body == "assessment"
                     else {"period_id": ids["period_id"]} if body == "plan"
                     else {"period_id": ids["period_id"], "skill_id": "passing_short", "slot": "club", "action": "reset"} if body == "slot"
                     else {"period_id": ids["period_id"], "date": "2026-10-20", "length": 60, "focus_tags": ["passing_short"], "player_ids": [ids["player_id"]]} if body == "session"
                     else {"players": [{"player_id": ids["player_id"], "attended": True}]} if body == "attendance"
                     else template if body == "template"
                     else team_drill if body == "team_drill"
                     else body)
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
        if level == ADMIN:
            # Team owners are not site admins.
            expected += [(owner, owner_csrf, 403), (coach, coach_csrf, 403)]
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

"""Coaches suggesting videos for drills."""
import pytest
from app import video_links
from app.database import SessionLocal
from app.drills import DATA_DIR, load_file
from app.models import DrillVideoSuggestion
from test_flows import clean_database, signed_in

SUGGEST = "/drills/rondo-4v1/video-suggestions"


def test_links_are_read_from_youtube_and_vimeo_urls():
    parse = video_links.parse
    assert parse("https://youtu.be/abcdefghijk?t=1m30s") == video_links.VideoLink("youtube", "abcdefghijk", "https://www.youtube.com/watch?v=abcdefghijk", 90)
    assert parse("https://m.youtube.com/watch?v=abcdefghijk&t=45").start_seconds == 45
    assert parse("https://www.youtube.com/shorts/abcdefghijk").url == "https://www.youtube.com/shorts/abcdefghijk"
    assert parse("https://vimeo.com/channels/staff/123456").url == "https://vimeo.com/123456"
    for bad in ("https://example.com/watch?v=abcdefghijk", "https://www.youtube.com/watch?v=short", "javascript:alert(1)", "not a link"):
        assert parse(bad) is None


@pytest.fixture
def library():
    clean_database()
    with SessionLocal() as db:
        load_file(db, DATA_DIR / "drills_v1.json")


def test_coaches_suggest_videos_for_review(monkeypatch, library):
    looked_up = []
    def lookup(link):
        looked_up.append(link.url)
        if link.video_id == "privateone1":
            raise video_links.VideoUnavailable()
        if link.video_id == "offline0001":
            raise video_links.LookupFailed()
        return video_links.VideoDetails("4v1 rondo for beginners", "A coaching channel", None)
    monkeypatch.setattr(video_links, "lookup", lookup)
    coach, csrf = signed_in("video-coach@example.com", monkeypatch)
    headers = {"x-csrf-token": csrf}
    variation = coach.get("/drills/rondo-4v1").json()["variations"][2]

    made = coach.post(SUGGEST, json={"url": "https://youtu.be/abcdefghijk?t=20", "variation_id": variation["id"], "note": "  Shows the rotation well "}, headers=headers)
    assert made.status_code == 201, made.text
    assert made.json() | {"id": 0, "created_at": None} == {
        "id": 0, "drill_slug": "rondo-4v1", "drill_title": "4v1 rondo", "variation_title": variation["title"],
        "url": "https://www.youtube.com/watch?v=abcdefghijk", "title": "4v1 rondo for beginners", "channel": "A coaching channel",
        "status": "pending", "reject_reason": None, "reject_note": None, "created_at": None, "reviewed_at": None}
    with SessionLocal() as db:
        row = db.get(DrillVideoSuggestion, made.json()["id"])
        assert (row.start_seconds, row.note, row.host, row.video_id) == (20, "Shows the rotation well", "youtube", "abcdefghijk")

    # Pending suggestions aren't shown on the drill.
    assert coach.get("/drills/rondo-4v1").json()["media"] == coach.get("/drills/rondo-4v1").json()["media"]
    assert [s["title"] for s in coach.get("/me/video-suggestions").json()] == ["4v1 rondo for beginners"]

    def refused(body, status, words):
        response = coach.post(SUGGEST, json=body, headers=headers)
        assert response.status_code == status and words in response.json()["detail"], response.text
    refused({"url": "https://www.youtube.com/watch?v=abcdefghijk"}, 409, "waiting for review")  # same video, other form
    refused({"url": "https://example.com/video"}, 422, "YouTube or Vimeo")
    refused({"url": "https://youtu.be/privateone1"}, 422, "isn't public")
    refused({"url": "https://youtu.be/offline0001"}, 503, "try again")
    refused({"url": "https://youtu.be/bbbbbbbbbbb", "variation_id": 999999}, 422, "variation")
    curated = next(m["url"] for m in coach.get("/drills/rondo-4v1").json()["media"] if m["kind"] == "video")
    refused({"url": curated}, 409, "already on this drill")
    assert coach.post("/drills/no-such-drill/video-suggestions", json={"url": "https://youtu.be/bbbbbbbbbbb"}, headers=headers).status_code == 404

    # Another coach can't suggest the same video, and sees only their own suggestions.
    other, other_csrf = signed_in("video-other@example.com", monkeypatch)
    assert other.post(SUGGEST, json={"url": "https://youtu.be/abcdefghijk"}, headers={"x-csrf-token": other_csrf}).status_code == 409
    assert other.get("/me/video-suggestions").json() == []

    # At most ten waiting for review.
    for n in range(9):
        assert coach.post(SUGGEST, json={"url": f"https://youtu.be/cccccccccc{n}"}, headers=headers).status_code == 201
    refused({"url": "https://youtu.be/ddddddddddd"}, 429, "waiting for review")

    # Deleting the account keeps the suggestions, without saying who made them.
    assert coach.post("/auth/delete-account", json={"password": "secure-password-123"}, headers=headers).status_code == 200
    with SessionLocal() as db:
        rows = db.query(DrillVideoSuggestion).all()
        assert len(rows) == 10 and all(r.suggested_by is None for r in rows)

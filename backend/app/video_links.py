"""Links to drill videos: which host and video a link points at, and the video's details from the host.

Only YouTube and Vimeo are accepted, the same hosts the drill data files may use. Looking a video up sends the
host nothing but the video's link."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VIMEO_HOSTS = {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
LOOKUP_TIMEOUT_SECONDS = 5


class VideoUnavailable(Exception):
    """The host says the video doesn't exist, is private, or can't be embedded."""


class LookupFailed(Exception):
    """The host couldn't be reached; trying again later may work."""


@dataclass
class VideoLink:
    host: str  # "youtube" or "vimeo"
    video_id: str
    url: str  # canonical link, stored and embedded
    start_seconds: int | None = None


@dataclass
class VideoDetails:
    title: str
    channel: str
    duration_seconds: int | None


def _seconds(value: str | None) -> int | None:
    """A start time as YouTube writes it: '90', '90s' or '1m30s'."""
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?", value or "")
    if not value or not match:
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def parse(url: str) -> VideoLink | None:
    """The video a YouTube or Vimeo link points at, or None for anything else."""
    try:
        parts = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host, path = parts.hostname.lower(), [p for p in parts.path.split("/") if p]
    query = urllib.parse.parse_qs(parts.query)
    if host in YOUTUBE_HOSTS:
        if host == "youtu.be":
            video_id, shorts = (path[0] if path else None), False
        elif path and path[0] in ("shorts", "embed", "live") and len(path) > 1:
            video_id, shorts = path[1], path[0] == "shorts"
        else:
            video_id, shorts = (query.get("v") or [None])[0], False
        if not video_id or not YOUTUBE_ID.match(video_id):
            return None
        canonical = f"https://www.youtube.com/shorts/{video_id}" if shorts else f"https://www.youtube.com/watch?v={video_id}"
        return VideoLink("youtube", video_id, canonical, _seconds((query.get("t") or query.get("start") or [None])[0]))
    if host in VIMEO_HOSTS:
        video_id = next((p for p in reversed(path) if p.isdigit()), None)
        if not video_id:
            return None
        return VideoLink("vimeo", video_id, f"https://vimeo.com/{video_id}")
    return None


def lookup(link: VideoLink) -> VideoDetails:
    """The video's title, channel and (Vimeo only) length, from the host's oEmbed endpoint."""
    endpoint = "https://www.youtube.com/oembed" if link.host == "youtube" else "https://vimeo.com/api/oembed.json"
    request = urllib.request.Request(f"{endpoint}?format=json&url={urllib.parse.quote(link.url, safe='')}",
                                     headers={"User-Agent": "TapLine-IDP"})
    try:
        with urllib.request.urlopen(request, timeout=LOOKUP_TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        # oEmbed answers 401/403 for private or non-embeddable videos and 400/404 for missing ones.
        if error.code in (400, 401, 403, 404):
            raise VideoUnavailable() from error
        raise LookupFailed() from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise LookupFailed() from error
    duration = data.get("duration")
    return VideoDetails(title=str(data.get("title") or "Untitled video")[:200],
                        channel=str(data.get("author_name") or "")[:120],
                        duration_seconds=int(duration) if isinstance(duration, (int, float)) else None)

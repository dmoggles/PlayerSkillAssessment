"""Check a drills data file before it's committed: the loader's own checks, plus what only shows across files.

Usage (from the repo root):
  DATABASE_URL=postgresql+psycopg://x:y@localhost/z PUBLIC_BASE_URL=http://x SMTP_HOST=x \
    backend/.venv/bin/python .claude/skills/write-up-drill/scripts/check.py backend/app/data/drills_vN.json [--slug SLUG ...]

--slug: the library slugs reserved by accepted submissions; each must be in the file, spelled exactly.
Exits 1 when there's anything to fix.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))
from app.drills import DATA_DIR, drill_problems  # noqa: E402

args = sys.argv[1:]
reserved = [args[i + 1] for i, a in enumerate(args) if a == "--slug" and i + 1 < len(args)]
files = [Path(a) for i, a in enumerate(args) if a != "--slug" and (i == 0 or args[i - 1] != "--slug")]
if len(files) != 1:
    sys.exit(__doc__)
path = files[0]
data = json.loads(path.read_text())
active = {t["id"] for t in json.loads((ROOT / "backend/migrations/data/skill_tags_v1.json").read_text())}
problems = []
if data.get("source_version") != path.stem:
    problems.append(f"source_version should be {path.stem!r}, the file's name")
others = {}
for other in sorted(DATA_DIR.glob("drills_v*.json")):
    if other.resolve() != path.resolve():
        for d in json.loads(other.read_text())["drills"]:
            others[d["slug"]] = other.name
slugs = [d.get("slug") for d in data["drills"]]
for d in data["drills"]:
    slug = d.get("slug")
    problems += [f"{slug}: {p}" for p in drill_problems(d, active)]
    if slug in others:
        problems.append(f"{slug}: already in {others[slug]} (a drill never moves between files: the loader would retire it there)")
    if re.match(r"t\d+-", slug or ""):
        problems.append(f"{slug}: looks like a team drill's slug; use the library slug the submission reserved")
    for link in d.get("links", []):
        if link.get("to") not in slugs and link.get("to") not in others:
            problems.append(f"{slug}: link to unknown drill {link.get('to')}")
    diagrams = sum(1 for m in d.get("media", []) if m.get("kind") == "diagram")
    if not diagrams and d.get("session_phase") not in ("warm_up", "cool_down") and not d.get("home_friendly"):
        problems.append(f"{slug}: no diagram (library drills for a group have one)")
problems += [f"duplicate slug {s}" for s in {s for s in slugs if slugs.count(s) > 1}]
problems += [f"reserved slug {s} is not in the file" for s in reserved if s not in slugs]
for p in problems:
    print(p)
print(f"{path.name}: {len(data['drills'])} drills, " + ("no problems" if not problems else f"{len(problems)} to fix"))
sys.exit(1 if problems else 0)

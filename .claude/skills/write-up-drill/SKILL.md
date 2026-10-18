---
name: write-up-drill
description: Turn a team drill that an admin accepted for the shared library into a library drill, with diagrams, videos and the user's review, in the next drills_vN.json. Use when the user has accepted a drill submission, or pastes or downloads a submission's data-file row.
---

# Write up an accepted drill for the shared library

A coach's drill has text and maybe a video link, but no diagrams, and its versions are whatever the coach wrote. An
admin accepting it in **Settings → Drill submissions** only reserves a **library slug**. It reaches the library when
a data file with exactly that slug is deployed: the loader then marks the submission published and the team sees
"Now in the shared library". This skill does the write-up in between. The user reviews everything before it's
committed. Follow the steps in order, and stop where a step says to wait.

## 1. Get the row
- Ask for the submission's row if you don't have it. In Drill submissions → **Being written up**, **Download row**
  gives `<library-slug>.json`. The user pastes it or puts it in the repo.
- Note the `slug`. It's the reserved library slug and must stay exactly as it is, or the submission is never published.
- Several accepted drills can go in one batch.

## 2. Research and plan (then wait)
- Read [content-rules.md](content-rules.md). Each rule came from the user's reviews.
- Look for duplicates or near-duplicates in `backend/app/data/drills_v*.json`: titles, tags and how the drill runs.
  Say if one is close; the user may decide to decline instead.
- Research how coaches run this kind of drill, and check that its set-up, numbers, space, ages and coaching points are sound.
- Present a plan to the user and **wait for their go-ahead** before building. The plan covers:
  - the title (literal), summary, part of the session, players, ages, minutes and space;
  - the tags with weights, and `ladder_tags` if the versions don't describe every tag;
  - the versions, each with its levels and what it changes. Keep the coach's versions where they're sound, and add
    an easier or harder one where it helps;
  - which versions get their own diagram, and what each diagram shows, step by step;
  - what you changed from the coach's version, and why. Keep the drill recognisably theirs.

## 3. Build
- **Which file:** new drills go in a new `backend/app/data/drills_v{N+1}.json` (`"source_version": "drills_v{N+1}"`),
  unless the user says to add them to a batch that hasn't been released yet. Never move a drill that's already in
  another file: the loader would retire it there.
- **Diagrams** use the diagram format in `backend/app/drills.py` (`diagram_problems` lists the rules): a pitch in
  metres, objects (players with team A, B or N, cones, one ball, mannequins, walls), and steps of pass, run,
  dribble, shot and move actions.
- **The coach's video:** keep it out of the file for now. It's one candidate for step 5, checked like any other.
- **Check the file:**
  ```
  DATABASE_URL=postgresql+psycopg://x:y@localhost/z PUBLIC_BASE_URL=http://x SMTP_HOST=x \
    backend/.venv/bin/python .claude/skills/write-up-drill/scripts/check.py backend/app/data/drills_vN.json --slug <library-slug>
  ```
  This runs the loader's checks, and also checks for slugs already in other files, the reserved slug being present,
  and group drills without a diagram. Fix everything it reports.

## 4. Review sheet (then wait)
- Render every diagram, step by step, in the scratchpad:
  ```
  node .claude/skills/write-up-drill/scripts/sheet.mjs backend/app/data/drills_vN.json <scratch>/sheet.html <slug>
  PW_DIR=<scratch>/pw node .claude/skills/write-up-drill/scripts/shot.mjs <scratch>/sheet.html <scratch>/sheet.png
  ```
  The first time, run `npm install --prefix <scratch>/pw playwright-core`.
- **Look at the PNG yourself first**, against the diagram rules:
  - is the base diagram free of anything the harder versions add?
  - do off-ball players move?
  - is the direction of play right?
  - is there one ball?
  - do any frames make shapes that could read as symbols?
  - Fix and re-render as needed.
- Send the user the sheet with SendUserFile, with the full text of each drill (set-up, steps, coaching points,
  versions). **Wait for their approval** and make the changes they ask for.

## 5. Videos (then wait)
- Find 2–4 candidates for each drill, plus the coach's own link if there was one, following the video rules in
  content-rules.md (oEmbed check, length, drill demo or tutorial, mismatches).
- The user picks. Add only what they choose. If nothing is good enough yet, leave it out, or use a stopgap with
  `needs_better_video`.

## 6. Ship
- Re-run `check.py`, then run the backend tests.
- Commit the data file on its own ("Add <title> to the drill library, from a team's submission"), and push to main,
  which deploys to dev. Watch the deploy with `gh run watch`.
- **Tell the user what to check on dev:**
  - the drill is in the library with its diagrams;
  - the submitting team's drill says "Now in the shared library" with a link;
  - the submission is under **In the library** in Drill submissions.
- On production, it publishes with the next release. Production releases happen only when the user asks.

## When it doesn't fit
- **Not good enough for the library,** or a duplicate: tell the user. They can **Decline** it with a reason the team
  sees. Declining frees the reserved slug.
- **The slug needs to change** (a misleading name): the user declines and accepts again with a new library slug.
  Don't change it in the file on your own.

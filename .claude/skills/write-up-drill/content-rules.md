# Drill content rules

Every library drill meets these, whoever first wrote it. Each rule came from a problem the user found while
reviewing drills. Check every drill against all of them before showing it to the user.

## Versions
1. **The base describes only the base.** Its set-up, steps, equipment and diagram never include what a harder version
   adds (the first goalkeeper drill wrongly put angled strikes in the base).
2. **Each version adds one clear new demand.** Order: easier (regression), base, harder (escalators). Levels on the 1–5
   scale continue from one version to the next without a gap.
3. **Overrides replace, not merge.** A version overrides set-up, equipment, steps, coaching points, players or space
   only where it really changes them, and gives the whole new value.
4. **Check each tag against the ladder.** If the harder versions don't make the drill harder for a tag (a 1v1 drill
   escalates for the attacker, not the defender), set `ladder_tags` to only the tags the versions describe. Use
   `"ladder_tags": []` for a set programme whose versions follow no rating.

## Diagrams
5. **A version that changes what happens on the pitch gets its own diagram** (extra players, new movement, a new
   pattern). Versions that only change speed, space, touches or rules share the one below them.
6. **Movement is coordinated.** In group drills, show off-ball players moving to support during every pass, not
   standing still ("movement is a little uncoordinated").
7. **The direction of play matches the game** situation the drill trains (a throw-in drill attacks along the
   touchline towards the end line, not straight away from it).
8. **Look at the paths as a whole shape, across all frames.** Avoid rotationally symmetric patterns of bent paths that
   can read as symbols: four players each running an edge and then turning in drew a swastika. Use odd numbers of
   players, uneven starts, mixed directions and straight walk-ins.
9. **One ball per diagram.** Handling and saving drills end with the ball in the keeper's hands, not in the goal.
10. **Captions say what the diagram simplifies** ("the diagram follows one pair").

## Names and words
11. **Literal names**: say what players do. No metaphors that could be mistaken for equipment ("goalkeeper handling
    ladder" was rejected: "there's no ladder").
12. Written for coaches, in plain UK English.

## Home drills
13. A home drill works alone or with a parent who only rolls or throws. Every one has an `indoors` text (a soft or
    futsal ball, household items, no full-power shots, no heading, no diving indoors). Use `wall` objects and `via`
    passes in diagrams. Skip the diagram for on-the-spot touches (ball mastery, keep-ups) and let a video show them.

## Videos
14. **Drill demos, not player tutorials.** The videos are for coaches setting a drill up on the field: short clips
    from coaching channels showing how the drill runs. Search drill, session or practice videos.
15. **Check every candidate** with YouTube or Vimeo oEmbed (title, channel) and its page description, and list its
    length prominently. Label each "drill demo" or "technique tutorial". Say in the caption where the video differs
    from our drill (a 5 × 5 m square against our 10 × 10 m).
16. **The user picks every video.** Never add one they haven't approved. A stopgap gets `"needs_better_video": true`;
    `python -m app.drills --video-report` lists those and drills with no video.

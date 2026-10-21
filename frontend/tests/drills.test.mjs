import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { loadJsx } from './helpers.mjs'

test('animated diagrams replay passes, runs, dribbles and shots into positions over time', async () => {
  const { buildTimeline, frameAt, stepArrows, ease } = await loadJsx('src/diagramModel.js')
  const { videoEmbedUrl } = await loadJsx('src/drillModel.js')
  const { default: DiagramPlayer } = await loadJsx('src/DiagramPlayer.jsx')
  const diagram = {
    pitch: { width: 10, length: 20, goals: [{ id: 'goal', at: [5, 20] }] },
    objects: { A: { type: 'player', team: 'A', at: [2, 2] }, B: { type: 'player', team: 'A', at: [8, 10] }, c: { type: 'cone', at: [5, 5] }, ball: { type: 'ball', with: 'A' } },
    steps: [
      { label: 'Pass while B runs', actions: [{ pass: { from: 'A', to: 'B' } }, { run: { who: 'B', to: [8, 12] } }] },
      { label: 'B dribbles', actions: [{ dribble: { who: 'B', to: [6, 16] } }] },
      { label: 'Shoot', actions: [{ shot: { who: 'B', to: 'goal' } }] },
    ],
  }
  const timeline = buildTimeline(diagram)
  assert.equal(timeline.states.length, 4)
  assert.deepEqual(timeline.states[1].positions.B, [8, 12])
  assert.equal(timeline.states[1].holder, 'B')
  assert.deepEqual(timeline.steps[0].ballMove.to, [8.45, 12.35], 'the pass meets the receiver where the run ends')
  assert.deepEqual(frameAt(timeline, 1, 0).positions.B, [8, 12])
  assert.deepEqual(frameAt(timeline, 1, 1).positions.B, [6, 16])
  assert.deepEqual(frameAt(timeline, 2, 1).ball, [5, 20], 'shots end in the goal')
  assert.deepEqual(buildTimeline({ ...diagram, steps: [{ label: 'Corner', actions: [{ shot: { who: 'A', to: [6, 20] } }] }] }).steps[0].ballMove.to, [6, 20], 'or at a point, such as a corner of the goal')
  assert.deepEqual(stepArrows(timeline, 0).map(a => a.kind), ['run', 'pass'])
  // A pass off a wall goes out to the wall, then back to the receiver, with an arrow for each leg.
  const wall = buildTimeline({ ...diagram, objects: { ...diagram.objects, W: { type: 'wall', at: [0, 0], to: [10, 0] } }, steps: [{ label: 'Off the wall', actions: [{ pass: { from: 'A', to: 'A', via: [2, 0] } }] }] })
  assert.deepEqual(frameAt(wall, 0, 0.5).ball, [2, 0], 'at the wall halfway through the step')
  assert.deepEqual(frameAt(wall, 0, 1).ball, [2.45, 2.35], 'back at the passer\'s feet')
  assert.deepEqual(stepArrows(wall, 0).map(a => [a.from, a.to]), [[[2.45, 2.35], [2, 0]], [[2, 0], [2.45, 2.35]]])
  assert.equal(ease(0), 0); assert.equal(ease(1), 1); assert.equal(ease(0.5), 0.5)

  const html = renderToStaticMarkup(React.createElement(DiagramPlayer, { diagram, caption: 'Test drill' }))
  assert.match(html, /role="img" aria-label="Test drill\. Step 1 of 3: Pass while B runs"/)
  assert.match(html, /diagram-arrow-run/)
  assert.match(html, /diagram-cone/)
  assert.match(renderToStaticMarkup(React.createElement(DiagramPlayer, { diagram: { ...diagram, objects: { ...diagram.objects, W: { type: 'wall', at: [0, 0], to: [10, 0] } } } })), /<line[^>]*class="diagram-wall"/)
  // It opens before step 1 has happened: A still has the ball and B has not run yet.
  assert.match(html, /<circle cx="142" cy="174" r="10"/, 'B at its starting spot')
  assert.match(html, /<circle cx="53.2" cy="51.6" r="4.5" class="diagram-ball"/, 'the ball with A')

  assert.equal(videoEmbedUrl('https://www.youtube.com/watch?v=abc123', 30), 'https://www.youtube-nocookie.com/embed/abc123?autoplay=1&rel=0&start=30')
  assert.equal(videoEmbedUrl('https://youtu.be/xyz'), 'https://www.youtube-nocookie.com/embed/xyz?autoplay=1&rel=0')
  assert.equal(videoEmbedUrl('https://vimeo.com/76979871'), 'https://player.vimeo.com/video/76979871?autoplay=1&dnt=1')
  assert.equal(videoEmbedUrl('https://example.com/video'), null)
  assert.equal(videoEmbedUrl('https://www.youtube.com/shorts/BIHD3HOH040'), 'https://www.youtube-nocookie.com/embed/BIHD3HOH040?autoplay=1&rel=0')
  const { isVerticalVideo } = await loadJsx('src/drillModel.js')
  assert.equal(isVerticalVideo('https://www.youtube.com/shorts/BIHD3HOH040'), true)
  assert.equal(isVerticalVideo('https://www.youtube.com/watch?v=abc'), false)
})

test('a chosen variation shows its own content where it overrides the drill, and the drill content otherwise', async () => {
  const { effectiveDrill } = await loadJsx('src/drillModel.js')
  const drill = { setup: 'Base setup', equipment: [{ item: 'cones', quantity: 4 }], instructions: ['Base step'], coaching_points: ['Base point'], players: [5, 5, 15], space: [10, 10] }
  const base = effectiveDrill(drill, { setup: null, equipment: null, instructions: null, coaching_points: null, players: null, space: null })
  assert.equal(base.setup, 'Base setup'); assert.equal(base.changed.size, 0)
  const harder = effectiveDrill(drill, { setup: 'Two defenders', equipment: null, instructions: null, coaching_points: ['Split them'], players: [6, 6, 18], space: [10, 10] })
  assert.deepEqual([harder.setup, harder.instructions, harder.coaching_points, harder.players], ['Two defenders', ['Base step'], ['Split them'], [6, 6, 18]])
  assert.deepEqual([...harder.changed].sort(), ['coaching_points', 'players', 'setup'], 'an override equal to the drill is not marked as changed')
  assert.equal(effectiveDrill(drill, undefined).setup, 'Base setup')
})

test('a variation without its own diagram inherits outward from the base version', async () => {
  const { variationDiagram } = await loadJsx('src/drillModel.js')
  const drill = {
    media: [{ id: 10, kind: 'diagram' }, { id: 11, kind: 'diagram' }, { id: 12, kind: 'diagram' }, { id: 13, kind: 'video' }],
    variations: [
      { id: 1, kind: 'regression', diagram_media_id: null },
      { id: 2, kind: 'regression', diagram_media_id: 12 },
      { id: 3, kind: 'base', diagram_media_id: null },
      { id: 4, kind: 'escalator', diagram_media_id: 11 },
      { id: 5, kind: 'escalator', diagram_media_id: null },
    ],
  }
  assert.equal(variationDiagram(drill, drill.variations[2]).id, 10, 'base: the drill first diagram, not an easier one')
  assert.equal(variationDiagram(drill, drill.variations[3]).id, 11, 'escalator: its own')
  assert.equal(variationDiagram(drill, drill.variations[4]).id, 11, 'escalator: inherits from the one below')
  assert.equal(variationDiagram(drill, drill.variations[1]).id, 12, 'regression: its own')
  assert.equal(variationDiagram(drill, drill.variations[0]).id, 12, 'regression: inherits from the one above')
  assert.equal(variationDiagram({ media: [], variations: [] }, undefined), null)
})

test('a variation shows its own video first, plus drill-wide videos no variation claims', async () => {
  const { visibleVideos } = await loadJsx('src/drillModel.js')
  const drill = {
    media: [{ id: 1, kind: 'diagram' }, { id: 2, kind: 'video', url: 'a' }, { id: 3, kind: 'video', url: 'b' }],
    variations: [{ id: 10, video_media_id: null }, { id: 11, video_media_id: 3 }],
  }
  assert.deepEqual(visibleVideos(drill, drill.variations[0]).map(v => v.id), [2], 'a claimed video is hidden elsewhere')
  assert.deepEqual(visibleVideos(drill, drill.variations[1]).map(v => [v.id, Boolean(v.forVariation)]), [[3, true], [2, false]])
})

test('drill filters combine, and equipment means "needs nothing beyond what I have" (balls, bibs and cones assumed)', async () => {
  const { EMPTY_FILTERS, activeFilterCount, filterOptions, matchesFilters } = await loadJsx('src/drillModel.js')
  const rondo = { title: 'Rondo 4v1', summary: 'Keep the ball', session_phase: 'technical', format: 'small_group', intensity: 'medium', players: [5, 5, 15], ages: [8, 16], levels: [1, 5], duration: [10, 15], home_friendly: false, equipment_items: ['balls', 'bibs', 'cones', 'mannequins'], tags: [{ id: 'passing_short', label: 'Short passing', area: 'technical' }], votes: { likes: 0, dislikes: 0, mine: 1 } }
  const slalom = { ...rondo, title: 'Cone slalom', summary: 'Dribble', session_phase: 'warm_up', format: 'individual', players: [1, 1, 20], home_friendly: true, equipment_items: ['balls', 'cones'], tags: [{ id: 'dribbling', label: 'Dribbling', area: 'technical' }], votes: { likes: 0, dislikes: 0, mine: 0 } }
  const match = changes => [rondo, slalom].filter(d => matchesFilters(d, { ...EMPTY_FILTERS, ...changes })).map(d => d.title)
  assert.deepEqual(match({}), ['Rondo 4v1', 'Cone slalom'])
  assert.deepEqual(match({ text: 'short PASS' }), ['Rondo 4v1'], 'search covers skill labels, ignoring case')
  assert.deepEqual(match({ players: '3' }), ['Cone slalom'], 'too few players for the rondo')
  assert.deepEqual(match({ players: '30' }), ['Rondo 4v1', 'Cone slalom'], 'a big squad splits into groups')
  assert.deepEqual(match({ equipment: ['goals'] }), ['Cone slalom'], 'the rondo also needs mannequins; balls, bibs and cones are assumed')
  assert.deepEqual(match({ equipment: ['mannequins'] }), ['Rondo 4v1', 'Cone slalom'])
  assert.deepEqual(match({ phase: 'warm_up' }), ['Cone slalom'])
  assert.deepEqual(match({ text: 'warm-up' }), ['Cone slalom'], 'search covers the part of the session')
  assert.deepEqual(match({ age: '17' }), [])
  assert.deepEqual(match({ duration: '8' }), [], 'both need at least 10 minutes')
  assert.deepEqual(match({ home: true, liked: true }), [])
  assert.deepEqual(match({ liked: true, area: 'technical', tag: 'passing_short', level: '3' }), ['Rondo 4v1'])
  assert.equal(activeFilterCount({ ...EMPTY_FILTERS, text: 'x', age: '12', equipment: ['balls'] }), 2, 'search is not counted as a filter')
  assert.deepEqual(filterOptions([rondo, slalom]).equipment, ['mannequins'], 'balls, bibs and cones are never choices')
  assert.deepEqual(filterOptions([rondo, slalom]).tags.map(t => t.label), ['Dribbling', 'Short passing'])
})

test("a coach's own vote outranks the global totals when ordering drills", async () => {
  const { sortDrills } = await loadJsx('src/drillModel.js')
  const drill = (title, likes, dislikes, mine) => ({ title, votes: { likes, dislikes, mine } })
  const order = sortDrills([drill('Popular but I dislike it', 9, 0, -1), drill('B unvoted', 0, 0, 0), drill('Popular', 5, 1, 0), drill('A unvoted', 0, 0, 0), drill('Unpopular but I like it', 0, 4, 1)])
  assert.deepEqual(order.map(d => d.title), ['Unpopular but I like it', 'Popular', 'A unvoted', 'B unvoted', 'Popular but I dislike it'])
})

test('playing groups: one shared group filters the library, a mixed squad shows its span, a new season moves everyone up', async () => {
  const { squadGroups, movedUp } = await loadJsx('src/dashboardModel.js')
  const players = [{ id: 1, active: true }, { id: 2, active: true }, { id: 3, active: true }, { id: 4, active: false }]
  assert.deepEqual(squadGroups(players, { 1: 11, 2: 11 }), { single: 11, span: null })
  assert.deepEqual(squadGroups(players, { 1: 10, 2: 12, 3: 11, 4: 15 }), { single: null, span: [10, 12] }, 'archived players do not count')
  assert.deepEqual(squadGroups(players, {}), { single: null, span: null })
  assert.deepEqual(movedUp(players, { 1: 10, 2: 21 }), { 1: '11', 2: '21', 3: '' }, 'capped at U21; no group stays unset; archived left out')
  const { auditText } = await loadJsx('src/auditModel.js')
  assert.equal(auditText({ action: 'playing_group_changed', actor_email: 'o@x', details: { player: 'Ana', period: 'Fall', from: 10, to: 11 } }), "o@x set Ana's playing group to U11 (Fall), was U10")
  assert.equal(auditText({ action: 'playing_group_changed', actor_email: 'o@x', details: { player: 'Ana', period: 'Fall', from: 11, to: null } }), "o@x cleared Ana's playing group (Fall)")
})

test('coaches are invited to suggest a video, more visibly when a drill has none', async () => {
  const { SuggestVideo } = await loadJsx('src/VideoSuggestions.jsx')
  const { SUGGESTION_STATUS, REJECT_REASONS } = await loadJsx('src/drillModel.js')
  const drill = { slug: 'rondo-4v1' }
  const none = renderToStaticMarkup(React.createElement(SuggestVideo, { drill, variation: { id: 1, kind: 'base', title: 'Base' }, prominent: true }))
  assert.match(none, /video-suggest prominent/)
  assert.match(none, /No video for this drill yet/)
  assert.match(none, /aria-expanded="false"[^>]*>Suggest a video</)
  const some = renderToStaticMarkup(React.createElement(SuggestVideo, { drill, variation: null }))
  assert.doesNotMatch(some, /No video for this drill yet/)
  assert.match(some, /class="link-btn"/)
  assert.deepEqual(Object.keys(SUGGESTION_STATUS), ['pending', 'approved', 'rejected', 'hidden'])
  assert.ok(Object.keys(REJECT_REASONS).includes('safeguarding'))
})

test('approved video suggestions follow the drill\'s own videos, for their variation or the whole drill', async () => {
  const { visibleVideos, hasVideo } = await loadJsx('src/drillModel.js')
  const drill = {
    variations: [{ id: 1, kind: 'base', video_media_id: null }, { id: 2, kind: 'escalator', video_media_id: 11 }],
    media: [{ id: 10, kind: 'video', url: 'a' }, { id: 11, kind: 'video', url: 'b' }, { id: 12, kind: 'diagram' }],
    suggested_videos: [{ id: 'suggested-1', url: 's1', variation_id: null }, { id: 'suggested-2', url: 's2', variation_id: 2 }],
  }
  const shown = variation => visibleVideos(drill, variation).map(v => `${v.url}${v.forVariation ? '*' : ''}${v.suggested ? '+' : ''}`)
  assert.deepEqual(shown(drill.variations[0]), ['a', 's1+'])
  assert.deepEqual(shown(drill.variations[1]), ['b*', 's2*+', 'a', 's1+'])
  assert.deepEqual(visibleVideos({ ...drill, suggested_videos: undefined }, drill.variations[0]).map(v => v.url), ['a'])
  assert.equal(hasVideo({ media: [], suggested_videos: [{ id: 'suggested-1' }] }), true)
  assert.equal(hasVideo({ media: [{ kind: 'diagram' }] }), false)
})

test('site admins review suggestions with a checklist before approving', async () => {
  const { default: VideoSuggestionQueue } = await loadJsx('src/areas/VideoSuggestionQueue.jsx')
  const { REVIEW_CHECKS } = await loadJsx('src/drillModel.js')
  const html = renderToStaticMarkup(React.createElement(VideoSuggestionQueue, { onMessage: () => {} }))
  assert.match(html, /Video suggestions/)
  assert.match(html, /Waiting for review/)
  assert.match(html, /Loading…/)
  assert.equal(REVIEW_CHECKS.length, 2)
  assert.match(REVIEW_CHECKS[1], /Unlisted/)
})

test('a suggestion can only be approved once the checklist is ticked, and an approved one can be taken down', async () => {
  const { SuggestionReview } = await loadJsx('src/areas/VideoSuggestionQueue.jsx')
  const item = { id: 7, drill_title: '4v1 rondo', variations: [{ id: 1, kind: 'base', title: 'Four around one' }], variation_id: 1,
    url: 'https://www.youtube.com/watch?v=abcdefghijk', start_seconds: null, title: 'Rondo demo', channel: 'Coaching channel', duration_seconds: null,
    note: 'Shows the rotation', suggested_by: 'coach@example.com', status: 'pending', caption: null, reject_reason: null, reject_note: null, reports: 0,
    created_at: '2026-10-17T10:00:00Z', reviewed_at: null }
  const render = props => renderToStaticMarkup(React.createElement(SuggestionReview, { item: { ...item, ...props }, onDone: () => {}, onMessage: () => {} }))
  const pending = render({})
  assert.match(pending, /Open on YouTube/)
  assert.match(pending, /by coach@example\.com/)
  assert.match(pending, /<blockquote>Shows the rotation<\/blockquote>/)
  assert.match(pending, /value="Rondo demo"/, 'the caption starts as the video title')
  assert.match(pending, /<button type="submit" class="primary-btn" disabled="">Approve/)
  assert.match(pending, /Turn down because/)
  const approved = render({ status: 'approved', caption: 'Rondo rotations' })
  assert.doesNotMatch(approved, />Approve</)
  assert.match(approved, />Take down</)
})

test("a team drill's form turns into the drill's fields, and back", async () => {
  const { emptyForm, formBody, formFromDrill, formProblems } = await loadJsx('src/teamDrillModel.js')
  const form = { ...emptyForm(), title: ' Four corners ', setup: 'A square.', instructions: ['Pass.', ' '], tags: { passing_short: 1 },
    equipment: { cones: '4', balls: '', goals: '0' }, space: ['15', ''], easier: { title: 'Two corners', change: 'Across a line.' }, harder: { title: '', change: '' } }
  assert.deepEqual(formProblems(form), [])
  const body = formBody(form)
  assert.equal(body.title, 'Four corners')
  assert.deepEqual(body.instructions, ['Pass.'])
  assert.deepEqual(body.equipment, [{ item: 'cones', quantity: 4 }], 'empty and zero quantities are left out')
  assert.equal(body.space, null, 'space needs both sides')
  assert.deepEqual(body.players, [4, 8, 12])
  assert.deepEqual(body.easier, { title: 'Two corners', change: 'Across a line.' })
  assert.equal(body.harder, null, 'an empty version is left out')
  assert.deepEqual(formProblems({ ...form, tags: {} }), ['Choose at least one skill this drill mainly trains.'])
  assert.deepEqual(formProblems({ ...form, tags: {}, session_phase: 'warm_up' }), [], 'warm-ups needn\'t train a skill')
  assert.deepEqual(formProblems({ ...form, players: ['8', '4', '12'], easier: { title: 'X', change: '' } }),
    ['Players: the smallest number, the best number and the most, in that order.', 'The easier version needs a name and what changes.'])
  const drill = { title: 'Four corners', summary: '', session_phase: 'technical', format: 'small_group', players: [4, 8, 12], ages: [8, 14],
    duration: [10, 15], intensity: 'medium', space: null, equipment: [{ item: 'cones', quantity: 4 }], setup: 'A square.', instructions: ['Pass.'],
    coaching_points: [], tags: [{ id: 'passing_short', weight: 1 }], home_friendly: false, indoors: null,
    variations: [{ kind: 'regression', title: 'Two corners', change: 'Across a line.' }, { kind: 'base', title: 'Four corners', change: '' }],
    media: [{ kind: 'video', url: 'https://youtu.be/x' }] }
  const back = formBody(formFromDrill(drill))
  assert.deepEqual([back.easier, back.harder, back.video_url, back.coaching_points], [{ title: 'Two corners', change: 'Across a line.' }, null, 'https://youtu.be/x', []])
})

test('the drill editor and the team filter', async () => {
  const { default: TeamDrillForm } = await loadJsx('src/TeamDrillForm.jsx')
  const tags = [{ id: 'passing_short', label: 'Short passing', area: 'technical', active: true }]
  const html = renderToStaticMarkup(React.createElement(TeamDrillForm, { teamId: 1, initialTags: tags, onSaved: () => {}, onCancel: () => {}, onMessage: () => {} }))
  for (const text of ['Add a drill', 'Only your team&#x27;s coaches see this drill', 'Part of the session', 'Skills it trains', 'Short passing', 'Set-up', 'Steps',
    '+ Add easier version', '+ Add harder version', 'Can be done at home', 'Video', 'Give the drill a name.']) assert.ok(html.includes(text), text)
  const { EMPTY_FILTERS, matchesFilters } = await loadJsx('src/drillModel.js')
  const base = { title: 'A', summary: '', tags: [], format: 'team', players: [1, 1, 1], ages: [5, 20], levels: [1, 5], duration: [1, 1], votes: { mine: 0 } }
  assert.equal(matchesFilters({ ...base, team_id: null }, { ...EMPTY_FILTERS, mine: true }), false)
  assert.equal(matchesFilters({ ...base, team_id: 3 }, { ...EMPTY_FILTERS, mine: true }), true)
})

test('the admin queue shows a submitted drill in full, with accept and decline', async () => {
  const { SubmissionReview } = await loadJsx('src/areas/DrillSubmissionQueue.jsx')
  const drill = { title: 'Four corners', summary: 'Pass and follow.', session_phase: 'technical', format: 'small_group', players: [4, 8, 12], ages: [8, 14],
    duration: [10, 15], space: [15, 15], tags: [{ id: 'p', label: 'Short passing', weight: 1 }], setup: 'A square.', equipment: [{ item: 'cones', quantity: 4 }],
    instructions: ['Pass.'], coaching_points: ['Open up.'], variations: [{ id: 1, kind: 'base', title: 'Four corners', change: '' }, { id: 2, kind: 'escalator', title: 'One touch', change: 'One touch only.' }],
    media: [] }
  const render = item => renderToStaticMarkup(React.createElement(SubmissionReview, { item, onDone: () => {}, onMessage: () => {} }))
  const pending = render({ id: 1, status: 'pending', note: 'Works with U10s', team: 'Riverside', created_at: '2026-10-18T10:00:00Z', drill })
  for (const text of ['Four corners', 'From Riverside', 'Works with U10s', 'A square.', '4 cones', 'Harder: One touch', 'Accept for the library', 'Decline because']) assert.ok(pending.includes(text), text)
  const accepted = render({ id: 1, status: 'accepted', note: '', team: 'Riverside', created_at: '2026-10-18T10:00:00Z', library_slug: 'four-corners', drill })
  assert.ok(accepted.includes('Download row') && accepted.includes('library slug four-corners') && !accepted.includes('Accept for the library'))
})

test("a team's own version of a library drill starts from its words only, and the two link to each other", async () => {
  const { formFromLibrary } = await loadJsx('src/teamDrillModel.js')
  const library = { title: 'Rondo', summary: 'Keep it', session_phase: 'opposed', format: 'small_group', players: [5, 5, 15], ages: [8, 16], duration: [10, 15],
    intensity: 'medium', space: [10, 10], equipment: [], setup: 'A square.', instructions: ['Keep it.'], coaching_points: ['Move.'], tags: [{ id: 'p', weight: 1 }],
    home_friendly: false, indoors: null, media: [{ kind: 'video', url: 'https://youtu.be/x' }, { kind: 'diagram' }],
    variations: [{ kind: 'regression', title: 'Big square', change: 'Bigger.' }, { kind: 'regression', title: 'Two touch', change: 'Two touches.' },
      { kind: 'base', title: 'Rondo', change: '' }, { kind: 'escalator', title: 'One touch', change: 'One touch.' }, { kind: 'escalator', title: '5v2', change: 'Two defenders.' }] }
  const form = formFromLibrary(library)
  assert.deepEqual([form.easier.title, form.harder.title], ['Two touch', 'One touch'], 'the versions nearest the base')
  assert.equal(form.video_url, '', 'no videos copied')
  assert.equal(form.setup, 'A square.')

  const { TeamVersion, TeamDrillActions } = await loadJsx('src/DrillLibrary.jsx')
  const render = (C, props) => renderToStaticMarkup(React.createElement(C, { onOpen: () => {}, onMessage: () => {}, onDeleted: () => {}, onSubmitted: () => {}, ...props }))
  assert.match(render(TeamVersion, { drill: { team_versions: [] }, teamId: 1, onMakeVersion: () => {} }), /Make our own version/)
  assert.match(render(TeamVersion, { drill: { team_versions: [{ team_id: 1, slug: 't1-ours', title: 'Our rondo' }] }, teamId: 1, onMakeVersion: () => {} }), /Your team uses its own version of this drill.*Our rondo/)
  const ours = render(TeamDrillActions, { drill: { team_id: 1, slug: 't1-ours', title: 'Our rondo', submission: null, shadows: { slug: 'rondo', title: 'Rondo' } }, onEdit: () => {} })
  assert.match(ours, /Your team&#x27;s version of .*Rondo/)
  assert.ok(ours.includes('Unlink') && ours.includes('Use the library version instead') && !ours.includes('Submit to the shared library') && !ours.includes('>Delete<'))
})

test('coaches can report a library drill\'s videos, and site admins see what was reported', async () => {
  const { VideoLink } = await loadJsx('src/DrillLibrary.jsx')
  const { LINK_REPORT_REASONS } = await loadJsx('src/drillModel.js')
  const { default: LinkReportQueue } = await loadJsx('src/areas/LinkReportQueue.jsx')
  const video = { id: 1, url: 'https://www.youtube.com/watch?v=abcdefghijk', caption: 'A rondo' }
  const drill = { slug: 'rondo-4v1' }
  assert.match(renderToStaticMarkup(React.createElement(VideoLink, { video, reportOn: drill })), /aria-expanded="false"[^>]*>Report link</)
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(VideoLink, { video })), /Report link/)
  assert.match(renderToStaticMarkup(React.createElement(VideoLink, { video: { ...video, url: 'https://example.com/clip' }, reportOn: drill })), /Report link/)
  assert.deepEqual(Object.keys(LINK_REPORT_REASONS), ['dead', 'inappropriate', 'other'])
  const html = renderToStaticMarkup(React.createElement(LinkReportQueue, { onMessage: () => {} }))
  assert.match(html, /Reported links/)
  assert.match(html, /Hidden/)
})

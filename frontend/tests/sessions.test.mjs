import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { loadJsx } from './helpers.mjs'

test('sessions split into upcoming and past, with times for each block', async () => {
  const { blockTimes, focusChip, splitSessions, versionLabel } = await loadJsx('src/sessionModel.js')
  const sessions = [{ id: 1, date: '2026-10-10' }, { id: 2, date: '2026-10-20' }, { id: 3, date: '2026-10-18' }, { id: 4, date: '2026-10-01' }]
  const { upcoming, past } = splitSessions(sessions, '2026-10-18')
  assert.deepEqual(upcoming.map(s => s.id), [3, 2], 'today counts as upcoming, soonest first')
  assert.deepEqual(past.map(s => s.id), [1, 4], 'latest first')
  const blocks = [{ minutes: 10 }, { minutes: 15 }, { minutes: 50 }]
  assert.deepEqual(blockTimes(blocks), ['0′', '10′', '25′'])
  assert.deepEqual(blockTimes(blocks, '18:45'), ['18:45', '18:55', '19:10'])
  assert.equal(versionLabel({ kind: 'escalator', title: '4v2' }), 'Harder: 4v2')
  assert.equal(versionLabel(null), 'Base version')
  assert.equal(focusChip({ label: 'Short passing', players: 5 }), 'Short passing · 5 players')
})

test('the Sessions area is in the navigation and opens on the list', async () => {
  const { AREAS } = await loadJsx('src/dashboardModel.js')
  assert.ok(AREAS.some(a => a.id === 'sessions' && a.label === 'Sessions'))
  const { default: SessionsArea } = await loadJsx('src/areas/SessionsArea.jsx')
  const html = renderToStaticMarkup(React.createElement(SessionsArea, { team: { id: 1, name: 'Falcons' }, period: { id: 2, label: 'Autumn' }, players: [], onMessage: () => {} }))
  assert.match(html, /Training sessions/)
  assert.match(html, /Plan a session/)
  assert.match(html, /Loading sessions…/)
  const noPeriod = renderToStaticMarkup(React.createElement(SessionsArea, { team: { id: 1, name: 'Falcons' }, period: null, players: [], onMessage: () => {} }))
  assert.match(noPeriod, /Add a period in Settings to plan sessions/)
})

test('a session template must add up to its length, and lists its parts in session order', async () => {
  const { DEFAULT_BREAKDOWNS, breakdownText, templateProblems, templateTotal } = await loadJsx('src/sessionModel.js')
  for (const [length, minutes] of Object.entries(DEFAULT_BREAKDOWNS)) assert.equal(templateTotal(minutes), Number(length))
  assert.equal(breakdownText({ cool_down: 5, full_squad_game: 25, warm_up: '10', technical: '' }), 'Warm-up 10 · Full squad game 25 · Cool-down 5')
  const draft = { name: 'Match prep', length: '60', minutes: { warm_up: '10', opposed: '20', full_squad_game: '25', cool_down: '5', technical: '' } }
  assert.deepEqual(templateProblems(draft), [])
  assert.deepEqual(templateProblems({ ...draft, length: '70' }), ['The parts add up to 60 of 70 minutes.'])
  assert.deepEqual(templateProblems({ name: ' ', length: '10', minutes: { warm_up: '' } }),
    ['Give the template a name.', 'The length is 15 to 150 minutes.', 'Give at least one part some minutes.'])
})

test('the templates view lists the team templates, and the editor counts the minutes', async () => {
  const { TemplatesView } = await loadJsx('src/areas/SessionsArea.jsx')
  const templates = [{ id: 1, name: 'Match prep', length: 60, minutes: { warm_up: 10, opposed: 25, full_squad_game: 25 }, used: 2 }]
  const html = renderToStaticMarkup(React.createElement(TemplatesView, { team: { id: 1, name: 'Falcons' }, initial: templates, onBack: () => {}, onMessage: () => {} }))
  assert.match(html, /Session templates/)
  assert.match(html, /Match prep/)
  assert.match(html, /60 min · Warm-up 10 · Opposed 25 · Full squad game 25 · used for 2 sessions/)
  assert.match(html, /New template/)
  const empty = renderToStaticMarkup(React.createElement(TemplatesView, { team: { id: 1, name: 'Falcons' }, initial: [], onBack: () => {}, onMessage: () => {} }))
  assert.match(empty, /No templates yet/)
})

test('the paper report prints each block for the version used, with what it brings and a register', async () => {
  const { reportBlock, sessionEquipment } = await loadJsx('src/sessionModel.js')
  const drill = { title: 'Rondo', setup: 'A square', equipment: [{ item: 'balls', quantity: 4 }, { item: 'cones', quantity: 4 }], instructions: ['Pass'],
    coaching_points: ['Move'], players: [5, 5, 10], space: [10, 10],
    media: [{ id: 1, kind: 'diagram', diagram: {} }, { id: 2, kind: 'diagram', diagram: {} }],
    variations: [{ id: 10, kind: 'base', title: 'Rondo', change: 'The base' }, { id: 11, kind: 'escalator', title: 'Two touch', change: 'Two touches at most.',
      diagram_media_id: 2, equipment: [{ item: 'balls', quantity: 8 }] }] }
  const block = { drill: { slug: 'rondo', title: 'Rondo' }, together: false, versions: [{ variation_id: 11, kind: 'escalator', title: 'Two touch' }] }
  const single = reportBlock(block, drill, null)
  assert.deepEqual(single.versions, [{ label: 'Harder: Two touch.', change: 'Two touches at most.' }])
  assert.equal(single.diagram.id, 2, "the version's own diagram")
  assert.deepEqual(single.content.equipment, [{ item: 'balls', quantity: 8 }])
  const groups = [{ name: 'Group A' }, { name: 'Group B' }]
  const split = reportBlock({ ...block, versions: [block.versions[0], { variation_id: 10, kind: 'base', title: 'Rondo' }] }, drill, groups)
  assert.deepEqual(split.versions.map(v => v.label), ['Group A: Harder: Two touch.', 'Group B: Base: Rondo.'])
  assert.equal(split.diagram.id, 1, "groups on different versions: the drill's own diagram")
  assert.deepEqual(reportBlock({ drill: null, title: 'Match', versions: [] }, undefined, groups).versions, [])
  assert.deepEqual(sessionEquipment([single, split, { content: null }]), [{ item: 'balls', quantity: 8 }, { item: 'cones', quantity: 4 }])

  const { default: SessionReport } = await loadJsx('src/SessionReport.jsx')
  const session = { title: 'Passing', date: '2026-10-20', start_time: '18:30', length: 20, template: null, expected: 1, versions: 'single', groups: [], notes: '',
    focus: [{ tag_id: 'p', label: 'Short passing' }], attendance: [{ player_id: 1, name: 'Ana', expected: true, attended: null }],
    blocks: [{ id: 1, phase: 'technical', minutes: 15, ...block, notes: '' }, { id: 2, phase: 'cool_down', minutes: 5, drill: null, title: 'Stretches', versions: [], notes: 'Good' }] }
  const html = renderToStaticMarkup(React.createElement(SessionReport, { session, teamName: 'Falcons', drills: { rondo: { ...drill, media: [] } } }))
  assert.match(html, /Falcons · Training session/)
  assert.match(html, /18:30–18:45/)
  assert.match(html, /8 balls/)
  assert.match(html, /Harder: Two touch\./)
  assert.match(html, /Register/)
  assert.match(html, /Ana/)
  assert.match(html, /<strong>Note:<\/strong> Good/)
})

test('the full squad game shows two balanced teams, which the coach can change', async () => {
  const { teamSummary } = await loadJsx('src/sessionModel.js')
  const team = { name: 'Team 1', players: [{ id: 1, name: 'Ana', position_label: 'Goalkeeper' }, { id: 2, name: 'Cat', position_label: 'Defender' },
    { id: 3, name: 'Eve', position_label: 'Defender' }, { id: 4, name: 'Ivy', position_label: null }],
  positions: [{ position: 'goalkeeper', label: 'Goalkeeper', count: 1 }, { position: 'defender', label: 'Defender', count: 2 }, { position: null, label: 'Position not set', count: 1 }],
  average_level: 2.6, average_age_group: 10.5, unrated: 1 }
  assert.equal(teamSummary(team), '4 players · 1 Goalkeeper, 2 Defenders, 1 Position not set · Average U10.5 · Average level 2.6 (1 not assessed)')
  assert.equal(teamSummary({ ...team, average_age_group: 10, average_level: null, unrated: 4 }).split(' · ').slice(-2).join(' · '), 'U10 · Not assessed')

  const { MatchTeams } = await loadJsx('src/areas/SessionsArea.jsx')
  const match = { by: 'planner', teams: [team, { ...team, name: 'Team 2', players: team.players.map(p => ({ ...p, id: p.id + 10 })) }] }
  const html = renderToStaticMarkup(React.createElement(MatchTeams, { match, editing: false }))
  assert.match(html, />Suggested teams</)
  assert.match(html, /Team 2/)
  assert.match(html, /Ana<span class="muted"> · Goalkeeper/)
  assert.match(html, /Change teams/)
  const editing = renderToStaticMarkup(React.createElement(MatchTeams, { match: { ...match, by: 'coach' }, editing: true }))
  assert.match(editing, /Save teams/)
  assert.match(editing, /Team 1: 4 · Team 2: 4. Changing who.*s expected balances the teams again/)
  assert.match(renderToStaticMarkup(React.createElement(MatchTeams, { match: null })), /once at least two players are expected/)
})

test('a coach can rename a session', async () => {
  const { SessionName } = await loadJsx('src/areas/SessionsArea.jsx')
  const html = renderToStaticMarkup(React.createElement(SessionName, { title: 'Training match' }))
  assert.match(html, /Session name<input required="" maxLength="120" value="Training match"/)
  assert.match(html, /Save name/)
})

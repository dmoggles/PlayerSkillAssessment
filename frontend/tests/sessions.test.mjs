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

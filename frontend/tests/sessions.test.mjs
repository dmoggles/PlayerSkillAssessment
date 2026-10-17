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

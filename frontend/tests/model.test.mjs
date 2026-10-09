import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AREAS, PLAYER_DATA_TABS, assessmentSignature, playerDataTabs, canManageTeam, initialPeriodId, initialPlayerId } from '../src/dashboardModel.js'
import { errorMessage } from '../src/api.js'
import { loadJsx } from './helpers.mjs'

test('five distinct coach areas have URL-safe IDs and short phone labels', () => {
  assert.deepEqual(AREAS.map(area => area.id), ['assessment', 'player-data', 'team-data', 'development', 'settings'])
  assert.equal(new Set(AREAS.map(area => area.short)).size, 5)
  for (const area of AREAS) assert.match(area.id, /^[a-z-]+$/)
})

test('API validation errors become readable text without exposing submitted values', () => {
  const error = { response: { data: { detail: [{ type: 'value_error', loc: ['body', 'password'], msg: 'Value error', input: 'secret-value', ctx: {} }] } } }
  assert.equal(errorMessage(error), 'password: Value error')
  assert.equal(errorMessage({ response: { data: { detail: 'Not found' } } }), 'Not found')
  assert.equal(errorMessage({}), 'Request failed. Please try again.')
  assert.equal(errorMessage({ response: { data: { detail: { message: 'Fix these before publishing', problems: ['A needs a tag', 'B needs a name'] } } } }), 'Fix these before publishing: A needs a tag; B needs a name')
})

test('player data exposes all sub-tabs, including confirmed priorities and the report', () => {
  assert.deepEqual(PLAYER_DATA_TABS.map(([id]) => id), ['summary', 'comparison', 'progress', 'priorities', 'report'])
  assert.deepEqual(playerDataTabs(false).map(([id]) => id), ['summary', 'progress', 'priorities', 'report'], 'no Comparison tab without self-assessment')
  assert.equal(playerDataTabs(true).length, 5)
})

test('shared context chooses an active player and period, or a valid fallback', () => {
  assert.equal(initialPlayerId([{ id: 1, active: false }, { id: 2, active: true }]), '2')
  assert.equal(initialPlayerId([{ id: 1, active: false }]), '1')
  assert.equal(initialPlayerId([]), '')
  assert.equal(initialPeriodId([{ id: 3, is_active: false }, { id: 4, is_active: true }]), '4')
  assert.equal(initialPeriodId([]), '')
})

test('team management is owner-only and assessment edits change the draft signature', () => {
  assert.equal(canManageTeam({ role: 'owner' }), true)
  assert.equal(canManageTeam({ role: 'coach' }), false)
  assert.equal(canManageTeam(undefined), false)
  const baseline = assessmentSignature('defender', '', 'sometimes', { touch: 3 })
  assert.equal(assessmentSignature('defender', '', 'often', { touch: 3 }), baseline)
  assert.notEqual(assessmentSignature('defender', '', 'sometimes', { touch: 4 }), baseline)
  assert.notEqual(assessmentSignature('midfielder', '', 'sometimes', { touch: 3 }), baseline)
})

test('an open page asks to be reloaded only when the server runs a different build', async () => {
  const { isOutdated } = await loadJsx('src/version.js')
  assert.equal(isOutdated('dev-e93b78e', 'dev-5085244'), true)
  assert.equal(isOutdated('dev-e93b78e', 'dev-e93b78e'), false)
  assert.equal(isOutdated('local', 'dev-e93b78e'), false, 'local builds never ask')
  assert.equal(isOutdated('dev-e93b78e', 'local'), false)
  assert.equal(isOutdated('dev-e93b78e', undefined), false, 'no answer from the server is not a new version')
})

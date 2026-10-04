import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { createServer } from 'vite'
import { AREAS, PLAYER_DATA_TABS, assessmentSignature, canManageTeam, initialPeriodId, initialPlayerId } from '../src/dashboardModel.js'
import { horizontalSwipe, ratedCount } from '../src/mobileAssessmentModel.js'
import { columnsByScore } from '../src/teamDataModel.js'
import { errorMessage } from '../src/api.js'

async function loadJsx(entry) {
  const server = await createServer({ logLevel: 'silent', server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  try { return await server.ssrLoadModule(`/${entry}`) }
  finally { await server.close() }
}

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
})

test('player data exposes all four sub-tabs, including confirmed priorities', () => {
  assert.deepEqual(PLAYER_DATA_TABS.map(([id]) => id), ['summary', 'comparison', 'progress', 'priorities'])
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

test('team heatmap retains desktop table and shows one swipeable phone card per open section', async () => {
  const { default: HeatmapView } = await loadJsx('src/HeatmapView.jsx')
  const matrix = { sections: [
    { id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [{ id: 'touch', label: 'First touch' }, { id: 'passing', label: 'Passing' }] },
    { id: 'tactical', label: 'Tactical', applies_to: ['defender'], skills: [{ id: 'positioning', label: 'Positioning' }] },
  ] }
  const assessments = [{ assessor: 'coach', position: 'outfield', player_name: 'Sam', primary_position: 'defender', ratings: [{ skill_id: 'touch', score: 3 }] }]
  const html = renderToStaticMarkup(React.createElement(HeatmapView, { matrix, assessments }))
  assert.match(html, /heatmap-scroll desktop-data/)
  assert.match(html, /role="group" aria-label="Compare by"/)
  assert.match(html, /role="group" aria-label="Skill set"/)
  for (const label of ['Individual players', 'By position', 'Outfield skills', 'Goalkeeper skills']) assert.match(html, new RegExp(`aria-label="${label}"`))
  assert.match(html, /aria-label="Individual players"[^>]*aria-pressed="true"/)
  assert.match(html, /aria-label="Goalkeeper skills"[^>]*aria-pressed="false"/)
  assert.match(html, /mobile-data team-skill-sections/)
  assert.match(html, /team-heading-technical.*aria-expanded="true"/)
  assert.match(html, /team-heading-tactical.*aria-expanded="false"/)
  assert.match(html, /Skill 1 of 2/)
  assert.match(html, /aria-label="Next skill"/)
  const mobile = html.split('mobile-data team-skill-sections')[1]
  assert.match(mobile, /team-skill-card.*First touch/)
  assert.match(mobile, /Sam/)
  assert.doesNotMatch(mobile, /Passing/)
  assert.doesNotMatch(mobile, /Positioning/)
})

test('team skill cards order players by score, leaving unrated players last', async () => {
  const { default: HeatmapView } = await loadJsx('src/HeatmapView.jsx')
  const columns = [{ key: 'Sam' }, { key: 'Alex' }, { key: 'Jo' }, { key: 'Lee' }]
  const scores = { Sam: 4, Alex: 2, Jo: 2 }
  assert.deepEqual(columnsByScore(columns, 'touch', (_, key) => scores[key] ?? null).map(column => column.key), ['Alex', 'Jo', 'Sam', 'Lee'])
  assert.deepEqual(columns.map(column => column.key), ['Sam', 'Alex', 'Jo', 'Lee'])

  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [{ id: 'touch', label: 'First touch' }] }] }
  const assessments = columns.map(column => ({ assessor: 'coach', position: 'outfield', player_name: column.key, primary_position: 'defender', ratings: scores[column.key] == null ? [] : [{ skill_id: 'touch', score: scores[column.key] }] }))
  const html = renderToStaticMarkup(React.createElement(HeatmapView, { matrix, assessments }))
  const mobile = html.split('mobile-data team-skill-sections')[1]
  assert.ok(mobile.indexOf('Alex') < mobile.indexOf('Jo'))
  assert.ok(mobile.indexOf('Jo') < mobile.indexOf('Sam'))
  assert.ok(mobile.indexOf('Sam') < mobile.indexOf('Lee'))
})

test('development keeps guidance in a help dialog', async () => {
  const { default: PrioritiesView } = await loadJsx('src/PrioritiesView.jsx')
  const matrix = {
    sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [{ id: 'touch', label: 'First touch', position_weights: { defender: 'high' } }] }],
    position_weight_values: { high: 2 }, secondary_position_blend: {}, priority: { top_n: 3 },
  }
  const coach = { position: 'outfield', primary_position: 'defender', ratings: [{ skill_id: 'touch', score: 3 }] }
  const html = renderToStaticMarkup(React.createElement(PrioritiesView, { matrix, coach, player: null, teamId: 1, playerId: 1, periodId: 1 }))
  assert.match(html, /aria-label="How priorities work"/)
  assert.match(html, /<dialog[^>]*aria-labelledby="priority-help-title"/)
  assert.match(html, /<form method="dialog">/)
  assert.ok(html.indexOf('The algorithm suggests') > html.indexOf('<dialog'))
})

test('player progress renders an empty state and phone cards once history exists', async () => {
  const { ProgressView } = await loadJsx('src/CoachDashboard.jsx')
  const matrix = { sections: [{ skills: [{ id: 'touch', label: 'First touch' }] }] }
  assert.match(renderToStaticMarkup(React.createElement(ProgressView, { matrix, history: [] })), /No coach assessments/)
  const history = [{ period_id: 1, label: 'Autumn', assessments: { coach: { ratings: [{ skill_id: 'touch', score: 2 }] } }, priorities: [] }, { period_id: 2, label: 'Winter', assessments: { coach: { ratings: [{ skill_id: 'touch', score: 4 }] } }, priorities: [] }]
  const html = renderToStaticMarkup(React.createElement(ProgressView, { matrix, history }))
  assert.match(html, /mobile-data mobile-card-list/)
  assert.match(html, /\+2/)
  assert.match(html, /Winter/)
  assert.doesNotMatch(html, /Confirmed priorities/)
})

test('dashboard renders five navigation destinations and an empty assessment state', async () => {
  const { default: CoachDashboard } = await loadJsx('src/CoachDashboard.jsx')
  const router = createMemoryRouter([{ path: '*', element: React.createElement(CoachDashboard, { user: { email: 'coach@example.com' }, onLogout: () => {} }) }], { initialEntries: ['/app/assessment'] })
  const html = renderToStaticMarkup(React.createElement(RouterProvider, { router }))
  assert.match(html, /Start with a team/)
  assert.match(html, /mobile-context-trigger/)
  assert.match(html, /Choose a team/)
  assert.match(html, /mobile-context-dialog/)
  assert.match(html, /desktop-context/)
  assert.doesNotMatch(html.match(/<header class="dashboard-header">[\s\S]*?<\/header>/)?.[0] ?? '', /Sign out/)
  assert.doesNotMatch(html.match(/<dialog[^>]*class="mobile-context-dialog"[\s\S]*?<\/dialog>/)?.[0] ?? '', /Sign out/)
  for (const area of AREAS) assert.match(html, new RegExp(`aria-label="${area.label}"`))
  assert.match(html, /bottom-nav/)
})

test('mobile Settings has an account sign-out control', async () => {
  const { default: CoachDashboard } = await loadJsx('src/CoachDashboard.jsx')
  const router = createMemoryRouter([{ path: '*', element: React.createElement(CoachDashboard, { user: { email: 'coach@example.com' }, onLogout: () => {} }) }], { initialEntries: ['/app/settings'] })
  const html = renderToStaticMarkup(React.createElement(RouterProvider, { router }))
  assert.match(html, /Change password/)
  assert.match(html, /<p class="app-version">Version local<\/p>/)
  assert.match(html, /<section class="panel dashboard-panel settings-account">[\s\S]*?coach@example\.com[\s\S]*?<button type="button">Sign out<\/button>/)
})

test('mobile assessment shows one full-description skill and section completion', async () => {
  const { default: MobileAssessment } = await loadJsx('src/MobileAssessment.jsx')
  const technical = { id: 'technical', label: 'Technical Skills', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'Developing description', 3: 'Achieving description', 5: 'Excelling description' } },
    { id: 'passing', label: 'Passing', descriptors: { 1: 'Passes late', 3: 'Passes well', 5: 'Passes early' } },
  ] }
  const tactical = { id: 'tactical', label: 'Tactical Skills', applies_to: ['defender'], skills: [{ id: 'positioning', label: 'Positioning', descriptors: { 1: 'Lost', 3: 'Aware', 5: 'Anticipates' } }] }
  const matrix = { sections: [technical, tactical], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: { 1: 'Developing', 3: 'Achieving', 5: 'Excelling' } } } }
  const html = renderToStaticMarkup(React.createElement(MobileAssessment, { matrix, position: 'outfield', ratings: { touch: 3 }, onChange: () => {} }))
  assert.equal(ratedCount(technical, { touch: 3 }), 1)
  assert.match(html, /1 of 3 skills rated/)
  assert.match(html, /1\/2 rated/)
  assert.match(html, /Technical Skills/)
  assert.match(html, /Tactical Skills/)
  assert.match(html, /Developing description/)
  assert.match(html, /Achieving description/)
  assert.match(html, /Excelling description/)
  assert.doesNotMatch(html, /Passes late/)
  assert.doesNotMatch(html, /Anticipates/)
  assert.equal(horizontalSwipe({ x: 180, y: 80 }, { x: 70, y: 90 }), 1)
  assert.equal(horizontalSwipe({ x: 70, y: 90 }, { x: 180, y: 80 }), -1)
  assert.equal(horizontalSwipe({ x: 180, y: 80 }, { x: 70, y: 160 }), 0)
})

test('unfiltered skill form still renders every applicable skill for desktop and self-assessment', async () => {
  const { default: SkillForm } = await loadJsx('src/SkillForm.jsx')
  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'Needs control', 3: 'Controls well', 5: 'Controls under pressure' } },
    { id: 'passing', label: 'Passing', descriptors: { 1: 'Late pass', 3: 'Good pass', 5: 'Early pass' } },
  ] }], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: {} } } }
  const html = renderToStaticMarkup(React.createElement(SkillForm, { matrix, position: 'outfield', ratings: {}, onChange: () => {} }))
  assert.match(html, /First touch/)
  assert.match(html, /Passing/)
  assert.match(html, /Controls under pressure/)
  assert.match(html, /Early pass/)
})

test('disagreements distinguish a missing player assessment from alignment', async () => {
  const { default: SummaryView } = await loadJsx('src/SummaryView.jsx')
  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [{ id: 'touch', label: 'First touch' }] }] }
  const coach = { position: 'outfield', ratings: [{ skill_id: 'touch', score: 3 }] }
  const missing = renderToStaticMarkup(React.createElement(SummaryView, { matrix, coach, player: null }))
  assert.match(missing, /player has not submitted a self-assessment yet/)
  assert.doesNotMatch(missing, /aligned on all jointly-rated skills/)
  const aligned = renderToStaticMarkup(React.createElement(SummaryView, { matrix, coach, player: { position: 'outfield', ratings: [{ skill_id: 'touch', score: 3 }] } }))
  assert.match(aligned, /aligned on all jointly-rated skills/)
})

test('confirmed priorities show medal cards, saved notes, and other periods', async () => {
  const { ConfirmedPrioritiesView } = await loadJsx('src/ConfirmedPrioritiesView.jsx')
  const matrix = { sections: [{ skills: [{ id: 'touch', label: 'First touch' }, { id: 'passing', label: 'Passing' }, { id: 'positioning', label: 'Positioning' }] }] }
  const history = [
    { period_id: 1, label: 'Autumn', priorities: [{ rank: 1, skill_id: 'passing', coach_note: 'Keep practising passing.' }] },
    { period_id: 2, label: 'Winter', priorities: [{ rank: 3, skill_id: 'positioning', coach_note: null }, { rank: 1, skill_id: 'touch', coach_note: 'Use both feet.' }, { rank: 2, skill_id: 'passing', coach_note: '' }] },
  ]
  const html = renderToStaticMarkup(React.createElement(ConfirmedPrioritiesView, { matrix, history, periodId: 2 }))
  assert.match(html, /🥇/)
  assert.match(html, /🥈/)
  assert.match(html, /🥉/)
  assert.match(html, /First touch/)
  assert.match(html, /Use both feet\./)
  assert.match(html, /Confirmed priorities from other periods/)
  assert.match(html, /Keep practising passing\./)
  assert.ok(html.indexOf('First touch') < html.indexOf('Positioning'))
  const empty = renderToStaticMarkup(React.createElement(ConfirmedPrioritiesView, { matrix, history: [], periodId: 2 }))
  assert.match(empty, /No confirmed priorities for this period yet/)
})

test('archived players get a read-only assessment with a restore prompt', async () => {
  const { default: MobileAssessment } = await loadJsx('src/MobileAssessment.jsx')
  const { ArchivedNotice } = await loadJsx('src/CoachDashboard.jsx')
  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'Needs control', 3: 'Controls well', 5: 'Controls under pressure' } },
  ] }], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: {} } } }
  const props = { matrix, position: 'outfield', ratings: { touch: 3 }, onChange: () => {} }
  const editable = renderToStaticMarkup(React.createElement(MobileAssessment, props))
  const archived = renderToStaticMarkup(React.createElement(MobileAssessment, { ...props, readOnly: true }))
  assert.match(editable, /Save assessment/)
  assert.doesNotMatch(archived, /Save assessment/)
  assert.equal(archived.match(/class="option-btn[^"]*"/g)?.length, 5)
  assert.equal(archived.match(/<button type="button" disabled="" class="option-btn/g)?.length, 5)
  const notice = renderToStaticMarkup(React.createElement(ArchivedNotice, { player: { name: 'Kai' }, onRestore: () => {} }))
  assert.match(notice, /Kai is archived\./)
  assert.match(notice, /Restore player/)
})

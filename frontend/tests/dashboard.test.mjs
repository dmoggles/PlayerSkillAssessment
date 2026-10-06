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
  assert.equal(errorMessage({ response: { data: { detail: { message: 'Fix these before publishing', problems: ['A needs a tag', 'B needs a name'] } } } }), 'Fix these before publishing: A needs a tag; B needs a name')
})

test('player data exposes all sub-tabs, including confirmed priorities and the report', () => {
  assert.deepEqual(PLAYER_DATA_TABS.map(([id]) => id), ['summary', 'comparison', 'progress', 'priorities', 'report'])
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

test('self-assessment board summarises statuses and copies new links as one list', async () => {
  const { SELF_LINK_STATUS, copyAllText, needsLink, statusDetail, statusSummary } = await loadJsx('src/selfLinkModel.js')
  const rows = [
    { player_name: 'Ana', status: 'submitted', submitted_at: '2026-10-03T10:00:00Z' },
    { player_name: 'Ben', status: 'opened', opened_at: '2026-10-02T10:00:00Z', expires_at: '2026-10-09T10:00:00Z' },
    { player_name: 'Cal', status: 'expired', expires_at: '2026-09-30T10:00:00Z' },
    { player_name: 'Dee', status: 'not_sent' },
  ]
  assert.equal(statusSummary(rows), '1 of 4 submitted · 1 opened · 1 expired · 1 not sent')
  assert.deepEqual(rows.filter(needsLink).map(r => r.player_name), ['Cal', 'Dee'])
  assert.match(statusDetail(rows[1]), /^Opened .+ · expires .+$/)
  assert.equal(statusDetail(rows[3]), '')
  assert.equal(statusDetail({ status: 'sent', issued_at: null, expires_at: null }), '')
  for (const status of ['not_sent', 'sent', 'opened', 'submitted', 'expired']) assert.ok(SELF_LINK_STATUS[status].label)
  assert.equal(copyAllText([{ player_name: 'Ana', url: 'https://x/self/a' }, { player_name: 'Ben', url: 'https://x/self/b' }]), 'Ana: https://x/self/a\nBen: https://x/self/b')
})

test('revision history lists what each saved version changed, newest first', async () => {
  const { revisionTimeline, revisionChanges } = await loadJsx('src/revisionModel.js')
  const { default: RevisionHistory } = await loadJsx('src/RevisionHistory.jsx')
  const labels = { touch: 'First touch', passing: 'Passing' }
  const v1 = { primary_position: 'defender', secondary_position: null, ratings: [{ skill_id: 'touch', score: 3 }, { skill_id: 'passing', score: null }] }
  const v2 = { primary_position: 'midfielder', secondary_position: 'winger', secondary_position_frequency: 'often', ratings: [{ skill_id: 'touch', score: 4 }, { skill_id: 'passing', score: 2 }] }
  assert.deepEqual(revisionChanges(null, v1, labels), ['Created as Defender with 1 skill rated'])
  assert.deepEqual(revisionChanges(v1, v2, labels), [
    'Primary position: Defender → Midfielder',
    'Secondary position: None → Winger (often)',
    'First touch: 3 → 4',
    'Passing: — → 2',
  ])
  assert.deepEqual(revisionChanges(v2, v2, labels), [])
  const revisions = [
    { version: 1, editor: 'a@example.com', created_at: '2026-10-01T10:00:00Z', snapshot: v1 },
    { version: 3, editor: 'b@example.com', created_at: '2026-10-03T10:00:00Z', snapshot: v2 },
    { version: 2, editor: 'b@example.com', created_at: '2026-10-02T10:00:00Z', snapshot: v2 },
  ]
  assert.deepEqual(revisionTimeline(revisions, labels).map(r => [r.version, r.changes.length]), [[3, 0], [2, 4], [1, 1]])
  const matrix = { sections: [{ id: 'technical', skills: [{ id: 'touch', label: 'First touch' }, { id: 'passing', label: 'Passing' }] }] }
  const html = renderToStaticMarkup(React.createElement(RevisionHistory, { matrix, revisions }))
  assert.match(html, /Revision history \(3\)/)
  assert.match(html, /Saved with no changes/)
  assert.match(html, /First touch: 3 → 4/)
  assert.equal(renderToStaticMarkup(React.createElement(RevisionHistory, { matrix, revisions: [] })), '')
})

test('audit events read as plain sentences', async () => {
  const { auditText } = await loadJsx('src/auditModel.js')
  const event = (action, details = {}, target_email = 'coach@example.com') => ({ action, actor_email: 'owner@example.com', target_email, details })
  assert.equal(auditText(event('role_changed', { from: 'coach', to: 'owner' })), 'owner@example.com made coach@example.com an owner')
  assert.equal(auditText(event('role_changed', { from: 'owner', to: 'coach' })), 'owner@example.com changed coach@example.com to a coach')
  assert.equal(auditText(event('period_deleted', { label: 'Autumn' }, null)), 'owner@example.com deleted the period Autumn')
  assert.equal(auditText(event('team_renamed', { from: 'A', to: 'B' }, null)), 'owner@example.com renamed the team from A to B')
  assert.equal(auditText(event('something_new', {}, null)), 'owner@example.com: something_new')
  assert.equal(auditText(event('matrix_published', { version: 2, applied_to: 'Summer' }, null)), 'owner@example.com published skill matrix version 2 (also used for Summer)')
  assert.equal(auditText(event('age_group_changed', { from: null, to: 12 }, null)), 'owner@example.com set the age group to U12')
  assert.equal(auditText(event('age_group_changed', { from: 12, to: 13 }, null)), 'owner@example.com set the age group to U13 (was U12)')
  assert.equal(auditText(event('age_group_changed', { from: 13, to: null }, null)), 'owner@example.com cleared the age group')
  assert.equal(auditText(event('player_gender_changed', { from: 'mixed', to: 'girls' }, null)), 'owner@example.com changed player wording from mixed to girls')
})

test('coach notes affect the unsaved-changes check and appear in the form and revision history', async () => {
  const { assessmentSignature, formFromAssessment, formSignature } = await import('../src/dashboardModel.js')
  const { revisionChanges } = await loadJsx('src/revisionModel.js')
  const { default: SkillForm } = await loadJsx('src/SkillForm.jsx')
  const saved = { primary_position: 'defender', note: 'Good week', ratings: [{ skill_id: 'touch', score: 3, note: 'Heavy touch' }, { skill_id: 'passing', score: 2, note: null }] }
  const form = formFromAssessment(saved)
  assert.deepEqual(form.notes, { touch: 'Heavy touch' })
  const baseline = formSignature(form)
  assert.equal(assessmentSignature('defender', '', 'sometimes', form.ratings, { ...form.notes, passing: '  ' }, 'Good week '), baseline)
  assert.notEqual(assessmentSignature('defender', '', 'sometimes', form.ratings, { touch: 'Lighter touch' }, 'Good week'), baseline)
  assert.notEqual(assessmentSignature('defender', '', 'sometimes', form.ratings, form.notes, ''), baseline)
  assert.equal(formFromAssessment(null).note, '')
  // A new period starts from the player's previous positions, with no ratings or notes.
  const { previousCoachAssessment } = await import('../src/dashboardModel.js')
  const winger = { primary_position: 'winger', secondary_position: 'striker', secondary_position_frequency: 'often', ratings: [{ skill_id: 'touch', score: 4, note: 'x' }] }
  const keeper = { primary_position: 'goalkeeper', secondary_position: null, ratings: [] }
  const periods = [{ id: 3 }, { id: 2 }, { id: 1 }]
  const history = [{ period_id: 1, assessments: { coach: keeper } }, { period_id: 2, assessments: { coach: winger } }]
  assert.equal(previousCoachAssessment(history, periods, 3), winger)
  assert.equal(previousCoachAssessment(history, periods, 2), keeper, 'nearest earlier period, not the current one')
  assert.equal(previousCoachAssessment(history, periods, 1), winger, 'no earlier period: most recent')
  assert.equal(previousCoachAssessment([], periods, 3), null)
  const fresh = formFromAssessment(null, winger)
  assert.deepEqual([fresh.position, fresh.secondary, fresh.frequency, fresh.ratings, fresh.notes], ['winger', 'striker', 'often', {}, {}])
  assert.equal(formFromAssessment(null).position, 'defender')

  const labels = { touch: 'First touch', passing: 'Passing' }
  const after = { ...saved, note: null, ratings: [{ skill_id: 'touch', score: 3, note: 'Better' }, { skill_id: 'passing', score: 2, note: 'Look up first' }] }
  assert.deepEqual(revisionChanges(saved, after, labels), ['First touch note edited', 'Passing note added', 'Overall note removed'])

  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'a', 3: 'b', 5: 'c' } }, { id: 'passing', label: 'Passing', descriptors: { 1: 'd', 3: 'e', 5: 'f' } },
  ] }], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: {} } } }
  const base = { matrix, position: 'outfield', ratings: {}, onChange: () => {}, notes: { touch: 'Heavy touch' } }
  const editable = renderToStaticMarkup(React.createElement(SkillForm, { ...base, onNoteChange: () => {} }))
  assert.match(editable, /aria-label="Note on First touch"[^>]*>Heavy touch<\/textarea>/)
  assert.match(editable, /Add note/)
  const archived = renderToStaticMarkup(React.createElement(SkillForm, { ...base, onNoteChange: () => {}, readOnly: true }))
  assert.match(archived, /Note: Heavy touch/)
  assert.doesNotMatch(archived, /textarea|Add note/)
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(SkillForm, base)), /Add note|textarea/)
})

test('priority follow-up compares last confirmed priorities with this period by coach score', async () => {
  const { priorityFollowUp, keepPriority } = await loadJsx('src/followUpModel.js')
  const { default: FollowUpCard } = await loadJsx('src/FollowUpCard.jsx')
  const coach = scores => ({ ratings: Object.entries(scores).map(([skill_id, score]) => ({ skill_id, score })) })
  const periods = [{ id: 3, label: 'Spring' }, { id: 2, label: 'Winter' }, { id: 1, label: 'Autumn' }]
  const history = [
    { period_id: 1, label: 'Autumn', assessments: { coach: coach({ touch: 2, pass: 3, scan: 2 }) }, priorities: [
      { skill_id: 'scan', rank: 2, coach_note: 'Look before receiving' }, { skill_id: 'touch', rank: 1 }, { skill_id: 'pass', rank: 3 }] },
    { period_id: 2, label: 'Winter', assessments: { coach: coach({ touch: 3 }) }, priorities: [] },
  ]
  const current = coach({ touch: 3, pass: 3, scan: 1 })
  const followUp = priorityFollowUp(periods, history, 3, current)
  assert.equal(followUp.periodLabel, 'Autumn')  // Winter had no confirmed priorities
  assert.deepEqual(followUp.items.map(i => [i.skill_id, i.before, i.now, i.trend]), [
    ['touch', 2, 3, 'improved'], ['scan', 2, 1, 'worse'], ['pass', 3, 3, 'unchanged']])
  assert.equal(priorityFollowUp(periods, history, 3, null).items[0].trend, 'pending')
  assert.equal(priorityFollowUp(periods, history, 1, current), null)  // nothing earlier
  assert.equal(priorityFollowUp(periods, history, 99, current), null)

  const rows = [{ skill_id: 'touch', coach_note: '' }, { skill_id: 'shoot', coach_note: 'x' }, { skill_id: 'head', coach_note: '' }]
  assert.deepEqual(keepPriority(rows, 'scan', ['touch', 'scan', 'pass']).map(r => r.skill_id), ['touch', 'shoot', 'scan'])
  assert.deepEqual(keepPriority(keepPriority(rows, 'scan', ['touch', 'scan', 'pass']), 'pass', ['touch', 'scan', 'pass']).map(r => r.skill_id), ['touch', 'pass', 'scan'])
  assert.equal(keepPriority(rows, 'touch', ['touch']), rows)
  assert.deepEqual(keepPriority(rows.slice(0, 1), 'scan', ['scan']).map(r => r.skill_id), ['touch', 'scan'])

  const matrix = { sections: [{ skills: [{ id: 'touch', label: 'First touch' }, { id: 'scan', label: 'Scanning' }, { id: 'pass', label: 'Passing' }] }] }
  const html = renderToStaticMarkup(React.createElement(FollowUpCard, { matrix, followUp, chosen: new Set(['pass']), canKeep: () => true, onKeep: () => {} }))
  assert.match(html, /Last period&#x27;s priorities <small>Autumn<\/small>/)
  assert.match(html, /Coach score 2 → 1/)
  assert.match(html, /Look before receiving/)
  assert.equal(html.match(/>Keep<\/button>/g)?.length, 1)  // scan only: touch improved, pass already chosen
  assert.match(html, /In this period/)
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(FollowUpCard, { matrix, followUp })), /Keep|In this period/)

  const { priorityTag } = await loadJsx('src/followUpModel.js')
  assert.equal(priorityTag('scan', 'scan', ['scan']), 'suggested')
  assert.equal(priorityTag('scan', 'touch', ['scan']), 'carried')
  assert.equal(priorityTag('head', 'touch', ['scan']), 'override')
})

test('player report shows coach-only section scores, strengths, focus, follow-up and progress', async () => {
  const { buildReport } = await loadJsx('src/reportModel.js')
  const { default: PlayerReport } = await loadJsx('src/PlayerReport.jsx')
  const matrix = { meta: { scale: { anchors: { 1: 'Developing', 3: 'Achieving', 5: 'Excelling' } } }, sections: [
    { id: 'technical', label: 'Technical', applies_to: ['winger'], skills: [{ id: 'touch', label: 'First touch' }, { id: 'pass', label: 'Passing' }] },
    { id: 'tactical', label: 'Tactical', applies_to: ['winger'], skills: [{ id: 'scan', label: 'Scanning' }] },
  ] }
  const coach = (scores, extra = {}) => ({ position: 'outfield', primary_position: 'winger', ratings: Object.entries(scores).map(([skill_id, score]) => ({ skill_id, score })), ...extra })
  const payload = { player: 'Rae', team: 'Reports', period: 'Spring', period_id: 2, message: 'Great season', history: [
    { period_id: 1, label: 'Autumn', assessments: { coach: coach({ touch: 2, pass: 3, scan: 2 }) }, priorities: [{ skill_id: 'scan', rank: 1, coach_note: 'Look up' }] },
    { period_id: 2, label: 'Spring', assessments: { coach: coach({ touch: 4, pass: 3, scan: 3 }, { secondary_position: 'striker' }) }, priorities: [{ skill_id: 'pass', rank: 1, coach_note: 'Weight of pass' }] },
  ] }
  const report = buildReport(matrix, payload)
  assert.equal(report.position, 'Winger, also Striker')
  assert.deepEqual(report.sections.map(s => [s.label, s.score]), [['Technical', 3.5], ['Tactical', 3]])
  assert.equal(report.strengths[0].label, 'First touch')
  assert.deepEqual(report.priorities, [{ rank: 1, label: 'Passing', note: 'Weight of pass' }])
  assert.deepEqual(report.followUp.items.map(i => [i.label, i.trend]), [['Scanning', 'improved']])
  assert.deepEqual(report.trend.rows.map(r => r.values), [[2.5, 3.5], [2, 3]])
  const html = renderToStaticMarkup(React.createElement(PlayerReport, { report }))
  for (const text of ['From your coach', 'Great season', 'Focus for next period', 'Weight of pass', 'Last period&#x27;s focus', 'Improved', 'Progress', '1 Developing, 3 Achieving, 5 Excelling'])
    assert.ok(html.includes(text), text)
  assert.doesNotMatch(html, /\b(she|her|he|his)\b/i)
  const empty = buildReport(matrix, { ...payload, message: null, history: [{ ...payload.history[0], period_id: 2, assessments: {} }] })
  assert.equal(empty.assessed, false)
  assert.match(renderToStaticMarkup(React.createElement(PlayerReport, { report: empty })), /no coach assessment for this period yet/)
})

test('report share status reads clearly and share events appear in the activity log', async () => {
  const { shareSummary } = await loadJsx('src/reportModel.js')
  const { auditText } = await loadJsx('src/auditModel.js')
  assert.match(shareSummary(null), /^Not shared/)
  assert.match(shareSummary({ issued_at: '2026-10-01T10:00:00Z', expires_at: '2026-10-31T10:00:00Z', opened_at: null, expired: false }), /^Shared .+ · expires .+ · not opened yet$/)
  assert.match(shareSummary({ issued_at: '2026-10-01T10:00:00Z', expires_at: '2026-10-31T10:00:00Z', opened_at: '2026-10-02T10:00:00Z', expired: false }), / · opened /)
  assert.match(shareSummary({ issued_at: '2026-09-01T10:00:00Z', expires_at: '2026-10-01T10:00:00Z', opened_at: null, expired: true }), /^The link expired on /)
  const event = { action: 'report_shared', actor_email: 'coach@example.com', details: { player: 'Max', period: 'Autumn' } }
  assert.equal(auditText(event), 'coach@example.com shared the report for Max (Autumn)')
  assert.equal(auditText({ ...event, details: { ...event.details, replaced: true } }), 'coach@example.com created a new report link for Max (Autumn), replacing the previous one')
  assert.equal(auditText({ ...event, action: 'report_share_revoked' }), 'coach@example.com revoked the report link for Max (Autumn)')
})

test('matrix editor helpers add, move, retire and tag skills without touching other data', async () => {
  const m = await loadJsx('src/matrixEditorModel.js')
  const doc = {
    positions: ['goalkeeper', 'defender', 'midfielder', 'winger', 'striker'].map(id => ({ id })),
    dependency_map: { touch: ['scan', 'pass'] },
    sections: [
      { id: 'technical', label: 'Technical', applies_to: m.OUTFIELD, skills: [{ id: 'touch', label: 'Touch', tags: { first_touch: 1 } }, { id: 'pass', label: 'Pass', tags: {} }] },
      { id: 'tactical', label: 'Tactical', applies_to: m.OUTFIELD, skills: [{ id: 'scan', label: 'Scan', tags: {} }] },
      { id: 'goalkeeper', label: 'Keeping', applies_to: m.GOALKEEPER, skills: [{ id: 'hands', label: 'Hands', tags: {} }] },
    ],
  }
  const [added, key] = m.addSkill(doc, 'tactical')
  const created = m.findSkill(added, key).skill
  assert.equal(created.id, null)
  assert.deepEqual(Object.keys(created.position_weights), ['goalkeeper', 'defender', 'midfielder', 'winger', 'striker'])
  const [withKeeperSkill, keeperKey] = m.addSkill(doc, 'goalkeeper')
  assert.deepEqual(Object.keys(m.findSkill(withKeeperSkill, keeperKey).skill.position_weights), ['goalkeeper'])
  assert.equal(doc.sections[1].skills.length, 1, 'original document untouched')

  assert.deepEqual(m.moveSkill(doc, 'pass', -1).sections[0].skills.map(s => s.id), ['pass', 'touch'])
  assert.deepEqual(m.moveSkillToSection(doc, 'pass', 'tactical').sections.map(s => s.skills.map(k => k.id)), [['touch'], ['scan', 'pass'], ['hands']])
  assert.equal(m.moveSkillToSection(doc, 'pass', 'goalkeeper'), doc, 'outfield skills cannot move into a goalkeeper section')
  const retired = m.removeSkill(doc, 'scan')
  assert.deepEqual(retired.dependency_map, { touch: ['pass'] })
  assert.deepEqual(m.removeSkill(doc, 'touch').dependency_map, {})
  assert.deepEqual(m.setTag(m.setTag(doc, 'pass', 'passing_short', 1), 'touch', 'first_touch', null).sections[0].skills.map(s => s.tags), [{}, { passing_short: 1 }])
  assert.deepEqual(m.setFoundationFor(doc, 'touch', []).dependency_map, {})
  assert.equal(m.removeSection(doc, 'technical').sections.length, 3, 'sections with skills are not removed')

  const server = { sections: added.sections.map(s => ({ ...s, skills: s.skills.map(k => k._key ? { ...k, id: 'new_skill' } : k) })) }
  const local = m.updateSkill(added, key, { label: 'Weak foot' })
  const adopted = m.adoptServerIds(local, server)
  assert.equal(m.findSkill(adopted, key).skill.id, 'new_skill', 'takes the server id')
  assert.equal(m.findSkill(adopted, key).skill.label, 'Weak foot', 'keeps local edits and the same selection key')

  assert.deepEqual(m.literalPronouns('Organises her teammates; where {they} {is|are} and their zone'), ['her', 'their'])
  assert.deepEqual(m.literalPronouns('Sets {their} position'), [])
  assert.equal(m.changeCount({ addition: ['a'], wording: ['b', 'c'], breaking: [] }), 3)
})

test('history views mark comparisons that cross a skill matrix change', async () => {
  const { ProgressView } = await loadJsx('src/CoachDashboard.jsx')
  const { priorityFollowUp } = await loadJsx('src/followUpModel.js')
  const { buildReport } = await loadJsx('src/reportModel.js')
  const { default: PlayerReport } = await loadJsx('src/PlayerReport.jsx')
  const { default: FollowUpCard } = await loadJsx('src/FollowUpCard.jsx')
  const coach = scores => ({ position: 'outfield', primary_position: 'winger', ratings: Object.entries(scores).map(([skill_id, score]) => ({ skill_id, score })) })
  const sections = { touch: 'technical', talk: 'tactical', restarts: 'technical', weak: 'technical' }
  const history = [
    { period_id: 1, label: 'Autumn', assessments: { coach: coach({ touch: 2, talk: 2, restarts: 3 }) }, priorities: [{ skill_id: 'talk', rank: 1 }, { skill_id: 'restarts', rank: 2 }, { skill_id: 'touch', rank: 3 }],
      matrix_version_id: 1, skill_changes: {}, skill_labels: { touch: 'Touch', talk: 'Communication', restarts: 'Restarts' }, skill_sections: sections },
    { period_id: 2, label: 'Spring', assessments: { coach: coach({ touch: 3, talk: 3, weak: 2 }) }, priorities: [],
      matrix_version_id: 7, skill_changes: { talk: 'reworded', restarts: 'retired', weak: 'added' }, skill_labels: { touch: 'Touch', talk: 'Communication', weak: 'Weak foot', restarts: 'Restarts' }, skill_sections: sections },
  ]
  const matrix = { meta: { scale: { anchors: {} } }, sections: [
    { id: 'technical', label: 'Technical', applies_to: ['winger'], skills: [{ id: 'touch', label: 'Touch' }, { id: 'weak', label: 'Weak foot' }] },
    { id: 'tactical', label: 'Tactical', applies_to: ['winger'], skills: [{ id: 'talk', label: 'Communication' }] },
  ] }

  const progress = renderToStaticMarkup(React.createElement(ProgressView, { matrix, history }))
  assert.match(progress, /Restarts/, 'retired skills keep their name')
  assert.match(progress, /3<sup class="matrix-change" title="Skill matrix: wording changed in Spring/)
  assert.match(progress, /\+1\*/, 'change across a rewording is flagged')
  assert.match(progress, /<td>Touch<\/td><td>2<\/td><td>3<\/td><td>\+1<\/td>/, 'unchanged skills are not flagged')
  assert.match(progress, /not directly comparable/)

  const periods = [{ id: 2, label: 'Spring' }, { id: 1, label: 'Autumn' }]
  const followUp = priorityFollowUp(periods, history, 2, history[1].assessments.coach)
  assert.deepEqual(followUp.items.map(i => [i.skill_id, i.trend, i.change]), [['talk', 'improved', 'reworded'], ['restarts', 'retired', 'retired'], ['touch', 'improved', null]])
  const card = renderToStaticMarkup(React.createElement(FollowUpCard, { matrix, followUp, canKeep: () => true, onKeep: () => {} }))
  assert.match(card, /wording changed since Autumn/)
  assert.match(card, /No longer assessed/)
  assert.match(card, /<strong>Restarts<\/strong>/, 'retired priorities show their name from history')
  assert.doesNotMatch(card, />Keep</, 'retired and improved priorities cannot be kept')

  const report = buildReport(matrix, { player: 'Rae', team: 'T', period: 'Spring', period_id: 2, message: null, history })
  assert.deepEqual(report.trend.rows.map(r => [r.label, r.changed]), [['Technical', [false, true]], ['Tactical', [false, true]]])
  assert.match(renderToStaticMarkup(React.createElement(PlayerReport, { report })), /skills in this area changed from this period/)
})

test('team insights shape trends by skill area and tag, keep colours fixed, and render each tab', async () => {
  const { sectionSeries, tagTrendRows, tagPositionRows, SERIES_COLORS, groupName } = await loadJsx('src/insightsModel.js')
  assert.equal(groupName('defender'), 'defenders')
  assert.equal(groupName(''), 'all positions')
  const { default: TrendChart } = await loadJsx('src/TrendChart.jsx')
  const { placeEndLabels } = await loadJsx('src/insightsModel.js')
  const placed = placeEndLabels([{ id: 'a', y: 100 }, { id: 'b', y: 100 }, { id: 'c', y: 100 }], 20, 240)
  assert.deepEqual(placed.map(l => l.labelY), [100, 113, 126], 'equal end values are stacked, not overprinted')
  assert.deepEqual(placeEndLabels([{ id: 'a', y: 238 }, { id: 'b', y: 240 }], 20, 240).map(l => l.labelY), [227, 240], 'kept inside the plot')
  const data = {
    section_labels: { technical: 'Technical', tactical: 'Tactical', goalkeeper: 'Goalkeeping' },
    tags: { first_touch: { label: 'First touch', area: 'technical' }, scanning: { label: 'Scanning', area: 'tactical' }, gk_positioning: { label: 'GK positioning', area: 'goalkeeping' } },
    trend: [
      { period_id: 1, label: 'Autumn', players: 3, changed_sections: [], sections: { technical: { average: 2.5 }, goalkeeper: { average: 3 } }, tags: { first_touch: { average: 2 }, gk_positioning: { average: 3 } } },
      { period_id: 2, label: 'Spring', players: 2, changed_sections: ['technical'], sections: { technical: { average: 3 }, tactical: { average: 2.75 } }, tags: { first_touch: { average: 3 }, scanning: { average: 2 } } },
    ],
  }
  const series = sectionSeries(data)
  assert.deepEqual(series.map(s => [s.id, s.values, s.changed]), [['technical', [2.5, 3], [false, true]], ['goalkeeper', [3, null], [false, false]], ['tactical', [null, 2.75], [false, false]]])
  assert.deepEqual(series.map(s => s.color), SERIES_COLORS.slice(0, 3), 'colours follow first appearance, in fixed order')
  assert.deepEqual(tagTrendRows(data).map(r => [r.label, r.values]), [['First touch', [2, 3]], ['Scanning', [null, 2]], ['GK positioning', [3, null]]])
  assert.deepEqual(tagPositionRows(data, [{ tags: { scanning: { average: 4 } } }]).map(r => r.id), ['scanning'])

  const svg = renderToStaticMarkup(React.createElement(TrendChart, { periods: ['Autumn', 'Spring'], series }))
  assert.equal(svg.match(/<polyline/g).length, 3, 'one line segment per series (single points still drawn as dots)')
  assert.match(svg, /class="chart-change">\*</)
  assert.match(svg, /class="chart-legend"/)
  assert.match(svg, /role="img"/)
})

test('priority player lists are sorted by rank, summarised, and collapsed when long', async () => {
  const { sortByRank, priorityCount } = await loadJsx('src/insightsModel.js')
  const { PlayerList } = await loadJsx('src/TeamInsights.jsx')
  const players = [{ player: 'Zed', rank: 2 }, { player: 'Ada', rank: 3 }, { player: 'Bea', rank: 1 }, { player: 'Al', rank: 1 }, { player: 'Cy', rank: 2 }, { player: 'Di', rank: 1 }]
  assert.deepEqual(sortByRank(players).map(p => p.player), ['Al', 'Bea', 'Di', 'Cy', 'Zed', 'Ada'])
  assert.equal(priorityCount(players), '6 players (3 as #1)')
  assert.equal(priorityCount([{ player: 'Al', rank: 1 }]), '1 player')
  assert.equal(priorityCount([{ player: 'Al', rank: 2 }, { player: 'Bo', rank: 3 }]), '2 players')
  const html = renderToStaticMarkup(React.createElement(PlayerList, { players }))
  assert.match(html, /Al \(#1\), Bea \(#1\), Di \(#1\), Cy \(#2\)/)
  assert.doesNotMatch(html, /Zed|Ada/)
  assert.match(html, />\+2 more</)
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(PlayerList, { players: players.slice(0, 4) })), /more/)
})

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
  assert.equal(ease(0), 0); assert.equal(ease(1), 1); assert.equal(ease(0.5), 0.5)

  const html = renderToStaticMarkup(React.createElement(DiagramPlayer, { diagram, caption: 'Test drill' }))
  assert.match(html, /role="img" aria-label="Test drill\. Step 1 of 3: Pass while B runs"/)
  assert.match(html, /diagram-arrow-run/)
  assert.match(html, /diagram-cone/)
  // It opens before step 1 has happened: A still has the ball and B has not run yet.
  assert.match(html, /<circle cx="142" cy="174" r="10"/, 'B at its starting spot')
  assert.match(html, /<circle cx="53.2" cy="51.6" r="4.5" class="diagram-ball"/, 'the ball with A')

  assert.equal(videoEmbedUrl('https://www.youtube.com/watch?v=abc123', 30), 'https://www.youtube-nocookie.com/embed/abc123?autoplay=1&start=30')
  assert.equal(videoEmbedUrl('https://youtu.be/xyz'), 'https://www.youtube-nocookie.com/embed/xyz?autoplay=1')
  assert.equal(videoEmbedUrl('https://vimeo.com/76979871'), 'https://player.vimeo.com/video/76979871?autoplay=1&dnt=1')
  assert.equal(videoEmbedUrl('https://example.com/video'), null)
  assert.equal(videoEmbedUrl('https://www.youtube.com/shorts/BIHD3HOH040'), 'https://www.youtube-nocookie.com/embed/BIHD3HOH040?autoplay=1')
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
  const rondo = { title: 'Rondo 4v1', summary: 'Keep the ball', format: 'small_group', intensity: 'medium', players: [5, 5, 15], ages: [8, 16], levels: [1, 5], duration: [10, 15], home_friendly: false, equipment_items: ['balls', 'bibs', 'cones', 'mannequins'], tags: [{ id: 'passing_short', label: 'Short passing', area: 'technical' }], votes: { likes: 0, dislikes: 0, mine: 1 } }
  const slalom = { ...rondo, title: 'Cone slalom', summary: 'Dribble', format: 'individual', players: [1, 1, 20], home_friendly: true, equipment_items: ['balls', 'cones'], tags: [{ id: 'dribbling', label: 'Dribbling', area: 'technical' }], votes: { likes: 0, dislikes: 0, mine: 0 } }
  const match = changes => [rondo, slalom].filter(d => matchesFilters(d, { ...EMPTY_FILTERS, ...changes })).map(d => d.title)
  assert.deepEqual(match({}), ['Rondo 4v1', 'Cone slalom'])
  assert.deepEqual(match({ text: 'short PASS' }), ['Rondo 4v1'], 'search covers skill labels, ignoring case')
  assert.deepEqual(match({ players: '3' }), ['Cone slalom'], 'too few players for the rondo')
  assert.deepEqual(match({ players: '30' }), ['Rondo 4v1', 'Cone slalom'], 'a big squad splits into groups')
  assert.deepEqual(match({ equipment: ['goals'] }), ['Cone slalom'], 'the rondo also needs mannequins; balls, bibs and cones are assumed')
  assert.deepEqual(match({ equipment: ['mannequins'] }), ['Rondo 4v1', 'Cone slalom'])
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

test('priority drill suggestions are folded away, name the variation and explain when nothing matches', async () => {
  const { PriorityDrills } = await loadJsx('src/DrillLibrary.jsx')
  const render = suggestion => renderToStaticMarkup(React.createElement(PriorityDrills, { suggestion, onOpen: () => {} }))
  const drill = { slug: 'rondo-4v1', title: '4v1 rondo', format: 'small_group', duration: [8, 12], votes: { likes: 0, dislikes: 0, mine: 1 }, ladder_for: [], variation: { id: 7, kind: 'regression', title: '5v1 in a bigger square', levels: [1, 2], level_matched: true } }
  const html = render({ tagged: true, level: 1, matches: 4, drills: [drill] })
  assert.match(html, /^<details class="priority-drills"><summary>Drills \(1\)<\/summary>/, 'closed until opened')
  assert.match(html, /matched to level 1/)
  assert.match(html, /4v1 rondo<\/button>/)
  assert.match(html, /Easier: 5v1 in a bigger square · Small group · 12 min/)
  assert.match(html, /You like this/)
  assert.match(html, /3 more in Settings → Drill library/)
  const offLadder = { ...drill, title: '1v1 to the end line', ladder_for: ['1v1 attacking'], variation: { ...drill.variation, kind: 'base', title: 'Live 1v1', level_matched: false } }
  assert.match(render({ tagged: true, level: 4, matches: 1, drills: [offLadder] }), /Base version; its levels follow 1v1 attacking/)
  assert.match(render({ tagged: true, level: null, matches: 1, drills: [{ ...drill, variation: { ...drill.variation, kind: 'base', title: '4v1', level_matched: false } }] }), /Not rated, so base versions/)
  assert.match(render({ tagged: true, level: 3, matches: 0, drills: [] }), /Drills \(0\).*No drills for this skill in the library yet/)
  assert.match(render({ tagged: false, level: 3, matches: 0, drills: [] }), /this skill has no tags/)
  assert.equal(render(undefined), '')
})

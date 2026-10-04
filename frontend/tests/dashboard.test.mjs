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

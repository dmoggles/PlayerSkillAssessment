import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { AREAS } from '../src/dashboardModel.js'
import { loadJsx } from './helpers.mjs'

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

test('saving plans and extending report links show in the activity log', async () => {
  const { auditText } = await loadJsx('src/auditModel.js')
  assert.equal(auditText({ action: 'plan_saved', actor_email: 'o@x', details: { player: 'Kit', period: 'Autumn' } }), 'o@x generated the development plan for Kit (Autumn)')
  assert.equal(auditText({ action: 'plan_saved', actor_email: 'o@x', details: { player: 'Kit', period: 'Autumn', replaced: true } }), 'o@x regenerated the development plan for Kit (Autumn)')
  assert.equal(auditText({ action: 'report_share_extended', actor_email: 'o@x', details: { player: 'Kit', period: 'Autumn', weeks: 2 } }), 'o@x extended the report link for Kit (Autumn) by 2 weeks')
  // Older events from the separate plan links still read sensibly.
  assert.equal(auditText({ action: 'plan_shared', actor_email: 'o@x', details: { player: 'Kit', period: 'Autumn' } }), 'o@x shared a development plan for Kit (Autumn)')
  assert.equal(auditText({ action: 'plan_share_revoked', actor_email: 'o@x', details: { player: 'Kit', period: 'Autumn' } }), 'o@x revoked the plan link for Kit (Autumn)')
})

test('the period form asks whether a new season starts', async () => {
  const { default: PeriodForm } = await loadJsx('src/PeriodForm.jsx')
  const html = renderToStaticMarkup(React.createElement(PeriodForm, { teamId: 1, players: [], latestPeriod: null, onCreated: () => {}, onMessage: () => {} }))
  assert.match(html, /This period starts a new season/)
  assert.match(html, /Add period<\/button>/)
})

test('squad plan runs and plan edits read clearly in the activity log', async () => {
  const { auditText } = await loadJsx('src/auditModel.js')
  const e = (action, details) => auditText({ action, actor_email: 'o@x', details })
  assert.equal(e('squad_plans_generated', { period: 'Fall', players: 12 }), 'o@x generated 12 plans for the squad (Fall)')
  assert.equal(e('plan_slot_changed', { player: 'Kit', period: 'Fall', change: 'choose' }), "o@x chose a drill for Kit's plan (Fall)")
  assert.equal(e('cycle_started', { player: 'Kit', period: 'Fall', number: 2, checked_in: true }), 'o@x started development cycle 2 for Kit (Fall), after a check-in')
  const { default: SquadPlans } = await loadJsx('src/SquadPlans.jsx')
  assert.match(renderToStaticMarkup(React.createElement(SquadPlans, { teamId: 1, periodId: 2, onGenerated: () => {} })), /Generate plans for the squad/)
})

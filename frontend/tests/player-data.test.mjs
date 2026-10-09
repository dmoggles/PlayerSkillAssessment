import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { loadJsx } from './helpers.mjs'

test('player progress renders an empty state and phone cards once history exists', async () => {
  const { default: ProgressView } = await loadJsx('src/ProgressView.jsx')
  const matrix = { sections: [{ skills: [{ id: 'touch', label: 'First touch' }] }] }
  assert.match(renderToStaticMarkup(React.createElement(ProgressView, { matrix, history: [] })), /No coach assessments/)
  const history = [{ period_id: 1, label: 'Autumn', assessments: { coach: { ratings: [{ skill_id: 'touch', score: 2 }] } }, priorities: [] }, { period_id: 2, label: 'Winter', assessments: { coach: { ratings: [{ skill_id: 'touch', score: 4 }] } }, priorities: [] }]
  const html = renderToStaticMarkup(React.createElement(ProgressView, { matrix, history }))
  assert.match(html, /mobile-data mobile-card-list/)
  assert.match(html, /\+2/)
  assert.match(html, /Winter/)
  assert.doesNotMatch(html, /Confirmed priorities/)
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

test('history views mark comparisons that cross a skill matrix change', async () => {
  const { default: ProgressView } = await loadJsx('src/ProgressView.jsx')
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

test('the player report shows the saved plan, with weeks to open', async () => {
  const { default: PlayerReport } = await loadJsx('src/PlayerReport.jsx')
  const plan = { weeks: 4, slots: [{ rank: 1, skill_id: 'a', label: 'Short passing', slot: 'club', drill: 'rondo', title: '4v1 rondo', duration: [8, 12],
    weeks: [{ id: 1, title: 'Easy' }, { id: 1, title: 'Easy' }, { id: 2, title: 'Base' }, { id: 2, title: 'Base' }], reasons: ['Trains Short passing (priority 1).'] }], gaps: [] }
  const html = renderToStaticMarkup(React.createElement(PlayerReport, { report: { player: 'Kit', team: 'Falcons', period: 'Autumn', assessed: false, plan }, onOpenDrill: () => {} }))
  assert.match(html, /Practice at home <small>4 weeks<\/small>/)
  assert.match(html, /4v1 rondo<\/button>/)
  assert.match(html, /Weeks 1–2<\/span> Easy/)
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(PlayerReport, { report: { player: 'Kit', assessed: false, plan: null } })), /Practice at home/)
})

test('a saved plan is out of date once the priorities change, including their order', async () => {
  const { planIsStale } = await loadJsx('src/planModel.js')
  const saved = { plan: { weeks: 4 }, skills: ['a', 'b'] }
  assert.equal(planIsStale(saved, ['a', 'b']), false)
  assert.equal(planIsStale(saved, ['b', 'a']), true, 'a different order is a different plan')
  assert.equal(planIsStale({ plan: null }, ['c']), false, 'no plan is not an out-of-date plan')
})

test('with self-assessment off, the summary is the coach\'s alone', async () => {
  const { default: SummaryView } = await loadJsx('src/SummaryView.jsx')
  const matrix = { sections: [{ id: 'tech', label: 'Technical', applies_to: ['defender'], skills: [{ id: 's1', label: 'Passing', position_weights: {} }] }], dependency_map: {}, position_weight_values: {} }
  const coach = { position: 'outfield', ratings: [{ skill_id: 's1', score: 3 }] }
  const on = renderToStaticMarkup(React.createElement(SummaryView, { matrix, coach, player: null, selfAssessmentOn: true }))
  const off = renderToStaticMarkup(React.createElement(SummaryView, { matrix, coach, player: null, selfAssessmentOn: false }))
  assert.match(on, /Disagreements/)
  assert.match(on, /<span class="cmp-cell">Player<\/span>/)
  assert.doesNotMatch(off, /Disagreements|>Player<|Combined|self-assessment/)
})

test('earlier development cycles show in the report as one line, and in confirmed priorities', async () => {
  const { default: PlayerReport } = await loadJsx('src/PlayerReport.jsx')
  const html = renderToStaticMarkup(React.createElement(PlayerReport, { report: { player: 'Kit', assessed: true, sections: [], strengths: [], priorities: [{ rank: 1, label: '1v1 defending' }],
    earlierFocus: ['Short passing', 'Dribbling'], trend: { periods: [], rows: [] }, plan: null } }))
  assert.match(html, /Earlier this period: Short passing, Dribbling/)
  const { ConfirmedPrioritiesView } = await loadJsx('src/ConfirmedPrioritiesView.jsx')
  const matrix = { sections: [{ id: 't', skills: [{ id: 'a', label: 'Short passing' }, { id: 'b', label: '1v1 defending' }] }] }
  const history = [{ period_id: 1, label: 'Fall', priorities: [{ skill_id: 'b', rank: 1 }], assessments: {},
    earlier_cycles: [{ number: 1, started_at: '2026-09-01T00:00:00Z', priorities: [{ skill_id: 'a', rank: 1 }] }] }]
  const view = renderToStaticMarkup(React.createElement(ConfirmedPrioritiesView, { matrix, history, periodId: 1, periods: [{ id: 1, label: 'Fall' }] }))
  assert.match(view, /Earlier cycles this period/)
  assert.match(view, /Cycle 1<\/strong>.*Short passing/)
})

test('a check-in asks better, same or worse for each focus skill, and results show in cycle history', async () => {
  const { default: CheckinForm } = await loadJsx('src/CheckinForm.jsx')
  const cycle = { number: 1, priorities: [{ skill_id: 'a', rank: 1 }, { skill_id: 'b', rank: 2 }] }
  const html = renderToStaticMarkup(React.createElement(CheckinForm, { cycle, names: { a: 'Short passing', b: 'Dribbling' }, onSubmit: () => {}, onSkip: () => {}, onCancel: () => {} }))
  assert.match(html, /Check-in: how did cycle 1 go\?/)
  assert.equal((html.match(/type="radio"/g) ?? []).length, 6, 'three choices for each of two skills')
  assert.match(html, /<button type="submit" disabled="">Save check-in and start cycle 2<\/button>/, 'disabled until every skill has a result')
  assert.match(html, /Skip check-in/)
  const { ConfirmedPrioritiesView } = await loadJsx('src/ConfirmedPrioritiesView.jsx')
  const matrix = { sections: [{ id: 't', skills: [{ id: 'a', label: 'Short passing' }, { id: 'b', label: 'Dribbling' }] }] }
  const history = [{ period_id: 1, label: 'Fall', priorities: [], assessments: {},
    earlier_cycles: [{ number: 1, started_at: '2026-09-01T00:00:00Z', priorities: [{ skill_id: 'a', rank: 1 }, { skill_id: 'b', rank: 2 }], checkin: { a: { trend: 'better', note: null } } }] }]
  const view = renderToStaticMarkup(React.createElement(ConfirmedPrioritiesView, { matrix, history, periodId: 1, periods: [{ id: 1, label: 'Fall' }] }))
  assert.match(view, /Short passing \(better\), Dribbling<\/li>/)
})

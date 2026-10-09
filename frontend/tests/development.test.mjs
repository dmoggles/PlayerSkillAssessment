import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { loadJsx } from './helpers.mjs'

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

test('a development plan groups by priority and folds repeated weeks into runs', async () => {
  const { planByPriority, weekRuns } = await loadJsx('src/planModel.js')
  const base = { id: 2, title: 'Base' }, hard = { id: 3, title: 'Hard' }
  assert.deepEqual(weekRuns([base, base, hard, hard]).map(r => `${r.label}: ${r.variation.title}`), ['Weeks 1–2: Base', 'Weeks 3–4: Hard'])
  assert.deepEqual(weekRuns([hard, hard, hard, hard]).map(r => r.label), ['Weeks 1–4'])
  assert.deepEqual(weekRuns([base, hard, base]).map(r => r.label), ['Week 1', 'Week 2', 'Week 3'])
  const plan = { slots: [{ rank: 2, skill_id: 'b', label: 'B', slot: 'club' }, { rank: 1, skill_id: 'a', label: 'A', slot: 'home' }, { rank: 1, skill_id: 'a', label: 'A', slot: 'club' }],
    gaps: [{ rank: 3, skill_id: 'c', label: 'C', slot: 'club', reason: 'No drills' }] }
  const grouped = planByPriority(plan)
  assert.deepEqual(grouped.map(p => [p.rank, Boolean(p.club), Boolean(p.home), p.gaps.length]), [[1, true, true, 0], [2, true, false, 0], [3, false, false, 1]])
})

test('coaches can change plan slots; the report view cannot', async () => {
  const { PlanCards } = await loadJsx('src/DevelopmentPlan.jsx')
  const plan = { weeks: 4, slots: [{ rank: 1, skill_id: 'a', label: 'Passing', slot: 'club', drill: 'rondo', title: 'Rondo', duration: [8, 12], chosen_by: 'coach', suggested: 'other',
    weeks: [{ id: 1, title: 'Easy' }, { id: 1, title: 'Easy' }, { id: 2, title: 'Base' }, { id: 2, title: 'Base' }], reasons: [] }],
    gaps: [{ rank: 1, skill_id: 'a', label: 'Passing', slot: 'home', reason: 'Removed by the coach.' }] }
  const editor = { edit: async () => {}, alternatives: async () => [] }
  const coachView = renderToStaticMarkup(React.createElement(PlanCards, { plan, onOpenDrill: () => {}, editor }))
  assert.match(coachView, /Chosen by you/)
  assert.match(coachView, />Change<\/button>/)
  assert.match(coachView, />Restore<\/button>/)
  const reportView = renderToStaticMarkup(React.createElement(PlanCards, { plan, onOpenDrill: () => {} }))
  assert.doesNotMatch(reportView, /Change<\/button>|Restore/)
})

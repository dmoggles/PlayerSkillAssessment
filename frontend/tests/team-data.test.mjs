import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { columnsByScore } from '../src/teamDataModel.js'
import { loadJsx } from './helpers.mjs'

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

test('team data defaults to the largest playing group, and moves between groups are flagged', async () => {
  const { groupCounts } = await loadJsx('src/dashboardModel.js')
  const players = [1, 2, 3, 4, 5].map(id => ({ id, active: id !== 5 }))
  assert.deepEqual(groupCounts(players, { 1: 11, 2: 11, 3: 10, 4: 12, 5: 12 }), [{ age: 11, players: 2 }, { age: 10, players: 1 }, { age: 12, players: 1 }], 'largest first, then younger; archived ignored')
  const { priorityFollowUp } = await loadJsx('src/followUpModel.js')
  const history = [
    { period_id: 1, label: 'Fall', age_group: 11, priorities: [{ skill_id: 'a', rank: 1 }], assessments: { coach: { ratings: [{ skill_id: 'a', score: 2 }] } } },
    { period_id: 2, label: 'Spring', age_group: 12, priorities: [], assessments: { coach: { ratings: [{ skill_id: 'a', score: 2 }] } } },
  ]
  const periods = [{ id: 2, label: 'Spring' }, { id: 1, label: 'Fall' }]
  assert.deepEqual(priorityFollowUp(periods, history, 2, history[1].assessments.coach).groupChange, { from: 11, to: 12 })
  assert.equal(priorityFollowUp(periods, history.map(r => ({ ...r, age_group: 11 })), 2, history[1].assessments.coach).groupChange, null)
  const { default: ProgressView } = await loadJsx('src/ProgressView.jsx')
  const html = renderToStaticMarkup(React.createElement(ProgressView, { matrix: { sections: [] }, history }))
  assert.match(html, /Spring<small>U12<sup class="matrix-change"/)
  assert.match(html, /moved to another playing group/)
})

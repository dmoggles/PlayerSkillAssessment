import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { loadJsx } from './helpers.mjs'

// The shipped scenarios, with each pitch filled in from its format as the API does.
const data = JSON.parse(readFileSync(new URL('../../backend/app/data/practice_scenarios.json', import.meta.url)))
const withPitch = s => ({ ...s, pitch: { ...data.formats[s.format], ...(s.pitch ?? {}), penaltyArea: { ...data.formats[s.format].penaltyArea, ...(s.pitch?.penaltyArea ?? {}) } } })
const SCENARIOS = data.scenarios.map(withPitch)

// A plain 7v7 pitch and a frame to try checks against: our goal's centre is (0, 18.3).
const PITCH = data.formats['7v7']
const scenario = (frame, extra = {}) => ({ id: 't', pitch: PITCH, controlled: 'you', frames: [frame], ...extra })
const frame = (extra = {}) => ({ id: 'f1', mark: 'a1', ball: { x: 30, y: 18.3 }, opponents: [{ id: 'a1', x: 20, y: 18.3 }],
  team: [{ id: 'you', x: 10, y: 10 }], target: { zones: [{ type: 'ellipse', cx: 15, cy: 18.3, rx: 1, ry: 1, points: 100 }], reasonCorrect: 'Well done.', checks: [] }, ...extra })
const run = async (check, position, f, s = scenario(f)) => {
  const { CHECKS } = await loadJsx('src/practice/checks.js')
  const { thresholdsFor } = await loadJsx('src/practice/thresholds.js')
  return CHECKS[check].run(position, f, { pitch: s.pitch, thresholds: thresholdsFor(s) })
}

test('every scenario\'s best spot scores 100 and passes its checks, and no player starts there', async () => {
  const { idealPosition, scoreFrame, startPosition } = await loadJsx('src/practice/practiceModel.js')
  assert.ok(SCENARIOS.length >= 5)
  for (const s of SCENARIOS) {
    for (const f of s.frames) {
      const best = scoreFrame(s, f, idealPosition(f))
      assert.equal(best.points, 100, `${s.id} ${f.id}: the best spot scores 100`)
      assert.deepEqual(best.failed, [], `${s.id} ${f.id}: the best spot passes ${best.failed.join(', ')}`)
      assert.equal(best.message, f.target.reasonCorrect)
      assert.ok(scoreFrame(s, f, startPosition(s, f)).points < 100, `${s.id} ${f.id}: the player has to move`)
      assert.ok(f.prompt.split(' ').length <= 15 && f.target.reasonCorrect.split(' ').length <= 15, `${s.id} ${f.id}: short words for players`)
    }
  }
})

test('goal-side: closer to goal than the attacker, within the angle of their line to goal', async () => {
  const f = frame()
  assert.equal((await run('GOAL_SIDE', { x: 15, y: 18.3 }, f)).pass, true)
  assert.equal((await run('GOAL_SIDE', { x: 22, y: 18.3 }, f)).pass, false, 'behind the attacker')
  // 34 degrees off the line passes, 36 doesn't (the default is 35).
  const at = deg => ({ x: 20 - 5 * Math.cos((deg * Math.PI) / 180), y: 18.3 + 5 * Math.sin((deg * Math.PI) / 180) })
  assert.equal((await run('GOAL_SIDE', at(34), f)).pass, true)
  const wide = await run('GOAL_SIDE', at(36), f)
  assert.deepEqual([wide.pass, wide.reason], [false, 'not_goal_side'])
  // A scenario can widen the angle.
  assert.equal((await run('GOAL_SIDE', at(36), f, scenario(f, { thresholds: { goalSideAngle: 40 } }))).pass, true)
})

test('ball-side: the same side of the attacker\'s line to goal as the ball, unless the ball is on that line', async () => {
  const wide = frame({ ball: { x: 25, y: 5 } })
  assert.equal((await run('BALL_SIDE', { x: 15, y: 16 }, wide)).pass, true)
  assert.equal((await run('BALL_SIDE', { x: 15, y: 20 }, wide)).reason, 'not_ball_side')
  assert.equal((await run('BALL_SIDE', { x: 15, y: 20 }, frame({ ball: { x: 30, y: 18.8 } }))).pass, null, 'within a metre of the line')
})

test('tight and dropped distances apply only when the ball is near or far', async () => {
  const near = frame({ ball: { x: 26, y: 18.3 } })  // 6 m from the attacker
  assert.equal((await run('DISTANCE_TIGHT', { x: 17, y: 18.3 }, near)).pass, true, '3 m off')
  assert.equal((await run('DISTANCE_TIGHT', { x: 16.9, y: 18.3 }, near)).reason, 'too_far')
  assert.equal((await run('DISTANCE_DROP', { x: 19, y: 18.3 }, near)).pass, null)
  const far = frame({ ball: { x: 40.5, y: 18.3 } })  // 20.5 m away
  assert.equal((await run('DISTANCE_TIGHT', { x: 10, y: 18.3 }, far)).pass, null)
  assert.equal((await run('DISTANCE_DROP', { x: 16, y: 18.3 }, far)).pass, true, '4 m off')
  assert.equal((await run('DISTANCE_DROP', { x: 16.1, y: 18.3 }, far)).reason, 'too_close')
  assert.equal((await run('DISTANCE_DROP', { x: 16.1, y: 18.3 }, frame({ ball: { x: 39.5, y: 18.3 } }))).pass, null, 'under 20 m')
})

test('covering a pressing teammate: behind them towards goal, 3 to 7 m back', async () => {
  const f = frame({ team: [{ id: 'you', x: 5, y: 5 }, { id: 'd1', x: 20, y: 18.3, action: 'PRESS' }] })
  assert.equal((await run('BEHIND_PRESSER', { x: 15, y: 18.3 }, f)).pass, true)
  assert.equal((await run('BEHIND_PRESSER', { x: 22, y: 18.3 }, f)).reason, 'not_behind')
  assert.equal((await run('BEHIND_PRESSER', { x: 18, y: 18.3 }, f)).reason, 'too_close')
  assert.equal((await run('BEHIND_PRESSER', { x: 12, y: 18.3 }, f)).reason, 'too_far')
  assert.equal((await run('BEHIND_PRESSER', { x: 18, y: 25 }, f)).reason, 'not_behind', 'off to the side')
})

test('nearest threat: closer to the marked attacker than to any other', async () => {
  const f = frame({ opponents: [{ id: 'a1', x: 20, y: 18.3 }, { id: 'a2', x: 20, y: 28 }] })
  assert.equal((await run('NEAREST_THREAT', { x: 16, y: 19 }, f)).pass, true)
  assert.equal((await run('NEAREST_THREAT', { x: 16, y: 26 }, f)).reason, 'wrong_player')
})

test('scoring: the innermost zone the position is in, and the hint from the first failing check', async () => {
  const { headline, idealPosition, scoreFrame, stars } = await loadJsx('src/practice/practiceModel.js')
  const f = frame({ ball: { x: 26, y: 18.3 }, target: {
    zones: [{ type: 'ellipse', cx: 18, cy: 18.3, rx: 1, ry: 1, points: 100 }, { type: 'ellipse', cx: 18, cy: 18.3, rx: 1.5, ry: 1.5, points: 60 }],
    reasonCorrect: 'Tight and goal-side.', checks: [{ check: 'DISTANCE_TIGHT' }, { check: 'GOAL_SIDE', message: 'Goal-side first!' }] } })
  const s = scenario(f)
  assert.deepEqual(idealPosition(f), { x: 18, y: 18.3 })
  const best = scoreFrame(s, f, { x: 18.9, y: 18.3 })
  assert.deepEqual([best.points, best.zoneHit, best.message, best.headline], [100, 0, 'Tight and goal-side.', 'Great position'])
  const edge = scoreFrame(s, f, { x: 18, y: 19.8 })  // on the outer zone's edge
  assert.deepEqual([edge.points, edge.zoneHit], [60, 1])
  // Behind the attacker and too far: goal-side comes first, with the frame's own words for it.
  const behind = scoreFrame(s, f, { x: 24, y: 18.3 })
  assert.deepEqual([behind.points, behind.zoneHit, behind.failed, behind.message, behind.headline],
    [0, null, ['GOAL_SIDE', 'DISTANCE_TIGHT'], 'Goal-side first!', 'Not quite'])
  assert.equal(scoreFrame(s, f, { x: 17.6, y: 19.8 }).message, 'Look at the ghost to see a better spot.', 'every check passes but no zone')
  assert.equal(headline(60), 'Good')
  assert.deepEqual([stars([]), stars([100, 80]), stars([60, 60]), stars([0, 100])], [0, 3, 2, 1])
})

test('polygon zones, and turning pitch metres into an upright drawing and back', async () => {
  const { inZone, toPitch, toScreen, viewDepth, clampToView } = await loadJsx('src/practice/geometry.js')
  const square = { type: 'polygon', corners: [[10, 10], [14, 10], [14, 14], [10, 14]], points: 100 }
  assert.ok(inZone(square, { x: 12, y: 12 }))
  assert.ok(!inZone(square, { x: 15, y: 12 }))
  const depth = viewDepth(scenario(frame()))
  assert.equal(depth, 54.9 / 2 + 5)
  assert.deepEqual(toScreen({ x: 0, y: 18.3 }, depth), [18.3, depth], 'our goal at the bottom')
  assert.deepEqual(toPitch(toScreen({ x: 7, y: 3 }, depth), depth), { x: 7, y: 3 })
  assert.deepEqual(clampToView({ x: -2, y: 40 }, PITCH, depth), { x: 0, y: 36.6 })
})

test('a scenario opens on its first step, with Check disabled until your player moves', async () => {
  const React = (await import('react')).default
  const { renderToStaticMarkup } = await import('react-dom/server')
  const { default: ScenarioPlayer } = await loadJsx('src/practice/ScenarioPlayer.jsx')
  const s = SCENARIOS.find(x => x.frames.length > 1)
  const html = renderToStaticMarkup(React.createElement(ScenarioPlayer, { scenario: s }))
  assert.match(html, new RegExp(`Step 1 of ${s.frames.length}`))
  assert.ok(html.includes(s.frames[0].prompt.replace(/'/g, '&#x27;')))
  assert.match(html, /<button type="button" class="primary-btn" disabled="">Check<\/button>/)
  assert.match(html, /Your attacker/)
  assert.match(html, /role="button" aria-label="Your player, [\d.]+ metres from your goal line/)
  assert.match(html, /<svg class="practice-pitch"/)
})

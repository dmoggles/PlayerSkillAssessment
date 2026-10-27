// Scoring a practice frame: the zone the player's position is in, the diagnostic checks, and one short message.
// Pure functions, so the same answer always scores the same.
import { CHECKS, LINE_CHECKS } from './checks'
import { inZone, zoneCentre } from './geometry'
import { thresholdsFor } from './thresholds'

// When every check passes but the spot still isn't the best: two clues, like a check's.
export const NEARLY = ['Close! Small changes make the difference.', 'Nearly there. Think about your angle and your distance.']
export const SHOW_AFTER = 3  // misses before the best spot is shown

// The best spot: the centre of the zone worth most.
export const idealPosition = frame => zoneCentre(bestZone(frame))
const bestZone = frame => frame.target.zones.reduce((best, z) => (z.points > best.points ? z : best))

// Score a position in a frame of a scenario (which brings the pitch and any thresholds of its own).
export function scoreFrame(scenario, frame, position) {
  const context = { pitch: scenario.pitch, thresholds: thresholdsFor(scenario) }
  let points = 0, zoneHit = null
  frame.target.zones.forEach((zone, i) => { if (zone.points > points && inZone(zone, position)) { points = zone.points; zoneHit = i } })
  const checks = (frame.target.checks ?? []).map(({ check, clues }) => {
    const definition = CHECKS[check]
    const { pass, reason } = definition.run(position, frame, context)
    const defaults = pass === false ? definition.clues[reason] : null
    return { id: check, pass, reason: pass === false ? reason : null, priority: definition.priority,
      clues: pass === false ? [clues?.[0] ?? defaults[0], clues?.[1] ?? defaults[1]] : null }
  })
  const failing = checks.filter(c => c.pass === false).sort((a, b) => a.priority - b.priority)
  return { points, zoneHit, checks: checks.map(c => ({ id: c.id, pass: c.pass, reason: c.reason })), failed: failing.map(c => c.id),
    clues: points === 100 ? null : failing[0]?.clues ?? NEARLY, lineClue: LINE_CHECKS.has(failing[0]?.id), headline: headline(points),
    message: points === 100 ? frame.target.reasonCorrect : (failing[0]?.clues ?? NEARLY)[0] }
}

// What to tell the player on their nth try at a frame: a question to think about first, a plainer pointer next,
// and only then the best spot, with why it's best. On the second miss at a goal-side or ball-side idea, the lines to
// goal come on to help.
export function feedbackFor(frame, result, tries) {
  if (result.points === 100) return { message: frame.target.reasonCorrect, ghost: false, lines: false }
  if (tries >= SHOW_AFTER) return { message: `Here's the best spot. ${frame.target.reasonCorrect}`, ghost: true, lines: false }
  return { message: result.clues[Math.min(tries, 2) - 1], ghost: false, lines: tries >= 2 && result.lineClue }
}

// Encouraging words, never "wrong".
export const headline = points => (points >= 100 ? 'Great position' : points >= 50 ? 'Good' : 'Not quite')

// One to three stars for a scenario, from the points of each frame's first try.
export function stars(firstTries) {
  if (!firstTries.length) return 0
  const average = firstTries.reduce((sum, p) => sum + p, 0) / firstTries.length
  return average >= 90 ? 3 : average >= 60 ? 2 : 1
}

// Which player you are in a frame: the scenario's, unless the frame hands you another (such as each defender in turn).
export const controlledIn = (scenario, frame) => frame.controlled ?? scenario.controlled

// Where your player starts in a frame: where you left them in the frame before, if you're the same player, or where
// they're drawn (in a scenario from a real game, where that player actually was).
export const startPosition = (scenario, frame, previous = null, previousFrame = null) => {
  if (previous && previousFrame && controlledIn(scenario, previousFrame) === controlledIn(scenario, frame)) return previous
  const own = frame.team.find(p => p.id === controlledIn(scenario, frame))
  return { x: own.x, y: own.y }
}

// Plain words for the concepts scenarios teach and the checks a position can miss.
export const CONCEPT_LABELS = { GOAL_SIDE: 'Goal-side', BALL_SIDE: 'Ball-side', DISTANCE_TIGHT: 'Getting tight', DISTANCE_DROP: 'Dropping off',
  PRESS: 'Pressing', COVER: 'Covering', SCAN_MARKER: 'Scanning', NEAREST_THREAT: 'Picking the danger', COMMUNICATE: 'Talking' }

// Scenarios grouped for the library: each topic's stages in order, each with its scenarios.
export function libraryStages(library, ageGroup = null) {
  const fits = s => ageGroup == null || (s.ages[0] <= ageGroup && ageGroup <= s.ages[1])
  return library.topics.map(topic => ({
    ...topic,
    stages: topic.stages.map(stage => ({ ...stage, scenarios: library.scenarios.filter(s => s.topic === topic.id && s.stage === stage.stage && fits(s)) }))
      .filter(stage => stage.scenarios.length || stage.random),
  })).filter(topic => topic.stages.length)
}

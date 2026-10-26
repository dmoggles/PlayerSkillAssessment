// Scoring a practice frame: the zone the player's position is in, the diagnostic checks, and one short message.
// Pure functions, so the same answer always scores the same.
import { CHECKS } from './checks'
import { inZone, zoneCentre } from './geometry'
import { thresholdsFor } from './thresholds'

export const NEARLY = 'Nearly there. The ghost shows the best spot.'
export const ELSEWHERE = 'Look at the ghost to see a better spot.'

// The best spot: the centre of the zone worth most.
export const idealPosition = frame => zoneCentre(bestZone(frame))
const bestZone = frame => frame.target.zones.reduce((best, z) => (z.points > best.points ? z : best))

// Score a position in a frame of a scenario (which brings the pitch and any thresholds of its own).
export function scoreFrame(scenario, frame, position) {
  const context = { pitch: scenario.pitch, thresholds: thresholdsFor(scenario) }
  let points = 0, zoneHit = null
  frame.target.zones.forEach((zone, i) => { if (zone.points > points && inZone(zone, position)) { points = zone.points; zoneHit = i } })
  const checks = (frame.target.checks ?? []).map(({ check, message }) => {
    const definition = CHECKS[check]
    const { pass, reason } = definition.run(position, frame, context)
    // When picking the right opponent is the task (they aren't shown), picking them is the first thing to fix.
    const priority = check === 'NEAREST_THREAT' && frame.showMark === false ? 0 : definition.priority
    return { id: check, pass, reason: pass === false ? reason : null, priority,
      message: pass === false ? message ?? definition.messages[reason] : null }
  })
  const failing = checks.filter(c => c.pass === false).sort((a, b) => a.priority - b.priority)
  const message = points === 100 ? frame.target.reasonCorrect : failing[0]?.message ?? (points > 0 ? NEARLY : ELSEWHERE)
  return { points, zoneHit, checks: checks.map(c => ({ id: c.id, pass: c.pass, reason: c.reason, message: c.message })), failed: failing.map(c => c.id), message, headline: headline(points) }
}

// Encouraging words, never "wrong".
export const headline = points => (points >= 100 ? 'Great position' : points >= 50 ? 'Good' : 'Not quite')

// One to three stars for a scenario, from the points of each frame's first try.
export function stars(firstTries) {
  if (!firstTries.length) return 0
  const average = firstTries.reduce((sum, p) => sum + p, 0) / firstTries.length
  return average >= 90 ? 3 : average >= 60 ? 2 : 1
}

// Where the player's own player starts in a frame: where they left it in the frame before, or where it's drawn.
export const startPosition = (scenario, frame, previous) => {
  if (previous) return previous
  const own = frame.team.find(p => p.id === scenario.controlled)
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
      .filter(stage => stage.scenarios.length),
  })).filter(topic => topic.stages.length)
}

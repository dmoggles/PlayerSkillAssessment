// Pure calculation helpers for assessment summaries (Layer 1), priority scores
// (Layer 2), and disagreement flags (Layer 3). Derived on demand from raw
// ratings — nothing is stored except the coach's confirmed priorities.
import { sectionsFor, norm } from './matrix'

export const ratingMap = (assessment) => {
  const m = {}
  if (assessment) {
    for (const r of assessment.ratings) m[r.skill_id] = r.score
  }
  return m
}

const mean = (arr) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : null)

// Combined per-skill score: mean(coach, player) if both present, else whichever
// is available, else null. Never coerces null to 0.
export const combinedScore = (c, p) => {
  if (c != null && p != null) return (c + p) / 2
  if (c != null) return c
  if (p != null) return p
  return null
}

const applicableSkills = (matrix, position) =>
  sectionsFor(matrix, position).flatMap(s => s.skills)

// Layer 1: section averages (coach / player / combined) for applicable sections.
export function sectionAverages(matrix, position, coachMap, playerMap) {
  return sectionsFor(matrix, position).map(section => {
    const coachVals = section.skills.map(s => coachMap[s.id]).filter(v => v != null)
    const playerVals = section.skills.map(s => playerMap[s.id]).filter(v => v != null)
    const coach = mean(coachVals)
    const player = mean(playerVals)
    const combined = coach != null && player != null ? (coach + player) / 2 : (coach ?? player)
    return { id: section.id, label: section.label, coach, player, combined }
  })
}

// Layer 1: top/bottom 3 skills by combined average (nulls excluded).
export function skillCallouts(matrix, position, coachMap, playerMap) {
  const scored = applicableSkills(matrix, position)
    .map(s => ({ skill_id: s.id, label: s.label, score: combinedScore(coachMap[s.id], playerMap[s.id]) }))
    .filter(x => x.score != null)
  const byDesc = [...scored].sort((a, b) => b.score - a.score)
  const byAsc = [...scored].sort((a, b) => a.score - b.score)
  return { top: byDesc.slice(0, 3), bottom: byAsc.slice(0, 3) }
}

// Layer 1: coach-score completeness for applicable skills.
export function completeness(matrix, position, coachMap) {
  const skills = applicableSkills(matrix, position)
  const applicable = skills.length
  const assessed = skills.filter(s => coachMap[s.id] != null).length
  const pct = applicable ? (assessed / applicable) * 100 : 0
  return { assessed, applicable, pct }
}

// Layer 2: priority scores. Returns all applicable skills ranked by urgency,
// highest first. Requires the coach assessment (positions + scores); player
// assessment is optional and blended in via combinedScore when present.
export function priorityScores(matrix, coach, player) {
  if (!coach) return []
  const position = coach.position
  const primary = norm(coach.primary_position)
  const secondary = norm(coach.secondary_position)
  const frequency = coach.secondary_position_frequency

  const coachMap = ratingMap(coach)
  const playerMap = ratingMap(player)

  const weightValues = matrix.position_weight_values
  const blendTable = matrix.secondary_position_blend
  const blend = secondary && blendTable[frequency]
    ? blendTable[frequency]
    : { primary: 1.0, secondary: 0.0 }
  const depMap = matrix.dependency_map ?? {}
  const depBonus = matrix.dependency_bonus ?? 1.0
  const lowThreshold = matrix.priority?.low_score_threshold ?? 2

  const weightFor = (skill, pos) => {
    const label = pos ? skill.position_weights?.[pos] : undefined
    return label ? (weightValues[label] ?? 0) : 0
  }

  const skills = sectionsFor(matrix, position).flatMap(s => s.skills)
  const rows = []
  for (const skill of skills) {
    const avg = combinedScore(coachMap[skill.id], playerMap[skill.id])
    if (avg == null) continue

    const effectiveWeight =
      weightFor(skill, primary) * blend.primary +
      weightFor(skill, secondary) * blend.secondary

    let bonus = 0
    if (skill.is_dependency_root) {
      for (const depId of depMap[skill.id] ?? []) {
        const depAvg = combinedScore(coachMap[depId], playerMap[depId])
        if (depAvg != null && depAvg <= lowThreshold) {
          bonus = depBonus
          break
        }
      }
    }

    const score = (6 - avg) * effectiveWeight + bonus
    rows.push({
      skill_id: skill.id,
      label: skill.label,
      avg,
      weight: effectiveWeight,
      bonus,
      score,
      isRoot: skill.is_dependency_root === true,
    })
  }
  rows.sort((a, b) => b.score - a.score)
  return rows
}

export const suggestedPriorities = (matrix, coach, player) =>
  priorityScores(matrix, coach, player).slice(0, matrix.priority?.top_n ?? 3)

export const CONVERSATION_FRAMING = {
  overestimation: "She thinks she's doing this well — show her what the higher level looks like before discussing it.",
  underestimation: "She's better at this than she thinks — a confidence conversation, not a development one.",
}

// Layer 3: per-skill disagreement (only where both coach and player are present).
export function disagreements(matrix, position, coachMap, playerMap) {
  const skills = applicableSkills(matrix, position)
  const out = []
  for (const s of skills) {
    const c = coachMap[s.id]
    const p = playerMap[s.id]
    if (c == null || p == null) continue
    const diff = p - c
    const abs = Math.abs(diff)
    const level = abs <= 1 ? 'aligned' : abs === 2 ? 'notable' : 'significant'
    const direction = diff > 0 ? 'overestimation' : diff < 0 ? 'underestimation' : 'aligned'
    out.push({
      skill_id: s.id,
      label: s.label,
      coach: c,
      player: p,
      diff,
      abs,
      level,
      direction,
      isRoot: s.is_dependency_root === true,
    })
  }
  return out
}

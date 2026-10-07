// Compares the priorities confirmed in the most recent earlier period with the
// coach's scores in the selected period. Coach scores only: self-ratings do not count.
import { ratingMap } from './assessment'
import { RATING_CHANGES, changesBetween, historyLabels } from './comparabilityModel'

export const TRENDS = {
  improved: 'Improved',
  unchanged: 'No change',
  worse: 'Dropped',
  pending: 'Not yet rated',
  retired: 'No longer assessed',
}

const trend = (before, now) => now == null || before == null ? 'pending' : now > before ? 'improved' : now < before ? 'worse' : 'unchanged'

// periods: newest first, as the API returns them. history: the player's history rows.
export function priorityFollowUp(periods, history, periodId, currentCoach) {
  const index = periods.findIndex(period => period.id === Number(periodId))
  if (index < 0) return null
  const byPeriod = Object.fromEntries(history.map(row => [row.period_id, row]))
  const earlier = periods.slice(index + 1).find(period => byPeriod[period.id]?.priorities.length)
  if (!earlier) return null
  const previous = byPeriod[earlier.id]
  const before = ratingMap(previous.assessments?.coach)
  const now = ratingMap(currentCoach)
  // Skill matrix changes between the earlier period and this one (when this period is in the history).
  const fromIndex = history.indexOf(previous)
  const toIndex = history.findIndex(row => row.period_id === Number(periodId))
  const changes = toIndex > fromIndex ? changesBetween(history, fromIndex, toIndex) : {}
  const labels = historyLabels(history)  // includes retired skills
  const items = [...previous.priorities].sort((a, b) => a.rank - b.rank).map(priority => {
    const change = RATING_CHANGES.includes(changes[priority.skill_id]) ? changes[priority.skill_id] : null
    return {
      skill_id: priority.skill_id,
      label: labels[priority.skill_id] ?? null,
      rank: priority.rank,
      coach_note: priority.coach_note ?? null,
      before: before[priority.skill_id] ?? null,
      now: now[priority.skill_id] ?? null,
      trend: change === 'retired' ? 'retired' : trend(before[priority.skill_id], now[priority.skill_id]),
      change,
    }
  })
  // A move to another playing group since then: the scores are judged against different cohorts.
  const nowRow = history.find(row => row.period_id === Number(periodId))
  const groupChange = previous.age_group && nowRow?.age_group && previous.age_group !== nowRow.age_group ? { from: previous.age_group, to: nowRow.age_group } : null
  return { periodId: earlier.id, periodLabel: earlier.label, items, groupChange }
}

// Why a priority row holds its skill: the algorithm's pick for that rank, one of last
// period's priorities carried into this period, or the coach's own override.
export const PRIORITY_TAGS = { suggested: 'Suggested', carried: 'Carried over', override: 'Override' }

export function priorityTag(skillId, suggestedId, previousIds = []) {
  if (skillId === suggestedId) return 'suggested'
  return previousIds.includes(skillId) ? 'carried' : 'override'
}

// Rows after keeping skillId: it replaces the lowest-ranked row that is not itself a kept
// previous priority, or is appended when fewer than three rows exist.
export function keepPriority(rows, skillId, previousIds, max = 3) {
  if (rows.some(row => row.skill_id === skillId)) return rows
  if (rows.length < max) return [...rows, { skill_id: skillId, coach_note: '' }]
  for (let i = rows.length - 1; i >= 0; i--) {
    if (!previousIds.includes(rows[i].skill_id)) return rows.map((row, idx) => idx === i ? { skill_id: skillId, coach_note: '' } : row)
  }
  return rows
}

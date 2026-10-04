// Turns the player-safe report payload into what the report shows. Coach scores only.
import { ratingMap, sectionAverages, skillCallouts } from './assessment'
import { priorityFollowUp } from './followUpModel'
import { POSITION_LABELS, norm, scaleAnchors } from './matrix'

export const REPORT_TRENDS = {
  improved: 'Improved',
  unchanged: 'Holding steady',
  worse: 'Needs more work',
  pending: 'Not yet assessed',
}

const positionLabel = id => POSITION_LABELS[norm(id)] ?? id

export function buildReport(matrix, report) {
  const names = Object.fromEntries(matrix.sections.flatMap(section => section.skills.map(skill => [skill.id, skill.label])))
  const history = report.history
  const current = history.find(row => row.period_id === report.period_id)
  const coach = current?.assessments.coach ?? null
  const newestFirst = [...history].reverse().map(row => ({ id: row.period_id, label: row.label }))
  const followUp = priorityFollowUp(newestFirst, history, report.period_id, coach)
  const anchors = scaleAnchors(matrix)
  const base = {
    player: report.player, team: report.team, period: report.period, message: report.message,
    scale: Object.entries(anchors).map(([point, label]) => `${point} ${label}`).join(', '),
    followUp: followUp && { label: followUp.periodLabel, items: followUp.items.map(item => ({ ...item, label: names[item.skill_id] ?? item.skill_id })) },
  }
  if (!coach) return { ...base, assessed: false }

  const coachMap = ratingMap(coach)
  const assessed = history.filter(row => row.assessments.coach)
  const sections = sectionAverages(matrix, coach.position, coachMap, {}).map(section => ({ id: section.id, label: section.label, score: section.coach }))
  return {
    ...base,
    assessed: true,
    position: [positionLabel(coach.primary_position), coach.secondary_position && `also ${positionLabel(coach.secondary_position)}`].filter(Boolean).join(', '),
    sections,
    strengths: skillCallouts(matrix, coach.position, coachMap, {}).top.map(skill => ({ label: skill.label, score: skill.score })),
    priorities: [...(current.priorities ?? [])].sort((a, b) => a.rank - b.rank).map(p => ({ rank: p.rank, label: names[p.skill_id] ?? p.skill_id, note: p.coach_note })),
    trend: {
      periods: assessed.map(row => row.label),
      rows: sections.map(section => ({
        label: section.label,
        values: assessed.map(row => {
          const match = sectionAverages(matrix, row.assessments.coach.position, ratingMap(row.assessments.coach), {}).find(s => s.id === section.id)
          return match?.coach ?? null
        }),
      })),
    },
  }
}

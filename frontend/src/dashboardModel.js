export const AREAS = [
  { id: 'assessment', label: 'Assessment', short: 'Assess', icon: 'assessment', subtitle: 'Record coach ratings' },
  { id: 'player-data', label: 'Player Data', short: 'Player', icon: 'player', subtitle: 'Individual insights and progress' },
  { id: 'team-data', label: 'Team Data', short: 'Team', icon: 'team', subtitle: 'Squad-wide skill picture' },
  { id: 'development', label: 'Development', short: 'Develop', icon: 'development', subtitle: 'Confirm coaching priorities' },
  { id: 'settings', label: 'Settings', short: 'Settings', icon: 'settings', subtitle: 'Teams, periods and squad' },
]

export const TEAM_DATA_TABS = [
  ['heatmap', 'Heatmap'],
  ['trends', 'Trends'],
  ['priorities', 'Priorities'],
  ['positions', 'Positions'],
]

export const PLAYER_GENDERS = [
  ['girls', 'Girls (she / her)'],
  ['boys', 'Boys (he / him)'],
  ['mixed', 'Mixed (they / them)'],
]

// U5 to U21; a playing group is the "U" number.
export const AGE_GROUPS = Array.from({ length: 17 }, (_, i) => i + 5)

// The playing groups of the active players: one group (the drill library filters by it), a span, or none set.
export function squadGroups(players, groups) {
  const ages = [...new Set(players.filter(p => p.active).map(p => groups[p.id]).filter(Boolean))].sort((a, b) => a - b)
  return { single: ages.length === 1 ? ages[0] : null, span: ages.length > 1 ? [ages[0], ages.at(-1)] : null }
}

// Playing groups present among the active players, with counts, largest first (ties: younger first). The first is
// the default for Team data, so its views do not mix ratings judged against different cohorts.
export function groupCounts(players, groups) {
  const counts = {}
  for (const p of players.filter(p => p.active)) if (groups[p.id]) counts[groups[p.id]] = (counts[groups[p.id]] ?? 0) + 1
  return Object.entries(counts).map(([age, n]) => ({ age: Number(age), players: n })).sort((a, b) => b.players - a.players || a.age - b.age)
}

// A new season's proposal: every active player one age group up from the latest period (empty where none was set).
export const movedUp = (players, groups) => Object.fromEntries(players.filter(p => p.active).map(p => [p.id, groups[p.id] ? String(Math.min(groups[p.id] + 1, 21)) : '']))

export const PLAYER_DATA_TABS = [
  ['summary', 'Summary'],
  ['comparison', 'Comparison'],
  ['progress', 'Progress'],
  ['priorities', 'Confirmed priorities'],
  ['report', 'Report'],
]

// The Comparison tab compares coach and self ratings, so it only exists while the team uses self-assessment.
export const playerDataTabs = selfAssessmentOn => PLAYER_DATA_TABS.filter(([id]) => selfAssessmentOn || id !== 'comparison')

const filledNotes = notes => Object.fromEntries(Object.entries(notes).filter(([, note]) => note?.trim()).map(([id, note]) => [id, note.trim()]))

export const assessmentSignature = (position, secondary, frequency, ratings, notes = {}, note = '', carried = []) =>
  JSON.stringify({ position, secondary, frequency: secondary ? frequency : null, ratings, notes: filledNotes(notes), note: note.trim(), carried: [...carried].sort() })

// Editable form state for a saved coach assessment. Without one, positions come from the player's
// previous coach assessment (ratings and notes always start empty).
export function formFromAssessment(assessment, previous = null) {
  const rows = assessment?.ratings ?? []
  const positions = assessment ?? previous
  return {
    position: positions?.primary_position ?? 'defender',
    secondary: positions?.secondary_position ?? '',
    frequency: positions?.secondary_position_frequency ?? 'sometimes',
    ratings: Object.fromEntries(rows.map(r => [r.skill_id, r.score])),
    notes: Object.fromEntries(rows.filter(r => r.note).map(r => [r.skill_id, r.note])),
    note: assessment?.note ?? '',
    // Scores copied from the previous period and not yet reviewed this period.
    carried: rows.filter(r => r.carried && r.score != null).map(r => r.skill_id),
  }
}

export const formSignature = form => assessmentSignature(form.position, form.secondary, form.frequency, form.ratings, form.notes, form.note, form.carried)

export const initialPlayerId = players => String(players.find(player => player.active)?.id ?? players[0]?.id ?? '')
export const initialPeriodId = periods => String(periods.find(period => period.is_active)?.id ?? periods[0]?.id ?? '')
export const canManageTeam = team => team?.role === 'owner'

// The player's coach assessment from the nearest earlier period, else their most recent one.
// periods: newest first (as the API returns them); history: oldest first.
export function previousCoachAssessment(history, periods, periodId) {
  const assessed = new Map(history.filter(row => row.assessments.coach && row.period_id !== Number(periodId)).map(row => [row.period_id, row.assessments.coach]))
  const index = periods.findIndex(period => period.id === Number(periodId))
  const earlier = periods.slice(index + 1).find(period => assessed.has(period.id))
  return earlier ? assessed.get(earlier.id) : [...assessed.values()].at(-1) ?? null
}

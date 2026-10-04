export const AREAS = [
  { id: 'assessment', label: 'Assessment', short: 'Assess', icon: 'assessment', subtitle: 'Record coach ratings' },
  { id: 'player-data', label: 'Player Data', short: 'Player', icon: 'player', subtitle: 'Individual insights and progress' },
  { id: 'team-data', label: 'Team Data', short: 'Team', icon: 'team', subtitle: 'Squad-wide skill picture' },
  { id: 'development', label: 'Development', short: 'Develop', icon: 'development', subtitle: 'Confirm coaching priorities' },
  { id: 'settings', label: 'Settings', short: 'Settings', icon: 'settings', subtitle: 'Teams, periods and squad' },
]

export const PLAYER_DATA_TABS = [
  ['summary', 'Summary'],
  ['comparison', 'Comparison'],
  ['progress', 'Progress'],
  ['priorities', 'Confirmed priorities'],
  ['report', 'Report'],
]

const filledNotes = notes => Object.fromEntries(Object.entries(notes).filter(([, note]) => note?.trim()).map(([id, note]) => [id, note.trim()]))

export const assessmentSignature = (position, secondary, frequency, ratings, notes = {}, note = '') =>
  JSON.stringify({ position, secondary, frequency: secondary ? frequency : null, ratings, notes: filledNotes(notes), note: note.trim() })

// Editable form state for a saved coach assessment (or an empty form when there is none).
export function formFromAssessment(assessment) {
  const rows = assessment?.ratings ?? []
  return {
    position: assessment?.primary_position ?? 'defender',
    secondary: assessment?.secondary_position ?? '',
    frequency: assessment?.secondary_position_frequency ?? 'sometimes',
    ratings: Object.fromEntries(rows.map(r => [r.skill_id, r.score])),
    notes: Object.fromEntries(rows.filter(r => r.note).map(r => [r.skill_id, r.note])),
    note: assessment?.note ?? '',
  }
}

export const formSignature = form => assessmentSignature(form.position, form.secondary, form.frequency, form.ratings, form.notes, form.note)

export const initialPlayerId = players => String(players.find(player => player.active)?.id ?? players[0]?.id ?? '')
export const initialPeriodId = periods => String(periods.find(period => period.is_active)?.id ?? periods[0]?.id ?? '')
export const canManageTeam = team => team?.role === 'owner'

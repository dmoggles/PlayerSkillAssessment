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
]

export const assessmentSignature = (position, secondary, frequency, ratings) =>
  JSON.stringify({ position, secondary, frequency: secondary ? frequency : null, ratings })

export const initialPlayerId = players => String(players.find(player => player.active)?.id ?? players[0]?.id ?? '')
export const initialPeriodId = periods => String(periods.find(period => period.is_active)?.id ?? periods[0]?.id ?? '')
export const canManageTeam = team => team?.role === 'owner'

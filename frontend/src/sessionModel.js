// Team training sessions: labels and the list's upcoming and past halves.
export const SESSION_LENGTHS = [45, 60, 75, 90]
export const PHASE_NAMES = { warm_up: 'Warm-up', technical: 'Technical', opposed: 'Opposed', small_sided_game: 'Small-sided game', full_squad_game: 'Full squad game', cool_down: 'Cool-down' }
// The planner's default breakdown for each length (TEMPLATES in backend/app/sessions.py).
export const DEFAULT_BREAKDOWNS = {
  45: { warm_up: 8, technical: 12, opposed: 12, small_sided_game: 10, cool_down: 3 },
  60: { warm_up: 10, technical: 15, opposed: 15, small_sided_game: 15, cool_down: 5 },
  75: { warm_up: 10, technical: 20, opposed: 20, small_sided_game: 20, cool_down: 5 },
  90: { warm_up: 12, technical: 20, opposed: 25, small_sided_game: 25, cool_down: 8 },
}

// "Warm-up 10 · Technical 20 · Cool-down 5": the parts a breakdown includes, in session order.
export const breakdownText = minutes => Object.keys(PHASE_NAMES).filter(p => Number(minutes[p]) > 0).map(p => `${PHASE_NAMES[p]} ${Number(minutes[p])}`).join(' · ')

export const templateTotal = minutes => Object.values(minutes).reduce((sum, m) => sum + (Number(m) || 0), 0)

// What stops a template draft from being saved (the server checks the same).
export function templateProblems({ name, length, minutes }) {
  const problems = []
  if (!name.trim()) problems.push('Give the template a name.')
  const total = Number(length)
  if (!Number.isInteger(total) || total < 15 || total > 150) problems.push('The length is 15 to 150 minutes.')
  const parts = Object.values(minutes).filter(m => m !== '' && m !== null && m !== undefined).map(Number)
  if (!parts.some(m => m > 0)) problems.push('Give at least one part some minutes.')
  else if (parts.some(m => !Number.isInteger(m) || m < 0 || m > 90)) problems.push('Each part takes up to 90 minutes.')
  else if (Number.isInteger(total) && templateTotal(minutes) !== total) problems.push(`The parts add up to ${templateTotal(minutes)} of ${total} minutes.`)
  return problems
}

const today = () => new Date().toISOString().slice(0, 10)

// Upcoming sessions soonest first; past ones latest first. Today's sessions count as upcoming.
export function splitSessions(sessions, now = today()) {
  const upcoming = sessions.filter(s => s.date >= now).sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id)
  const past = sessions.filter(s => s.date < now).sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id)
  return { upcoming, past }
}

export const sessionDate = (date, time) => {
  const day = new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  return time ? `${day}, ${time}` : day
}

// The start time of each block, from the session's start (or from 0:00 when there is none).
export function blockTimes(blocks, start = null) {
  let minutes = 0
  return blocks.map(block => {
    const at = minutes
    minutes += block.minutes
    if (!start) return `${at}′`
    const [h, m] = start.split(':').map(Number)
    const total = h * 60 + m + at
    return `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
  })
}

export const versionLabel = version => version ? `${version.kind === 'base' ? 'Base' : version.kind === 'regression' ? 'Easier' : 'Harder'}: ${version.title}` : 'Base version'

// A focus suggestion's chip text: "Short passing · 5 players".
export const focusChip = focus => `${focus.label}${focus.players ? ` · ${focus.players} ${focus.players === 1 ? 'player' : 'players'}` : ''}`

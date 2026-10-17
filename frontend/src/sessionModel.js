// Team training sessions: labels and the list's upcoming and past halves.
export const SESSION_LENGTHS = [45, 60, 75, 90]
export const PHASE_NAMES = { warm_up: 'Warm-up', technical: 'Technical', opposed: 'Opposed', small_sided_game: 'Small-sided game', cool_down: 'Cool-down' }

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

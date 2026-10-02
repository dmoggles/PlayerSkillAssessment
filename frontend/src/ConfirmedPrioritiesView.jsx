import { useEffect, useState } from 'react'
import { getPlayerHistory } from './api'

const MEDALS = {
  1: { icon: '🥇', label: 'Gold medal' },
  2: { icon: '🥈', label: 'Silver medal' },
  3: { icon: '🥉', label: 'Bronze medal' },
}

function PriorityCards({ priorities, names }) {
  return <div className="confirmed-priority-grid">{[...priorities].sort((a, b) => a.rank - b.rank).map(priority => {
    const medal = MEDALS[priority.rank] ?? { icon: '🏅', label: 'Medal' }
    return <article className="confirmed-priority-card" key={priority.rank}>
      <div className="confirmed-priority-card-head"><span className="priority-medal" role="img" aria-label={medal.label}>{medal.icon}</span><span className="priority-rank-label">Priority {priority.rank}</span></div>
      <h4>{names[priority.skill_id] ?? priority.skill_id}</h4>
      {priority.coach_note?.trim() && <p className="confirmed-priority-note">{priority.coach_note.trim()}</p>}
    </article>
  })}</div>
}

export function ConfirmedPrioritiesView({ matrix, history, periodId }) {
  const names = Object.fromEntries(matrix.sections.flatMap(section => section.skills.map(skill => [skill.id, skill.label])))
  const selected = history.find(row => row.period_id === Number(periodId))
  const otherPeriods = history.filter(row => row.period_id !== Number(periodId) && row.priorities.length)

  return <div className="confirmed-priorities">
    <h3>{selected?.label ?? 'Selected period'}</h3>
    {selected?.priorities.length
      ? <PriorityCards priorities={selected.priorities} names={names} />
      : <p className="muted">No confirmed priorities for this period yet. Confirm them in Development.</p>}
    {otherPeriods.length > 0 && <details className="other-priorities"><summary>Confirmed priorities from other periods</summary>{otherPeriods.map(row => <section key={row.period_id}><h3>{row.label}</h3><PriorityCards priorities={row.priorities} names={names} /></section>)}</details>}
  </div>
}

export default function ConfirmedPrioritiesPanel({ matrix, teamId, playerId, periodId }) {
  const [history, setHistory] = useState([])
  const [state, setState] = useState('loading')

  useEffect(() => {
    let live = true
    getPlayerHistory(teamId, playerId).then(rows => { if (live) { setHistory(rows); setState('ready') } }).catch(() => { if (live) setState('error') })
    return () => { live = false }
  }, [teamId, playerId])

  if (state === 'loading') return <p className="muted" role="status">Loading confirmed priorities…</p>
  if (state === 'error') return <p className="error" role="alert">Could not load confirmed priorities. Please try again.</p>
  return <ConfirmedPrioritiesView matrix={matrix} history={history} periodId={periodId} />
}

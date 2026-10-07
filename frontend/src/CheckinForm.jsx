import { useState } from 'react'
import { CHECKIN } from './followUpModel'

// End of a development cycle: how each focus skill went (better, same or worse, plus an optional note),
// recorded as the next cycle starts. It can be skipped; it never changes the period assessment.
export default function CheckinForm({ cycle, names, onSubmit, onSkip, onCancel }) {
  const [entries, setEntries] = useState(() => Object.fromEntries(cycle.priorities.map(p => [p.skill_id, { trend: '', note: '' }])))
  const [busy, setBusy] = useState(false)
  const set = (skill, patch) => setEntries(e => ({ ...e, [skill]: { ...e[skill], ...patch } }))
  const complete = cycle.priorities.every(p => entries[p.skill_id].trend)
  const run = async action => { setBusy(true); try { await action() } finally { setBusy(false) } }
  const submit = event => {
    event.preventDefault()
    run(() => onSubmit(cycle.priorities.map(p => ({ skill_id: p.skill_id, trend: entries[p.skill_id].trend, note: entries[p.skill_id].note.trim() || null }))))
  }
  return <form className="checkin-form" onSubmit={submit} aria-labelledby="checkin-title">
    <h3 id="checkin-title">Check-in: how did cycle {cycle.number} go?</h3>
    <p className="muted hint">For each focus skill, compared with the start of this cycle. This is kept with the cycle and does not change the period's ratings.</p>
    {cycle.priorities.map(p => <fieldset key={p.skill_id} className="checkin-skill">
      <legend>{names[p.skill_id] ?? p.skill_id}</legend>
      <div className="checkin-choices">{Object.entries(CHECKIN).map(([trend, { label }]) => <label key={trend} className={`checkin-choice${entries[p.skill_id].trend === trend ? ' active' : ''}`}>
        <input type="radio" name={`checkin-${p.skill_id}`} value={trend} checked={entries[p.skill_id].trend === trend} onChange={() => set(p.skill_id, { trend })} /> {label}
      </label>)}</div>
      <input type="text" maxLength={300} placeholder="Optional note" aria-label={`Note for ${names[p.skill_id] ?? p.skill_id}`} value={entries[p.skill_id].note} onChange={e => set(p.skill_id, { note: e.target.value })} />
    </fieldset>)}
    <div className="inline-row">
      <button type="submit" disabled={!complete || busy}>Save check-in and start cycle {cycle.number + 1}</button>
      <button type="button" disabled={busy} onClick={() => run(onSkip)}>Skip check-in</button>
      <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>
    </div>
  </form>
}

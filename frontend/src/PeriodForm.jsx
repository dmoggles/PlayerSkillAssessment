import { useState } from 'react'
import { createPeriod, errorMessage, getPeriodGroups } from './api'
import { AGE_GROUPS, movedUp } from './dashboardModel'

// Adds a period. Playing groups carry over from the latest period; a period that starts a new season first shows
// every player moved up an age group, to adjust before it is created.
export default function PeriodForm({ teamId, players, latestPeriod, onCreated, onMessage }) {
  const [label, setLabel] = useState('')
  const [newSeason, setNewSeason] = useState(false)
  const [review, setReview] = useState(null)
  const [busy, setBusy] = useState(false)

  const create = async options => {
    setBusy(true)
    try { const period = await createPeriod(teamId, label.trim(), options); setLabel(''); setNewSeason(false); setReview(null); onCreated(period) }
    catch (e) { onMessage(errorMessage(e)) }
    finally { setBusy(false) }
  }
  const submit = async event => {
    event.preventDefault()
    if (!newSeason) return create({})
    if (!review) {
      try { setReview(movedUp(players, latestPeriod ? await getPeriodGroups(teamId, latestPeriod.id) : {})) } catch (e) { onMessage(errorMessage(e)) }
      return
    }
    create({ starts_season: true, groups: Object.fromEntries(Object.entries(review).map(([id, age]) => [id, age ? Number(age) : null])) })
  }

  return <form className="period-form" onSubmit={submit}>
    <div className="inline-row">
      <input aria-label="New period label" placeholder="New period label" required maxLength={100} value={label} onChange={e => setLabel(e.target.value)} disabled={Boolean(review)} />
      <button disabled={busy}>{review ? 'Create period' : newSeason ? 'Next: playing groups' : 'Add period'}</button>
    </div>
    <label className="checkbox"><input type="checkbox" checked={newSeason} disabled={Boolean(review)} onChange={e => setNewSeason(e.target.checked)} /> This period starts a new season</label>
    {review && <div className="season-review">
      <p className="muted">Everyone moves up one age group. Adjust anyone who is staying or playing up, then create the period.</p>
      <div className="settings-list">{players.filter(p => p.active).map(p => <label key={p.id} className="settings-item season-review-row">
        <span>{p.name}</span>
        <select aria-label={`${p.name}'s playing group`} value={review[p.id] ?? ''} onChange={e => setReview(r => ({ ...r, [p.id]: e.target.value }))}>
          <option value="">Not set</option>{AGE_GROUPS.map(age => <option key={age} value={age}>U{age}</option>)}
        </select>
      </label>)}</div>
      <button type="button" className="link-btn" onClick={() => setReview(null)}>Back</button>
    </div>}
  </form>
}

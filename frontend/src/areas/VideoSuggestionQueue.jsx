import { useEffect, useState } from 'react'
import { approveVideoSuggestion, errorMessage, getVideoSuggestionQueue, rejectVideoSuggestion } from '../api'
import { VideoLink } from '../DrillLibrary'
import { REJECT_REASONS, REVIEW_CHECKS } from '../drillModel'
import { Section } from './DashboardParts'

const LISTS = { pending: 'Waiting for review', approved: 'Approved', rejected: 'Turned down' }
const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const length = seconds => seconds == null ? null : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
const variationName = v => `${v.kind === 'base' ? 'Base' : v.kind === 'regression' ? 'Easier' : 'Harder'}: ${v.title}`

// Site admins: review coaches' video suggestions, and take approved videos down again.
export default function VideoSuggestionQueue({ onMessage }) {
  const [list, setList] = useState('pending')
  // The loaded list remembers which tab it belongs to, so switching tabs shows "Loading…" until the new one arrives.
  const [loaded, setLoaded] = useState({ list: null, items: [] })
  const [waiting, setWaiting] = useState(null)
  useEffect(() => {
    let live = true
    getVideoSuggestionQueue(list).then(value => {
      if (!live) return
      setLoaded({ list, items: value })
      if (list === 'pending') setWaiting(value.length)
    }).catch(e => onMessage(errorMessage(e, 'Could not load video suggestions.')))
    return () => { live = false }
  }, [list, onMessage])
  const items = loaded.list === list ? loaded.items : null

  const done = (item, message) => {
    setLoaded(previous => ({ ...previous, items: previous.items.filter(i => i.id !== item.id) }))
    if (list === 'pending') setWaiting(count => Math.max(0, (count ?? 1) - 1))
    onMessage(message)
  }

  return <Section title={`Video suggestions${waiting ? ` (${waiting} waiting)` : ''}`} description="Videos coaches suggest for drills. Nothing is shown until you approve it; approved videos are shown to every coach, and to players in shared reports.">
    <div className="queue-tabs" role="group" aria-label="Which suggestions">
      {Object.entries(LISTS).map(([id, label]) => <button key={id} type="button" aria-pressed={list === id} className={list === id ? 'active' : ''} onClick={() => setList(id)}>{label}</button>)}
    </div>
    {items === null ? <p className="muted" role="status">Loading…</p>
      : !items.length ? <p className="muted">{list === 'pending' ? 'No suggestions waiting.' : 'None yet.'}</p>
      : <ul className="video-queue">{items.map(item => <SuggestionReview key={item.id} item={item} onDone={done} onMessage={onMessage} />)}</ul>}
  </Section>
}

export function SuggestionReview({ item, onDone, onMessage }) {
  const [caption, setCaption] = useState(item.caption ?? item.title)
  const [variationId, setVariationId] = useState(item.variation_id ?? '')
  const [checked, setChecked] = useState(REVIEW_CHECKS.map(() => false))
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const host = item.url.includes('vimeo.com') ? 'Vimeo' : 'YouTube'
  const variation = item.variations.find(v => v.id === item.variation_id)

  const act = async (call, message) => {
    setBusy(true)
    try { await call(); onDone(item, message) } catch (e) { onMessage(errorMessage(e, 'Could not save the review.')); setBusy(false) }
  }
  const approve = event => {
    event.preventDefault()
    act(() => approveVideoSuggestion(item.id, { caption, variation_id: variationId === '' ? null : Number(variationId) }), `Added “${caption}” to ${item.drill_title}.`)
  }
  const reject = event => {
    event.preventDefault()
    act(() => rejectVideoSuggestion(item.id, { reason, note }), item.status === 'approved' ? `Took the video off ${item.drill_title}.` : 'Suggestion turned down.')
  }

  return <li className="video-review">
    <header>
      <strong>{item.drill_title}</strong>{variation && <span className="muted"> · {variationName(variation)}</span>}
      <small className="muted">Suggested {day(item.created_at)} by {item.suggested_by ?? 'a deleted account'}{item.reports ? ` · reported ${item.reports} ${item.reports === 1 ? 'time' : 'times'}` : ''}</small>
    </header>
    <p className="video-review-title"><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
      <span className="muted"> · {item.channel || 'Unknown channel'}{length(item.duration_seconds) ? ` · ${length(item.duration_seconds)}` : ''} · <a href={item.url} target="_blank" rel="noreferrer">Open on {host}</a></span></p>
    {item.note && <blockquote>{item.note}</blockquote>}
    <VideoLink video={{ id: item.id, url: item.url, start_seconds: item.start_seconds, caption: '' }} />
    {item.status === 'rejected' && <p className="muted">Turned down: {REJECT_REASONS[item.reject_reason]}{item.reject_note ? `: ${item.reject_note}` : ''}</p>}

    {item.status !== 'approved' && <form className="video-review-approve" onSubmit={approve}>
      <div className="field"><label htmlFor={`caption-${item.id}`}>Caption</label>
        <input id={`caption-${item.id}`} required maxLength={200} value={caption} onChange={e => setCaption(e.target.value)} /></div>
      <div className="field"><label htmlFor={`variation-${item.id}`}>Shows</label>
        <select id={`variation-${item.id}`} value={variationId} onChange={e => setVariationId(e.target.value)}>
          <option value="">The whole drill</option>
          {item.variations.map(v => <option key={v.id} value={v.id}>{variationName(v)}</option>)}
        </select></div>
      <fieldset className="review-checks"><legend>Before approving</legend>
        {REVIEW_CHECKS.map((text, i) => <label key={text} className="checkbox"><input type="checkbox" checked={checked[i]} onChange={e => setChecked(previous => previous.map((c, j) => (j === i ? e.target.checked : c)))} /> {text}</label>)}
      </fieldset>
      <button type="submit" className="primary-btn" disabled={busy || !checked.every(Boolean)}>Approve</button>
    </form>}

    {item.status !== 'rejected' && <form className="video-review-reject" onSubmit={reject}>
      <div className="field"><label htmlFor={`reason-${item.id}`}>{item.status === 'approved' ? 'Take down because' : 'Turn down because'}</label>
        <select id={`reason-${item.id}`} required value={reason} onChange={e => setReason(e.target.value)}>
          <option value="">Choose a reason</option>
          {Object.entries(REJECT_REASONS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select></div>
      <div className="field"><label htmlFor={`note-${item.id}`}>Note to the coach <span className="muted">(optional)</span></label>
        <input id={`note-${item.id}`} maxLength={300} value={note} onChange={e => setNote(e.target.value)} /></div>
      <button type="submit" className="danger-btn" disabled={busy}>{item.status === 'approved' ? 'Take down' : 'Turn down'}</button>
    </form>}
  </li>
}

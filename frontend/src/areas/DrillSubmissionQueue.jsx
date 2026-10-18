import { useEffect, useState } from 'react'
import { acceptDrillSubmission, declineDrillSubmission, errorMessage, getDrillSubmissionQueue, getDrillSubmissionRow } from '../api'
import { VideoLink } from '../DrillLibrary'
import { FORMAT_LABELS, PHASE_LABELS, equipmentLabel, playersText } from '../drillModel'
import { Section } from './DashboardParts'

const LISTS = { pending: 'Waiting for review', accepted: 'Being written up', declined: 'Declined', published: 'In the library' }
const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const kindName = kind => (kind === 'base' ? 'Base' : kind === 'regression' ? 'Easier' : 'Harder')

// Site admins: drills teams offer to the shared library. Accepting doesn't publish: it reserves the drill's library
// slug and gives its data-file row, to write up with diagrams in the next drills file. Loading that file publishes it.
export default function DrillSubmissionQueue({ onMessage }) {
  const [list, setList] = useState('pending')
  const [loaded, setLoaded] = useState({ list: null, items: [] })
  const [waiting, setWaiting] = useState(null)
  useEffect(() => {
    let live = true
    getDrillSubmissionQueue(list).then(value => {
      if (!live) return
      setLoaded({ list, items: value })
      if (list === 'pending') setWaiting(value.length)
    }).catch(e => onMessage(errorMessage(e, 'Could not load drill submissions.')))
    return () => { live = false }
  }, [list, onMessage])
  const items = loaded.list === list ? loaded.items : null
  const done = (item, message) => {
    setLoaded(previous => ({ ...previous, items: previous.items.filter(i => i.id !== item.id) }))
    if (list === 'pending') setWaiting(count => Math.max(0, (count ?? 1) - 1))
    onMessage(message)
  }
  return <Section title={`Drill submissions${waiting ? ` (${waiting} waiting)` : ''}`} description="Drills teams offer to the shared library. Accepting reserves a library slug; the drill is published once it's written up with diagrams in a drills file and loaded.">
    <div className="queue-tabs" role="group" aria-label="Which submissions">
      {Object.entries(LISTS).map(([id, label]) => <button key={id} type="button" aria-pressed={list === id} className={list === id ? 'active' : ''} onClick={() => setList(id)}>{label}</button>)}
    </div>
    {items === null ? <p className="muted" role="status">Loading…</p>
      : !items.length ? <p className="muted">{list === 'pending' ? 'No drills waiting.' : 'None yet.'}</p>
      : <ul className="video-queue">{items.map(item => <SubmissionReview key={item.id} item={item} onDone={done} onMessage={onMessage} />)}</ul>}
  </Section>
}

export function SubmissionReview({ item, onDone, onMessage }) {
  const { drill } = item
  const [slug, setSlug] = useState(item.library_slug ?? '')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const act = async (call, message) => {
    setBusy(true)
    try { await call(); onDone(item, message) } catch (e) { onMessage(errorMessage(e, 'Could not save the review.')); setBusy(false) }
  }
  const download = async () => {
    try {
      const row = await getDrillSubmissionRow(item.id)
      const link = document.createElement('a')
      link.href = URL.createObjectURL(new Blob([JSON.stringify(row, null, 2) + '\n'], { type: 'application/json' }))
      link.download = `${row.slug}.json`
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (e) { onMessage(errorMessage(e, 'Could not get the row.')) }
  }
  const video = drill.media.find(m => m.kind === 'video')
  return <li className="video-review drill-review">
    <header>
      <strong>{drill.title}</strong>
      <small className="muted">From {item.team ?? 'a deleted team'} · {day(item.created_at)}{item.library_slug ? ` · library slug ${item.library_slug}` : ''}</small>
    </header>
    <p className="drill-facts">{PHASE_LABELS[drill.session_phase]} · {FORMAT_LABELS[drill.format]} · {playersText(drill.players)} · U{drill.ages[0]}–U{drill.ages[1]} · {drill.duration[0]}–{drill.duration[1]} min{drill.space ? ` · ${drill.space[0]}×${drill.space[1]} m` : ''}</p>
    <p className="drill-tags">{drill.tags.map(t => <span key={t.id} className={`status-pill ${t.weight === 1 ? 'info-pill' : 'muted-pill'}`}>{t.label}</span>)}</p>
    {item.note && <blockquote>{item.note}</blockquote>}
    {drill.summary && <p>{drill.summary}</p>}
    <p><strong>Set-up:</strong> {drill.setup}</p>
    {drill.equipment.length > 0 && <p><strong>Equipment:</strong> {drill.equipment.map(e => `${e.quantity ?? ''} ${equipmentLabel(e.item)}`.trim()).join(', ')}</p>}
    <ol>{drill.instructions.map(step => <li key={step}>{step}</li>)}</ol>
    {drill.coaching_points.length > 0 && <ul>{drill.coaching_points.map(point => <li key={point}>{point}</li>)}</ul>}
    {drill.variations.length > 1 && <ul className="drill-review-versions">{drill.variations.map(v => <li key={v.id}><strong>{kindName(v.kind)}: {v.title}</strong>{v.kind !== 'base' && ` · ${v.change}`}</li>)}</ul>}
    {video && <VideoLink video={{ id: video.id, url: video.url, caption: '' }} />}
    {item.status === 'declined' && <p className="muted">Declined: {item.reason}</p>}

    {item.status === 'accepted' && <div className="inline-row"><button type="button" className="primary-btn" onClick={download}>Download row</button>
      <span className="muted">Add it to the next drills file with diagrams; loading the file publishes it.</span></div>}
    {(item.status === 'pending' || item.status === 'declined') && <form className="video-review-approve" onSubmit={e => { e.preventDefault(); act(() => acceptDrillSubmission(item.id, slug.trim()), `Accepted ${drill.title} for the library.`) }}>
      <div className="field"><label htmlFor={`slug-${item.id}`}>Library slug <span className="muted">(empty: from the name)</span></label>
        <input id={`slug-${item.id}`} maxLength={80} value={slug} onChange={e => setSlug(e.target.value)} placeholder="for-example-four-corner-passing" /></div>
      <button type="submit" className="primary-btn" disabled={busy}>Accept for the library</button>
    </form>}
    {(item.status === 'pending' || item.status === 'accepted') && <form className="video-review-reject" onSubmit={e => { e.preventDefault(); act(() => declineDrillSubmission(item.id, reason.trim()), 'Submission declined.') }}>
      <div className="field"><label htmlFor={`decline-${item.id}`}>Decline because <span className="muted">(the team sees this)</span></label>
        <input id={`decline-${item.id}`} required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} placeholder="For example: very like Passing through gates" /></div>
      <button type="submit" className="danger-btn" disabled={busy || !reason.trim()}>Decline</button>
    </form>}
  </li>
}

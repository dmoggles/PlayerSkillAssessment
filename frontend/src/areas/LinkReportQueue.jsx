import { useEffect, useState } from 'react'
import { errorMessage, getLinkReportQueue, handleLinkReport } from '../api'
import { LINK_REPORT_REASONS } from '../drillModel'
import { Section } from './DashboardParts'

const LISTS = { open: 'Reported', hidden: 'Hidden' }
const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

// Site admins: links coaches reported on library drills. Hiding takes the link off the drill for everyone.
export default function LinkReportQueue({ onMessage }) {
  const [list, setList] = useState('open')
  const [loaded, setLoaded] = useState({ list: null, items: [] })
  const [waiting, setWaiting] = useState(null)
  useEffect(() => {
    let live = true
    getLinkReportQueue(list).then(value => {
      if (!live) return
      setLoaded({ list, items: value })
      if (list === 'open') setWaiting(value.length)
    }).catch(e => onMessage(errorMessage(e, 'Could not load reported links.')))
    return () => { live = false }
  }, [list, onMessage])
  const items = loaded.list === list ? loaded.items : null

  const act = async (item, action, message) => {
    try {
      await handleLinkReport(item.id, action)
      setLoaded(previous => ({ ...previous, items: previous.items.filter(i => i.id !== item.id) }))
      if (list === 'open') setWaiting(count => Math.max(0, (count ?? 1) - 1))
      onMessage(message)
    } catch (e) { onMessage(errorMessage(e, 'Could not save that.')) }
  }

  return <Section title={`Reported links${waiting ? ` (${waiting} waiting)` : ''}`} description="Videos and links on library drills that coaches say don't work or shouldn't be there. Hiding one takes it off the drill for everyone, even when the drill files are loaded again.">
    <div className="queue-tabs" role="group" aria-label="Which links">
      {Object.entries(LISTS).map(([id, label]) => <button key={id} type="button" aria-pressed={list === id} className={list === id ? 'active' : ''} onClick={() => setList(id)}>{label}</button>)}
    </div>
    {items === null ? <p className="muted" role="status">Loading…</p>
      : !items.length ? <p className="muted">{list === 'open' ? 'No reported links.' : 'None hidden.'}</p>
      : <ul className="video-queue">{items.map(item => <li key={item.id} className="video-review">
        <header>
          <strong>{item.drill_title}</strong>
          <span className="muted"> · {item.kind === 'link' ? 'Link' : 'Video'}{item.suggested ? ', suggested by a coach' : ', from the drill files'}</span>
          {list === 'hidden' && item.handled_at && <small className="muted">Hidden {day(item.handled_at)}</small>}
        </header>
        <p className="video-review-title"><a href={item.url} target="_blank" rel="noreferrer">{item.caption || item.url}</a>
          {!item.kind && <span className="muted"> · no longer on the drill</span>}</p>
        <ul className="link-reports">{item.reports.map((r, i) => <li key={i}>
          <strong>{LINK_REPORT_REASONS[r.reason]}</strong><span className="muted"> · {r.reported_by ?? 'a deleted account'}, {day(r.created_at)}</span>
          {r.note && <blockquote>{r.note}</blockquote>}
        </li>)}</ul>
        {list === 'open' && !item.suggested && <p className="muted hint">To replace or remove it for good, change the drill's data file.</p>}
        <div className="inline-row">
          {list === 'open' ? <>
            <button type="button" className="danger-btn" onClick={() => act(item, 'hide', `Hid the link on ${item.drill_title}.`)}>Hide from the drill</button>
            <button type="button" className="secondary-btn" onClick={() => act(item, 'keep', `Kept the link on ${item.drill_title}.`)}>It's fine, keep it</button>
          </> : <button type="button" className="secondary-btn" onClick={() => act(item, 'restore', `Put the link back on ${item.drill_title}.`)}>Show it again</button>}
        </div>
      </li>)}</ul>}
  </Section>
}

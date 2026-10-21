import { useState } from 'react'
import { errorMessage, reportDrillLink } from './api'
import { LINK_REPORT_REASONS } from './drillModel'

// On a library drill: a coach reports a video or link that doesn't work, or shouldn't be there. A site admin checks it.
export default function ReportLink({ drill, url }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState('')
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      setSent((await reportDrillLink(drill.slug, { url, reason, note })).message)
      setOpen(false)
    } catch (e) {
      setError(errorMessage(e, 'Could not send your report. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  if (sent) return <p className="notice report-link-sent" role="status">{sent}</p>
  return <div className="report-link">
    <button type="button" className="link-btn" aria-expanded={open} onClick={() => { setOpen(value => !value); setError('') }}>Report link</button>
    {open && <form className="stack" onSubmit={submit}>
      <fieldset><legend>What's wrong with it?</legend>
        {Object.entries(LINK_REPORT_REASONS).map(([id, label]) => <label key={id} className="checkbox">
          <input type="radio" name={`report-${url}`} value={id} required checked={reason === id} onChange={() => setReason(id)} /> {label}</label>)}
      </fieldset>
      <div className="field"><label htmlFor={`report-note-${url}`}>Anything to add <span className="muted">(optional)</span></label>
        <textarea id={`report-note-${url}`} rows={2} maxLength={500} value={note} onChange={e => setNote(e.target.value)} /></div>
      <div className="inline-row">
        <button type="submit" className="primary-btn" disabled={busy}>{busy ? 'Sending…' : 'Send report'}</button>
        <button type="button" className="link-btn" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>}
    {error && <p className="error" role="alert">{error}</p>}
  </div>
}

import { useEffect, useState } from 'react'
import { errorMessage, getMyVideoSuggestions, suggestVideo } from './api'
import { APP_NAME } from './brand'
import { REJECT_REASONS, SUGGESTION_STATUS } from './drillModel'

// On a drill: a coach suggests a video. A site admin checks every suggestion before other coaches see it.
// `prominent` when the drill has no video yet, so the invitation is more visible.
export function SuggestVideo({ drill, variation, prominent = false }) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [forVariation, setForVariation] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(null)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      setSent(await suggestVideo(drill.slug, { url: url.trim(), variation_id: forVariation && variation ? variation.id : null, note }))
      setUrl('')
      setNote('')
      setForVariation(false)
      setOpen(false)
    } catch (e) {
      setError(errorMessage(e, 'Could not send your suggestion. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  return <section className={`video-suggest${prominent ? ' prominent' : ''}`}>
    {prominent && !open && <p>No video for this drill yet. Know a good one?</p>}
    <button type="button" className={prominent ? 'primary-btn' : 'link-btn'} aria-expanded={open}
      onClick={() => { setOpen(value => !value); setSent(null); setError('') }}>Suggest a video</button>
    {open && <form className="stack" onSubmit={submit}>
      <div className="field"><label htmlFor="video-url">Link to a YouTube or Vimeo video</label>
        <input id="video-url" type="url" required maxLength={500} placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={e => setUrl(e.target.value)} /></div>
      {variation && variation.kind !== 'base' && <label className="checkbox"><input type="checkbox" checked={forVariation} onChange={e => setForVariation(e.target.checked)} /> It shows this variation: {variation.title}</label>}
      <div className="field"><label htmlFor="video-note">Why it's a good fit <span className="muted">(optional)</span></label>
        <textarea id="video-note" rows={2} maxLength={500} value={note} onChange={e => setNote(e.target.value)} /></div>
      <p className="muted hint">If it's approved, the video will be shown to everyone who uses {APP_NAME}. Only suggest a video that is public, or that you have the owner's permission to share. A site admin checks every suggestion first.</p>
      <button type="submit" className="primary-btn" disabled={busy}>{busy ? 'Sending…' : 'Send suggestion'}</button>
    </form>}
    {error && <p className="error" role="alert">{error}</p>}
    {sent && <p className="notice" role="status">Thanks: “{sent.title}”{sent.channel ? ` (${sent.channel})` : ''} is waiting for review. You can follow it in Settings, under Account.</p>}
  </section>
}

// Settings → Account: the coach's own suggestions and where each stands.
export function MyVideoSuggestions() {
  const [items, setItems] = useState(null)
  useEffect(() => {
    let live = true
    getMyVideoSuggestions().then(value => { if (live) setItems(value) }).catch(() => { if (live) setItems(false) })
    return () => { live = false }
  }, [])
  if (!items || !items.length) return items === false ? <p className="muted">Could not load your video suggestions.</p> : null
  return <div className="my-video-suggestions">
    <h4>Your video suggestions</h4>
    <ul>{items.map(s => <li key={s.id}>
      <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a>
      <span className="muted"> for {s.drill_title}{s.variation_title ? ` (${s.variation_title})` : ''}</span>
      <span className={`status-pill ${s.status === 'approved' ? '' : s.status === 'pending' ? 'muted-pill' : 'warn-pill'}`}>{SUGGESTION_STATUS[s.status]}</span>
      {s.status === 'rejected' && s.reject_reason && <small className="muted">{REJECT_REASONS[s.reject_reason]}{s.reject_note ? `: ${s.reject_note}` : ''}</small>}
    </li>)}</ul>
  </div>
}

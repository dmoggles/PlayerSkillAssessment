import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage, requestAccess } from '../api'

const EMPTY = { name: '', email: '', club: '', teams: '', message: '', website: '' }

// The landing page's call to action: a club asks for access, and a site admin replies with an invitation.
export default function RequestAccess() {
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState('')
  const [error, setError] = useState('')
  const set = key => event => setForm(previous => ({ ...previous, [key]: event.target.value }))

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { message } = await requestAccess({ ...form, teams: form.teams === '' ? null : Number(form.teams) })
      setDone(message)
      setForm(EMPTY)
    } catch (e) {
      setError(errorMessage(e, 'Could not send your request. Please try again.'))
    } finally { setBusy(false) }
  }

  if (done) return <p className="access-done" role="status">{done}</p>
  return <form className="access-form" onSubmit={submit}>
    <div className="access-grid">
      <label className="field">Your name<input required maxLength={120} autoComplete="name" value={form.name} onChange={set('name')} /></label>
      <label className="field">Email<input type="email" required maxLength={255} autoComplete="email" value={form.email} onChange={set('email')} /></label>
      <label className="field">Club<input required maxLength={120} autoComplete="organization" value={form.club} onChange={set('club')} /></label>
      <label className="field"><span>Number of teams <span className="optional">(optional)</span></span><input type="number" min={1} max={99} inputMode="numeric" value={form.teams} onChange={set('teams')} /></label>
    </div>
    <label className="field"><span>Anything we should know? <span className="optional">(optional)</span></span><textarea rows={3} maxLength={1000} value={form.message} onChange={set('message')} /></label>
    {/* Left empty by people; bots that fill every field are ignored. */}
    <label className="access-trap" aria-hidden="true">Website<input tabIndex={-1} autoComplete="off" value={form.website} onChange={set('website')} /></label>
    <p className="access-privacy">We'll use these details only to reply about access, and delete them once we have. See the <Link to="/privacy">privacy notice</Link>.</p>
    {error && <p className="access-error" role="alert">{error}</p>}
    <button className="button button-lime" disabled={busy}>{busy ? 'Sending…' : 'Request access'}</button>
  </form>
}

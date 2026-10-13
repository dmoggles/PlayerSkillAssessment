import { useState } from 'react'
import { deleteAccount, errorMessage } from './api'

// Deletes the signed-in coach's account. Teams keep their players and assessments; the coach's name comes off them.
export default function DeleteAccountForm({ confirmDiscard }) {
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (!confirmDiscard() || !window.confirm('Delete your account permanently? This cannot be undone.')) return
    setBusy(true)
    setMessage('')
    try {
      await deleteAccount(password)
      window.location.assign('/')
    } catch (error) {
      setMessage(errorMessage(error, 'Could not delete your account. Please try again.'))
      setBusy(false)
    }
  }

  return <div className="delete-account">
    <button type="button" className="link-btn" aria-expanded={open} onClick={() => { setOpen(value => !value); setMessage('') }}>Delete account…</button>
    {open && <form className="stack" onSubmit={submit}>
      <p className="muted">Your teams keep their players, assessments and plans, but your email is taken off them. If you're a team's only owner, make another coach an owner or delete the team first.</p>
      <label className="field">Password<input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>
      <button className="danger-btn" disabled={busy}>{busy ? 'Deleting…' : 'Delete my account'}</button>
    </form>}
    {message && <p className="notice" role="status">{message}</p>}
  </div>
}

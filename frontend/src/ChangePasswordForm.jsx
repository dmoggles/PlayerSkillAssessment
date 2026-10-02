import { useState } from 'react'
import { changePassword, errorMessage } from './api'

export default function ChangePasswordForm() {
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (next !== confirm) { setMessage('New passwords do not match.'); return }
    setBusy(true)
    setMessage('')
    try {
      const result = await changePassword(current, next)
      setCurrent(''); setNext(''); setConfirm('')
      setOpen(false)
      setMessage(result.message)
    } catch (error) {
      setMessage(errorMessage(error, 'Could not change password. Please try again.'))
    } finally { setBusy(false) }
  }

  return <div className="change-password">
    <button type="button" aria-expanded={open} onClick={() => { setOpen(value => !value); setMessage('') }}>Change password</button>
    {open && <form className="stack" onSubmit={submit}>
      <label className="field">Current password<input type="password" autoComplete="current-password" required value={current} onChange={event => setCurrent(event.target.value)} /></label>
      <label className="field">New password<input type="password" autoComplete="new-password" minLength={12} maxLength={200} required value={next} onChange={event => setNext(event.target.value)} /></label>
      <label className="field">Confirm new password<input type="password" autoComplete="new-password" minLength={12} maxLength={200} required value={confirm} onChange={event => setConfirm(event.target.value)} /></label>
      <button disabled={busy}>Save password</button>
    </form>}
    {message && <p className="notice" role="status">{message}</p>}
  </div>
}

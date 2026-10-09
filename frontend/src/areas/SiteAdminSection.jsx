import { useEffect, useState } from 'react'
import { cancelSiteInvite, errorMessage, getSiteInvites, sendSiteInvite } from '../api'
import { Section } from './DashboardParts'

const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

// Site admins invite each new club's first coach; that coach then creates their own team and invites the rest.
export default function SiteAdminSection({ onMessage }) {
  const [invites, setInvites] = useState(null)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { getSiteInvites().then(setInvites).catch(e => onMessage(errorMessage(e, 'Could not load invitations.'))) }, [onMessage])

  const send = async event => {
    event.preventDefault()
    setBusy(true)
    try {
      const sent = await sendSiteInvite(email)
      setInvites(previous => [sent, ...(previous ?? []).filter(i => i.email !== sent.email)])
      setEmail('')
      onMessage(sent.message)
    } catch (e) { onMessage(errorMessage(e, 'Could not send the invitation.')) } finally { setBusy(false) }
  }
  const cancel = async invite => {
    try {
      onMessage((await cancelSiteInvite(invite.id)).message)
      setInvites(previous => previous.filter(i => i.id !== invite.id))
    } catch (e) { onMessage(errorMessage(e, 'Could not cancel the invitation.')) }
  }

  return <Section title="Site admin" description="Sign-up is by invitation. Invite a new club's first coach here; they create their team and invite the rest.">
    <form className="inline-row" onSubmit={send}>
      <input type="email" aria-label="New coach's email" placeholder="New coach's email" required value={email} onChange={e => setEmail(e.target.value)} />
      <button disabled={busy}>{busy ? 'Sending…' : 'Invite new club'}</button>
    </form>
    {invites?.length > 0 && <ul className="site-invites">
      {invites.map(invite => <li key={invite.id} className="settings-item">
        <span><strong>{invite.email}</strong><small>Waiting for sign-up · link expires {day(invite.expires_at)}</small></span>
        <button type="button" onClick={() => cancel(invite)}>Cancel</button>
      </li>)}
    </ul>}
    {invites?.length === 0 && <p className="muted">No invitations waiting.</p>}
  </Section>
}

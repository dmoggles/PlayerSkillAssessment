import { useEffect, useState } from 'react'
import { cancelSiteInvite, errorMessage, getSiteInvites, sendSiteInvite } from '../api'
import { Section } from './DashboardParts'
import AccessRequestsList from './AccessRequestsList'
import InviteLink from './InviteLink'

const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

// Site admins invite each new club's first coach; that coach then creates their own team and invites the rest.
export default function SiteAdminSection({ onMessage }) {
  const [invites, setInvites] = useState(null)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [newInvite, setNewInvite] = useState(null)
  useEffect(() => { getSiteInvites().then(setInvites).catch(e => onMessage(errorMessage(e, 'Could not load invitations.'))) }, [onMessage])

  const send = async event => {
    event.preventDefault()
    setBusy(true)
    try {
      const sent = await sendSiteInvite(email)
      setInvites(previous => [sent, ...(previous ?? []).filter(i => i.email !== sent.email)])
      setEmail('')
      setNewInvite(sent)
    } catch (e) { onMessage(errorMessage(e, 'Could not send the invitation.')) } finally { setBusy(false) }
  }
  const cancel = async invite => {
    try {
      onMessage((await cancelSiteInvite(invite.id)).message)
      setInvites(previous => previous.filter(i => i.id !== invite.id))
    } catch (e) { onMessage(errorMessage(e, 'Could not cancel the invitation.')) }
  }

  return <Section title="Site admin" description="Sign-up is by invitation. Invite a new club's first coach here; they create their team and invite the rest.">
    <AccessRequestsList onMessage={onMessage} onInvited={sent => setInvites(previous => [sent, ...(previous ?? []).filter(i => i.email !== sent.email)])} />
    <form className="inline-row" onSubmit={send}>
      <input type="email" aria-label="New coach's email" placeholder="New coach's email" required value={email} onChange={e => setEmail(e.target.value)} />
      <button className="primary-btn" disabled={busy}>{busy ? 'Sending…' : 'Invite new club'}</button>
    </form>
    {newInvite && <InviteLink invite={newInvite} days={14} onDone={() => setNewInvite(null)} />}
    {invites?.length > 0 && <ul className="site-invites">
      {invites.map(invite => <li key={invite.id} className="settings-item">
        <span><strong>{invite.email}</strong><small>Waiting for sign-up · link expires {day(invite.expires_at)}</small></span>
        <button className="danger-btn" type="button" onClick={() => cancel(invite)}>Cancel</button>
      </li>)}
    </ul>}
    {invites?.length === 0 && <p className="muted">No invitations waiting.</p>}
  </Section>
}

import { useEffect, useState } from 'react'
import { declineAccessRequest, errorMessage, getAccessRequests, inviteFromAccessRequest } from '../api'
import InviteLink from './InviteLink'

const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

// Site admin: clubs that asked for access from the public site. Inviting sends the usual site invitation.
export default function AccessRequestsList({ onMessage, onInvited }) {
  const [requests, setRequests] = useState(null)
  const [invite, setInvite] = useState(null)
  useEffect(() => { getAccessRequests().then(setRequests).catch(e => onMessage(errorMessage(e, 'Could not load access requests.'))) }, [onMessage])
  const remove = request => setRequests(previous => previous.filter(r => r.id !== request.id))
  const act = async (request, call) => {
    try {
      const result = await call(request.id)
      remove(request)
      if (result.link) { setInvite(result); onInvited(result) } else onMessage(result.message)
    } catch (e) { onMessage(errorMessage(e, 'Could not update the request.')) }
  }

  if (!requests) return null
  return <div className="access-requests">
    <h3>Access requests{requests.length ? ` (${requests.length})` : ''}</h3>
    {invite && <InviteLink invite={invite} days={14} onDone={() => setInvite(null)} />}
    {!requests.length ? <p className="muted">No requests waiting.</p> : <ul className="site-invites">
      {requests.map(request => <li key={request.id} className="settings-item">
        <span><strong>{request.club}</strong> · {request.name} · {request.email}
          <small>{day(request.created_at)}{request.teams ? ` · ${request.teams} ${request.teams === 1 ? 'team' : 'teams'}` : ''}{request.has_account ? ' · already has an account' : ''}</small>
          {request.message && <small className="access-message">{request.message}</small>}</span>
        <span className="item-actions">
          {!request.has_account && <button type="button" onClick={() => act(request, inviteFromAccessRequest)}>Invite</button>}
          <button type="button" onClick={() => act(request, declineAccessRequest)}>Decline</button>
        </span>
      </li>)}
    </ul>}
  </div>
}

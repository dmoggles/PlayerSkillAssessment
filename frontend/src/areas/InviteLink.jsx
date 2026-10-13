import { useState } from 'react'

// A new invitation's link, to send by WhatsApp or text as well as (or instead of) email. Links are stored only as
// hashes, so this is the one time it can be shown; inviting the same address again makes a fresh one.
export default function InviteLink({ invite, days, onDone }) {
  const [copied, setCopied] = useState(false)
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'
  const copy = event => {
    const field = event.currentTarget.parentElement.querySelector('input')
    navigator.clipboard?.writeText(invite.link).then(() => setCopied(true)).catch(() => field?.select())
  }
  const share = () => navigator.share({ title: 'Your invitation', text: `Your invitation for ${invite.email}:`, url: invite.link }).catch(() => {})
  return <div className="invite-link" role="status">
    <p><strong>{invite.emailed ? `Invitation emailed to ${invite.email}.` : `The email to ${invite.email} couldn't be sent.`}</strong> {invite.emailed ? 'You can also send the link yourself:' : 'The invitation is ready: send this link yourself.'}</p>
    <div className="issued-link">
      <input readOnly aria-label={`Invitation link for ${invite.email}`} value={invite.link} onFocus={e => e.target.select()} />
      <button type="button" onClick={copy}>{copied ? 'Copied' : 'Copy link'}</button>
      {canShare && <button type="button" onClick={share}>Share…</button>}
    </div>
    <p className="muted">Only {invite.email} can use it, once, within {days} days. It won't be shown again; invite them again for a new link.</p>
    <button type="button" className="link-btn" onClick={onDone}>Done</button>
  </div>
}

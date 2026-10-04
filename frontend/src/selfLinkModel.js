// Status labels and summaries for the squad self-assessment board.
export const SELF_LINK_STATUS = {
  not_sent: { label: 'Not sent', pill: 'muted-pill' },
  sent: { label: 'Sent', pill: 'info-pill' },
  opened: { label: 'Opened', pill: 'info-pill' },
  submitted: { label: 'Submitted', pill: '' },
  expired: { label: 'Expired', pill: 'warn-pill' },
}

export const needsLink = row => row.status === 'not_sent' || row.status === 'expired'
export const hasLiveLink = row => row.status === 'sent' || row.status === 'opened'

const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

export function statusDetail(row) {
  const expires = row.expires_at ? `expires ${day(row.expires_at)}` : null
  if (row.status === 'submitted') return row.submitted_at ? `Submitted ${day(row.submitted_at)}` : ''
  if (row.status === 'expired') return `Expired ${day(row.expires_at)}`
  if (row.status === 'opened') return [row.opened_at && `Opened ${day(row.opened_at)}`, expires].filter(Boolean).join(' · ')
  if (row.status === 'sent') return [row.issued_at && `Sent ${day(row.issued_at)}`, expires].filter(Boolean).join(' · ')
  return ''
}

export function statusSummary(rows) {
  const count = status => rows.filter(row => row.status === status).length
  const parts = ['opened', 'sent', 'expired', 'not_sent'].filter(count).map(status => `${count(status)} ${SELF_LINK_STATUS[status].label.toLowerCase()}`)
  return [`${count('submitted')} of ${rows.length} submitted`, ...parts].join(' · ')
}

export const copyAllText = links => links.map(link => `${link.player_name}: ${link.url}`).join('\n')

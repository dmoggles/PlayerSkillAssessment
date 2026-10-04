import { useCallback, useEffect, useState } from 'react'
import { errorMessage, getSelfLinkBoard, issueSelfLinks, revokeSelfLink } from './api'
import { SELF_LINK_STATUS, copyAllText, hasLiveLink, needsLink, statusDetail, statusSummary } from './selfLinkModel'

// Squad-wide link issuing and status for one period. Raw links are only returned when issued,
// so newly issued links stay listed here until the coach dismisses them.
export default function SelfAssessmentBoard({ teamId, period, rosterKey, onMessage }) {
  const [rows, setRows] = useState([])
  const [issued, setIssued] = useState([])
  const [busy, setBusy] = useState(false)
  const reload = useCallback(() => getSelfLinkBoard(teamId, period.id).then(setRows).catch(e => onMessage(errorMessage(e))), [teamId, period.id, onMessage])
  useEffect(() => { reload() }, [reload, rosterKey])

  const pending = rows.filter(needsLink).length

  async function issue(playerIds) {
    setBusy(true)
    try {
      const { links } = await issueSelfLinks(teamId, period.id, playerIds)
      setIssued(previous => [...links, ...previous.filter(old => !links.some(link => link.player_id === old.player_id))])
      onMessage(links.length ? `Created ${links.length} ${links.length === 1 ? 'link' : 'links'}. Copy them now; they will not be shown again.` : 'Every active player already has a link or has submitted.')
      await reload()
    } catch (e) { onMessage(errorMessage(e)) } finally { setBusy(false) }
  }
  async function revoke(row) {
    if (!window.confirm(`Revoke ${row.player_name}'s link? It will stop working immediately.`)) return
    try {
      await revokeSelfLink(teamId, row.player_id, period.id)
      setIssued(previous => previous.filter(link => link.player_id !== row.player_id))
      await reload()
    } catch (e) { onMessage(errorMessage(e)) }
  }

  return <div className="self-board">
    {!period.is_active && <p className="muted">Links can only be issued for the active period. Showing status for {period.label}.</p>}
    <div className="self-board-toolbar"><span className="muted">{rows.length ? statusSummary(rows) : 'No active players yet.'}</span>{period.is_active && <button type="button" onClick={() => issue()} disabled={busy || pending === 0}>{pending ? `Create links for ${pending} ${pending === 1 ? 'player' : 'players'}` : 'All players have links'}</button>}</div>
    {issued.length > 0 && <div className="issued-links">
      <div className="issued-links-heading"><strong>New links: copy them now, they will not be shown again</strong><div className="item-actions"><button type="button" onClick={() => navigator.clipboard.writeText(copyAllText(issued)).then(() => onMessage('All new links copied.'))}>Copy all</button><button type="button" onClick={() => setIssued([])}>Done</button></div></div>
      {issued.map(link => <div className="issued-link" key={link.player_id}><span>{link.player_name}</span><input readOnly aria-label={`${link.player_name} link`} value={link.url} onFocus={e => e.target.select()} /><button type="button" onClick={() => navigator.clipboard.writeText(link.url)}>Copy</button></div>)}
    </div>}
    <div className="settings-list">{rows.map(row => <div className="settings-item" key={row.player_id}>
      <span>{row.player_name} <span className={`status-pill ${SELF_LINK_STATUS[row.status].pill}`}>{SELF_LINK_STATUS[row.status].label}</span>{statusDetail(row) && <small>{statusDetail(row)}</small>}</span>
      <div className="item-actions">{period.is_active && row.status !== 'submitted' && <button type="button" disabled={busy} onClick={() => issue([row.player_id])}>{row.status === 'not_sent' ? 'Create link' : 'New link'}</button>}{hasLiveLink(row) && <button type="button" onClick={() => revoke(row)}>Revoke</button>}</div>
    </div>)}</div>
  </div>
}

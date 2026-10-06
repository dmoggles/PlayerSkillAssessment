import { useEffect, useState } from 'react'
import { errorMessage, extendReportShare, getPlayerReport, revokeReportShare, savePlayerReport, shareReport } from './api'
import { DrillDialog } from './DrillLibrary'
import PlayerReport from './PlayerReport'
import { buildReport, shareSummary } from './reportModel'

// Coach view of the player report: edit the message, preview, print or save as PDF.
export default function ReportPanel({ matrix, teamId, playerId, periodId, readOnly, onMessage, onDirtyChange }) {
  const [report, setReport] = useState(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [link, setLink] = useState('')
  const [extendBy, setExtendBy] = useState('2')
  const [openDrill, setOpenDrill] = useState(null)

  useEffect(() => {
    let live = true
    getPlayerReport(teamId, playerId, periodId).then(value => { if (live) { setReport(value); setDraft(value.message ?? '') } }).catch(e => onMessage(errorMessage(e)))
    return () => { live = false }
  }, [teamId, playerId, periodId, onMessage])

  // An unsaved message counts as unsaved changes, so leaving prompts before it is lost.
  const changed = report !== null && draft.trim() !== (report.message ?? '')
  useEffect(() => { onDirtyChange(changed) }, [changed, onDirtyChange])
  useEffect(() => () => onDirtyChange(false), [onDirtyChange])

  if (!report) return <p className="muted" role="status">Loading report…</p>
  const view = buildReport(matrix, report)

  const reload = () => getPlayerReport(teamId, playerId, periodId).then(setReport)
  async function createLink() {
    if (report.share && !report.share.expired && !window.confirm('Create a new link? The current link will stop working.')) return
    try { const value = await shareReport(teamId, playerId, periodId); setLink(value.url); onMessage('Link created. Copy it now; it will not be shown again.'); await reload() } catch (e) { onMessage(errorMessage(e)) }
  }
  async function revokeLink() {
    if (!window.confirm('Revoke this link? Anyone who has it will no longer be able to open the report.')) return
    try { await revokeReportShare(teamId, playerId, periodId); setLink(''); onMessage('Link revoked.'); await reload() } catch (e) { onMessage(errorMessage(e)) }
  }

  async function extendLink() {
    try { await extendReportShare(teamId, playerId, periodId, Number(extendBy)); onMessage(`Link extended by ${extendBy} week${extendBy === '1' ? '' : 's'}; it is the same link.`); await reload() } catch (e) { onMessage(errorMessage(e)) }
  }
  async function save() {
    setSaving(true)
    try { const value = await savePlayerReport(teamId, playerId, periodId, draft); setReport(value); setDraft(value.message ?? ''); onMessage('Report message saved.') } catch (e) { onMessage(errorMessage(e)) } finally { setSaving(false) }
  }

  return <div className="report-panel">
    <div className="report-controls">
      {!readOnly && <label className="field">Message to the player <small>Shown at the top of the report</small><textarea rows={3} maxLength={1000} value={draft} onChange={e => setDraft(e.target.value)} placeholder="A few words of encouragement or context for this period" /></label>}
      <div className="inline-row">{!readOnly && <button type="button" disabled={!changed || saving} onClick={save}>{saving ? 'Saving…' : 'Save message'}</button>}<button type="button" onClick={() => window.print()}>Print or save as PDF</button></div>
      {view.assessed && !view.priorities.length && <p className="warning">Priorities for this period are not confirmed yet, so the report has no focus areas. Confirm them in Development.</p>}
      {changed && <p className="muted">The preview shows the saved message. Save to update it.</p>}
      <div className="report-share">
        <h3>Share link</h3>
        <p className="muted">{shareSummary(report.share)}</p>
        <div className="inline-row"><button type="button" onClick={createLink}>{report.share ? 'New link' : 'Create link'}</button>{report.share && !report.share.expired && <button type="button" onClick={revokeLink}>Revoke</button>}</div>
        {report.share && <div className="inline-row report-extend"><label>Extend the same link by <select aria-label="Extend by" value={extendBy} onChange={e => setExtendBy(e.target.value)}>{['1', '2', '4'].map(w => <option key={w} value={w}>{w} week{w === '1' ? '' : 's'}</option>)}</select></label><button type="button" onClick={extendLink}>Extend</button></div>}
        {link && <div className="field link-field"><label>Copy this link now; it will not be shown again</label><input readOnly value={link} onFocus={e => e.target.select()} /><button type="button" onClick={() => navigator.clipboard.writeText(link).then(() => onMessage('Link copied.'))}>Copy link</button></div>}
      </div>
    </div>
    <PlayerReport report={view} onOpenDrill={(slug, variationId) => setOpenDrill({ slug, variationId })} />
    {openDrill && <DrillDialog drill={openDrill} onMessage={onMessage} onClose={() => setOpenDrill(null)} />}
  </div>
}

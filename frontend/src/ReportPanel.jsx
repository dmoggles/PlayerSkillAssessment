import { useEffect, useState } from 'react'
import { errorMessage, getPlayerReport, savePlayerReport } from './api'
import PlayerReport from './PlayerReport'
import { buildReport } from './reportModel'

// Coach view of the player report: edit the message, preview, print or save as PDF.
export default function ReportPanel({ matrix, teamId, playerId, periodId, readOnly, onMessage, onDirtyChange }) {
  const [report, setReport] = useState(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

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
    </div>
    <PlayerReport report={view} />
  </div>
}

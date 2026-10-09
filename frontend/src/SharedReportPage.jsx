import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage, getSharedReport, getSharedReportDrill } from './api'
import { DrillDialog } from './DrillLibrary'
import PlayerReport from './PlayerReport'
import { MadeWith } from './brand'
import { buildReport } from './reportModel'

// Public, read-only report opened from a coach's share link.
export default function SharedReportPage() {
  const { token } = useParams()
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [openDrill, setOpenDrill] = useState(null)
  const [drillError, setDrillError] = useState('')
  // The report's link also opens the drills in its plan, and only those.
  const loadDrill = useCallback(slug => getSharedReportDrill(token, slug), [token])

  useEffect(() => {
    getSharedReport(token)
      .then(value => setReport(buildReport(value.matrix, value)))
      .catch(e => setError(errorMessage(e, 'This link is unavailable.')))
  }, [token])

  return <div className="page public-page shared-report-page">
    {error ? <section className="public-card"><h1>Player report</h1><p role="alert">{error}</p></section>
      : !report ? <p className="muted" role="status">Loading report…</p>
        : <><div className="shared-report-actions"><button type="button" onClick={() => window.print()}>Print or save as PDF</button></div>
          <PlayerReport report={report} onOpenDrill={(slug, variationId) => { setDrillError(''); setOpenDrill({ slug, variationId }) }} />
          {drillError && <p className="error" role="alert">{drillError}</p>}
          {openDrill && <DrillDialog drill={openDrill} loadDrill={loadDrill} onMessage={setDrillError} onClose={() => setOpenDrill(null)} />}</>}
    <MadeWith />
  </div>
}

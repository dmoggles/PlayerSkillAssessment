import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage, getSharedReport, getSkillMatrix } from './api'
import PlayerReport from './PlayerReport'
import { buildReport } from './reportModel'

// Public, read-only report opened from a coach's share link.
export default function SharedReportPage() {
  const { token } = useParams()
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getSharedReport(token), getSkillMatrix()])
      .then(([value, matrix]) => setReport(buildReport(matrix, value)))
      .catch(e => setError(errorMessage(e, 'This link is unavailable.')))
  }, [token])

  return <div className="page public-page shared-report-page">
    {error ? <section className="public-card"><h1>Player report</h1><p role="alert">{error}</p></section>
      : !report ? <p className="muted" role="status">Loading report…</p>
        : <><div className="shared-report-actions"><button type="button" onClick={() => window.print()}>Print or save as PDF</button></div><PlayerReport report={report} /></>}
  </div>
}

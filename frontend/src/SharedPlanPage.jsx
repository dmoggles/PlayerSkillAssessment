import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage, getSharedPlan, getSharedPlanDrill } from './api'
import { PlanCards } from './DevelopmentPlan'
import { DrillDialog } from './DrillLibrary'

const longDay = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })

// Public, read-only development plan opened from a coach's link. Its drills open through the same link.
export default function SharedPlanPage() {
  const { token } = useParams()
  const [shared, setShared] = useState(null)
  const [error, setError] = useState('')
  const [openDrill, setOpenDrill] = useState(null)
  const [drillError, setDrillError] = useState('')
  useEffect(() => {
    getSharedPlan(token).then(setShared).catch(e => setError(errorMessage(e, 'This link is unavailable.')))
  }, [token])
  const loadDrill = useCallback(slug => getSharedPlanDrill(token, slug), [token])

  if (error) return <div className="page public-page"><section className="public-card"><h1>Development plan</h1><p role="alert">{error}</p></section></div>
  if (!shared) return <div className="page public-page"><p className="muted" role="status">Loading plan…</p></div>
  return <div className="page public-page shared-plan-page">
    <p className="eyebrow">{shared.team} · {shared.period}</p>
    <h1>{shared.player}'s {shared.plan.weeks}-week plan</h1>
    <p className="muted">For each priority: a drill for training and one to practise at home. Tap a week to see that version of the drill. This link works until {longDay(shared.expires_at)}.</p>
    <div className="shared-report-actions"><button type="button" onClick={() => window.print()}>Print or save as PDF</button></div>
    <PlanCards plan={shared.plan} onOpenDrill={(slug, variationId) => { setDrillError(''); setOpenDrill({ slug, variationId }) }} />
    {drillError && <p className="error" role="alert">{drillError}</p>}
    {openDrill && <DrillDialog drill={openDrill} loadDrill={loadDrill} onMessage={setDrillError} onClose={() => setOpenDrill(null)} />}
  </div>
}

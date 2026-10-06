import { useEffect, useState } from 'react'
import { errorMessage, generatePlan, getSavedPlan } from './api'
import { planByPriority, planIsStale, weekRuns } from './planModel'

const SLOT_LABELS = { club: 'At training', home: 'At home' }

// The player's saved 4-week plan of club and home drills for the priorities above. Generating saves it; it also
// appears in the player report, so the report's share link is how the player or a parent sees it.
// skills are the saved priorities in rank order; unsaved says the coach has changed them without saving.
export default function DevelopmentPlan({ teamId, playerId, periodId, skills, unsaved = false, onOpenDrill, readOnly = false }) {
  const [saved, setSaved] = useState(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    getSavedPlan(teamId, playerId, periodId).then(value => { if (live) setSaved(value) }).catch(e => { if (live) { setSaved({ plan: null }); setError(errorMessage(e)) } })
    return () => { live = false }
  }, [teamId, playerId, periodId])
  const generate = async () => {
    if (saved?.plan && !window.confirm('Replace the saved plan? If the player report is shared, its link will show the new plan.')) return
    setBusy(true); setError('')
    try { setSaved(await generatePlan(teamId, playerId, periodId)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  if (saved === undefined) return <section className="development-plan"><p className="muted" role="status">Loading plan…</p></section>
  const plan = saved.plan
  return <section className="development-plan" aria-labelledby="plan-title">
    <div className="development-plan-head">
      <div><h3 id="plan-title">4-week plan</h3><p className="muted hint">{plan
        ? `Saved ${new Date(saved.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}. It is part of the player report; share the report to send it to the player or a parent.`
        : 'Club and home drills for the priorities above, stepping up after two weeks. Generating saves it to the player report.'}</p></div>
      {!readOnly && <button type="button" onClick={generate} disabled={busy || unsaved || !skills.length}>{busy ? 'Generating…' : plan ? 'Regenerate' : 'Generate plan'}</button>}
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {!readOnly && (unsaved || !skills.length) && <p className="muted hint">{plan ? 'Save the priorities above to regenerate the plan from them.' : 'Save the priorities above to generate a plan from them.'}</p>}
    {planIsStale(saved, skills) && <p className="warning">The saved priorities have changed since this plan was made. Regenerate to update it.</p>}
    {plan && <PlanCards plan={plan} onOpenDrill={onOpenDrill} />}
  </section>
}

export function PlanCards({ plan, onOpenDrill }) {
  return <div className="plan-cards">{planByPriority(plan).map(p => <article key={p.rank} className="plan-card">
    <h4><span className="plan-rank">{p.rank}</span>{p.label}</h4>
    {['club', 'home'].map(slot => p[slot] && <PlanSlot key={slot} slot={p[slot]} onOpenDrill={onOpenDrill} />)}
    {p.gaps.map(g => <p key={g.slot} className="plan-gap"><strong>{SLOT_LABELS[g.slot]}:</strong> {g.reason}</p>)}
  </article>)}</div>
}

function PlanSlot({ slot, onOpenDrill }) {
  return <div className="plan-slot">
    <p className="plan-slot-head"><span className="status-pill muted-pill">{SLOT_LABELS[slot.slot]}</span>
      <button type="button" className="link-btn" onClick={() => onOpenDrill(slot.drill, slot.weeks[0].id)}>{slot.title}</button>
      <span className="muted"> · {slot.duration[1]} min</span></p>
    <ol className="plan-weeks">{weekRuns(slot.weeks).map(run => <li key={run.from}>
      <button type="button" onClick={() => onOpenDrill(slot.drill, run.variation.id)}><span className="muted">{run.label}</span> {run.variation.title}</button>
    </li>)}</ol>
    <ul className="plan-reasons">{slot.reasons.map(r => <li key={r}>{r}</li>)}</ul>
  </div>
}

import { useState } from 'react'
import { errorMessage, getDevelopmentPlan } from './api'
import { planByPriority, weekRuns } from './planModel'

const SLOT_LABELS = { club: 'At training', home: 'At home' }

// A 4-week plan of club and home drills for the priorities above, generated on request and not saved.
export default function DevelopmentPlan({ teamId, playerId, periodId, skills, onOpenDrill }) {
  const [state, setState] = useState({ status: 'idle', plan: null, key: '', error: '' })
  const key = skills.join(',')
  const generate = async () => {
    setState(s => ({ ...s, status: 'loading', error: '' }))
    try { setState({ status: 'ready', plan: await getDevelopmentPlan(teamId, playerId, periodId, skills), key, error: '' }) }
    catch (e) { setState(s => ({ ...s, status: 'idle', error: errorMessage(e) })) }
  }
  const { plan } = state
  return <section className="development-plan" aria-labelledby="plan-title">
    <div className="development-plan-head">
      <div><h3 id="plan-title">4-week plan</h3><p className="muted hint">Club and home drills for the priorities above, stepping up after two weeks. Generated each time; not saved.</p></div>
      <button type="button" onClick={generate} disabled={state.status === 'loading' || !skills.length}>{state.status === 'loading' ? 'Generating…' : plan ? 'Regenerate' : 'Generate plan'}</button>
    </div>
    {state.error && <p className="error" role="alert">{state.error}</p>}
    {plan && state.key !== key && <p className="warning">The priorities have changed since this plan was made. Regenerate to update it.</p>}
    {plan && <div className="plan-cards">{planByPriority(plan).map(p => <article key={p.rank} className="plan-card">
      <h4><span className="plan-rank">{p.rank}</span>{p.label}</h4>
      {['club', 'home'].map(slot => p[slot] && <PlanSlot key={slot} slot={p[slot]} onOpenDrill={onOpenDrill} />)}
      {p.gaps.map(g => <p key={g.slot} className="plan-gap"><strong>{SLOT_LABELS[g.slot]}:</strong> {g.reason}</p>)}
    </article>)}</div>}
  </section>
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

import { useEffect, useState } from 'react'
import { errorMessage, getDevelopmentPlan, getPlanShare, revokePlanShare, sharePlan } from './api'
import { planByPriority, planShareSummary, shareIsStale, weekRuns } from './planModel'

const SLOT_LABELS = { club: 'At training', home: 'At home' }

// A 4-week plan of club and home drills for the priorities above, generated on request. Sharing freezes a copy
// behind a link that needs no login.
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
      <div><h3 id="plan-title">4-week plan</h3><p className="muted hint">Club and home drills for the priorities above, stepping up after two weeks. Generated each time; sharing saves a copy.</p></div>
      <button type="button" onClick={generate} disabled={state.status === 'loading' || !skills.length}>{state.status === 'loading' ? 'Generating…' : plan ? 'Regenerate' : 'Generate plan'}</button>
    </div>
    {state.error && <p className="error" role="alert">{state.error}</p>}
    {plan && state.key !== key && <p className="warning">The priorities have changed since this plan was made. Regenerate to update it.</p>}
    {plan && <PlanCards plan={plan} onOpenDrill={onOpenDrill} />}
    <PlanShare teamId={teamId} playerId={playerId} periodId={periodId} skills={skills} />
  </section>
}

function PlanShare({ teamId, playerId, periodId, skills }) {
  const [share, setShare] = useState(undefined)
  const [link, setLink] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => {
    let live = true
    getPlanShare(teamId, playerId, periodId).then(value => { if (live) setShare(value.share) }).catch(() => { if (live) setShare(null) })
    return () => { live = false }
  }, [teamId, playerId, periodId])
  if (share === undefined) return null
  const create = async () => {
    if (share && !share.expired && !window.confirm('Create a new link? The current link will stop working.')) return
    try { const value = await sharePlan(teamId, playerId, periodId, skills); setShare(value.share); setLink(value.url); setMessage('Link created. Copy it now; it will not be shown again.') }
    catch (e) { setMessage(errorMessage(e)) }
  }
  const revoke = async () => {
    if (!window.confirm('Revoke this link? Anyone who has it will no longer be able to open the plan.')) return
    try { await revokePlanShare(teamId, playerId, periodId); setShare(null); setLink(''); setMessage('Link revoked.') }
    catch (e) { setMessage(errorMessage(e)) }
  }
  const copy = () => navigator.clipboard?.writeText(link).then(() => setMessage('Link copied.'), () => setMessage('Copy the link from the box.'))
  return <div className="plan-share">
    <h4>Share with the player</h4>
    <p className="muted">{planShareSummary(share)}</p>
    {shareIsStale(share, skills) && <p className="warning">The shared plan was made for different priorities. Create a new link to share the current ones.</p>}
    <div className="inline-row">
      <button type="button" onClick={create} disabled={!skills.length}>{share && !share.expired ? 'New link' : 'Create link'}</button>
      {share && !share.expired && <button type="button" onClick={revoke}>Revoke</button>}
    </div>
    {link && <div className="plan-share-link"><input readOnly aria-label="Plan link" value={link} onFocus={e => e.target.select()} /><button type="button" onClick={copy}>Copy</button></div>}
    {message && <p role="status" className="muted">{message}</p>}
  </div>
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

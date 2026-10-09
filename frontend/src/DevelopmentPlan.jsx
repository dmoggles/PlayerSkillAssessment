import { useEffect, useMemo, useState } from 'react'
import { editPlanSlot, errorMessage, generatePlan, getDrill, getDrills, getPlanAlternatives, getSavedPlan } from './api'
import { planByPriority, planIsStale, weekRuns } from './planModel'

const SLOT_LABELS = { club: 'At training', home: 'At home' }

// The player's saved 4-week plan of club and home drills for the priorities above. Generating saves it; it also
// appears in the player report, so the report's share link is how the player or a parent sees it.
// skills are the saved priorities in rank order; unsaved says the coach has changed them without saving.
export default function DevelopmentPlan({ teamId, playerId, periodId, skills, unsaved = false, onOpenDrill, onSaved = () => {}, readOnly = false }) {
  const [saved, setSaved] = useState(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    getSavedPlan(teamId, playerId, periodId).then(value => { if (live) setSaved(value) }).catch(e => { if (live) { setSaved({ plan: null }); setError(errorMessage(e)) } })
    return () => { live = false }
  }, [teamId, playerId, periodId])
  const generate = async () => {
    if (saved?.plan && !window.confirm('Regenerate the plan? Drills you chose yourself are kept; the rest may change. If the player report is shared, its link shows the new plan.')) return
    setBusy(true); setError('')
    try { setSaved(await generatePlan(teamId, playerId, periodId)); onSaved() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const editor = useMemo(() => ({
    edit: async (skillId, slot, change) => { const value = await editPlanSlot(teamId, playerId, periodId, skillId, slot, change); setSaved(value); onSaved() },
    alternatives: (skillId, slot) => getPlanAlternatives(teamId, playerId, periodId, skillId, slot),
  }), [teamId, playerId, periodId, onSaved])
  if (saved === undefined) return <section className="development-plan"><p className="muted" role="status">Loading plan…</p></section>
  const plan = saved.plan
  return <section className="development-plan" aria-labelledby="plan-title">
    <div className="development-plan-head">
      <div><h3 id="plan-title">4-week plan</h3><p className="muted hint">{plan
        ? `Saved ${new Date(saved.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}. The player report shows its home drills; share the report to send them to the player or a parent.`
        : 'Club and home drills for the priorities above, stepping up after two weeks. Generating saves it to the player report.'}</p></div>
      {!readOnly && <button type="button" onClick={generate} disabled={busy || unsaved || !skills.length}>{busy ? 'Generating…' : plan ? 'Regenerate' : 'Generate plan'}</button>}
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {!readOnly && (unsaved || !skills.length) && <p className="muted hint">{plan ? 'Save the priorities above to regenerate the plan from them.' : 'Save the priorities above to generate a plan from them.'}</p>}
    {planIsStale(saved, skills) && <p className="warning">The saved priorities have changed since this plan was made. Regenerate to update it.</p>}
    {plan && <PlanCards plan={plan} onOpenDrill={onOpenDrill} editor={readOnly ? null : editor} />}
  </section>
}

// editor (coach view only): { edit(skillId, slot, change), alternatives(skillId, slot) } to override slots.
export function PlanCards({ plan, onOpenDrill, editor = null }) {
  return <div className="plan-cards">{planByPriority(plan).map(p => <article key={p.rank} className="plan-card">
    <h4><span className="plan-rank">{p.rank}</span>{p.label}</h4>
    {['club', 'home'].map(slot => p[slot] && <PlanSlot key={slot} slot={p[slot]} onOpenDrill={onOpenDrill} editor={editor} />)}
    {p.gaps.map(g => <div key={g.slot} className="plan-gap"><span><strong>{SLOT_LABELS[g.slot]}:</strong> {g.reason}</span>
      {editor && g.reason === 'Removed by the coach.' && <button type="button" className="link-btn" onClick={() => editor.edit(g.skill_id, g.slot, { action: 'reset' })}>Restore</button>}
    </div>)}
  </article>)}</div>
}

function PlanSlot({ slot, onOpenDrill, editor }) {
  const [editing, setEditing] = useState(false)
  return <div className="plan-slot">
    <p className="plan-slot-head"><span className="status-pill muted-pill">{SLOT_LABELS[slot.slot]}</span>
      <button type="button" className="link-btn" onClick={() => onOpenDrill(slot.drill, slot.weeks[0].id)}>{slot.title}</button>
      <span className="muted"> · {slot.duration[1]} min</span>
      {slot.chosen_by === 'coach' && <span className="status-pill info-pill">Chosen by you</span>}
      {editor && !editing && <button type="button" className="link-btn plan-change" onClick={() => setEditing(true)}>Change</button>}</p>
    {editing && <SlotEditor slot={slot} editor={editor} onDone={() => setEditing(false)} />}
    <ol className="plan-weeks">{weekRuns(slot.weeks).map(run => <li key={run.from}>
      <button type="button" onClick={() => onOpenDrill(slot.drill, run.variation.id)}><span className="muted">{run.label}</span> {run.variation.title}</button>
    </li>)}</ol>
    <ul className="plan-reasons">{slot.reasons.map(r => <li key={r}>{r}</li>)}</ul>
  </div>
}

// Override one slot: a ranked alternative or any drill in the library, its starting version, or remove the slot.
function SlotEditor({ slot, editor, onDone }) {
  const [alternatives, setAlternatives] = useState(null)
  const [library, setLibrary] = useState(null)
  const [choice, setChoice] = useState(slot.drill)
  const [variations, setVariations] = useState([])
  const [start, setStart] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    editor.alternatives(slot.skill_id, slot.slot).then(value => { if (live) setAlternatives(value) }).catch(e => { if (live) setError(errorMessage(e)) })
    getDrills().then(value => { if (live) setLibrary(value) }).catch(() => {})
    return () => { live = false }
  }, [editor, slot.skill_id, slot.slot])
  useEffect(() => {
    let live = true
    getDrill(choice).then(value => { if (live) { setVariations(value.variations); setStart('') } }).catch(() => { if (live) setVariations([]) })
    return () => { live = false }
  }, [choice])
  const run = async change => { setError(''); try { await editor.edit(slot.skill_id, slot.slot, change); onDone() } catch (e) { setError(errorMessage(e)) } }
  const listed = new Set((alternatives ?? []).map(a => a.slug))
  return <div className="slot-editor">
    {!alternatives ? <p className="muted" role="status">Loading alternatives…</p> : <>
      <fieldset><legend>The planner's ranking for this slot</legend>
        {alternatives.map(a => <label key={a.slug} className="slot-option"><input type="radio" name={`slot-${slot.skill_id}-${slot.slot}`} checked={choice === a.slug} onChange={() => setChoice(a.slug)} />
          <span><strong>{a.title}</strong>{a.slug === slot.drill && <span className="muted"> (current)</span>}<small>{a.notes.join(' · ')}</small></span></label>)}
        {!alternatives.length && <p className="muted">No other drills train this skill yet.</p>}
      </fieldset>
      {library && <label className="field">Or any drill in the library<select value={listed.has(choice) ? '' : choice} onChange={e => e.target.value && setChoice(e.target.value)}>
        <option value="">Choose a drill…</option>{library.filter(d => !listed.has(d.slug)).map(d => <option key={d.slug} value={d.slug}>{d.title}</option>)}</select></label>}
      {variations.length > 0 && <label className="field">Starting version<select value={start} onChange={e => setStart(e.target.value)}>
        <option value="">Matched to the player's level</option>{variations.map(v => <option key={v.id} value={v.id}>{v.title} (levels {v.levels[0]}–{v.levels[1]})</option>)}</select></label>}
      <div className="inline-row">
        <button type="button" onClick={() => run({ action: 'choose', drill: choice, start_variation_id: start ? Number(start) : null })}>Use this drill</button>
        {slot.chosen_by === 'coach' && <button type="button" onClick={() => run({ action: 'reset' })}>Reset to planner's choice</button>}
        <button type="button" onClick={() => run({ action: 'remove' })}>Remove from plan</button>
        <button type="button" className="link-btn" onClick={onDone}>Cancel</button>
      </div>
    </>}
    {error && <p className="error" role="alert">{error}</p>}
  </div>
}

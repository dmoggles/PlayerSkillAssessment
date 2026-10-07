import { useState, useEffect, useMemo, useRef } from 'react'
import CheckinForm from './CheckinForm'
import DevelopmentPlan from './DevelopmentPlan'
import { DrillDialog, PriorityDrills } from './DrillLibrary'
import { ratingMap, completeness, priorityScores, suggestedPriorities } from './assessment'
import { errorMessage, getCycles, getDrillSuggestions, getPriorities, setPriorities, startCycle } from './api'
import FollowUpCard from './FollowUpCard'
import { CHECKIN, PRIORITY_TAGS, keepPriority, priorityTag } from './followUpModel'

const fmt1 = (v) => (v == null ? '—' : v.toFixed(1))
const noop = () => {}

export default function PrioritiesView({ matrix, coach, player, teamId, periodId, playerId, followUp = null, onDirtyChange = noop, readOnly = false }) {
  const ranked = useMemo(() => priorityScores(matrix, coach, player), [matrix, coach, player])
  const suggested = useMemo(() => suggestedPriorities(matrix, coach, player), [matrix, coach, player])
  const byId = useMemo(() => Object.fromEntries(ranked.map(r => [r.skill_id, r])), [ranked])

  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('idle')
  const helpDialog = useRef(null)
  const [suggestions, setSuggestions] = useState({})
  const [openDrill, setOpenDrill] = useState(null)
  const [drillError, setDrillError] = useState('')
  const [drillsVersion, setDrillsVersion] = useState(0)
  // What is saved, and whether the rows differ from it: plans are only generated from saved priorities.
  const [savedSkills, setSavedSkills] = useState([])
  const [dirty, setDirty] = useState(false)
  // Development cycles in this period, newest (current) first; refreshed when a plan is saved or a cycle starts.
  const [cycles, setCycles] = useState([])
  const [cyclesVersion, setCyclesVersion] = useState(0)
  const currentCycle = cycles[0] ?? null
  const [checkingIn, setCheckingIn] = useState(false)
  const previousCycle = cycles[1] ?? null
  useEffect(() => {
    let live = true
    getCycles(teamId, playerId, periodId).then(value => { if (live) setCycles(value) }).catch(() => { if (live) setCycles([]) })
    return () => { live = false }
  }, [teamId, playerId, periodId, cyclesVersion])
  const skillsKey = rows.map(r => r.skill_id).join(',')

  // Drill suggestions follow the chosen skills, and refresh after a drill dialog closes (a vote may change them).
  useEffect(() => {
    if (!skillsKey) return
    let live = true
    getDrillSuggestions(teamId, playerId, periodId, skillsKey.split(','))
      .then(value => { if (live) setSuggestions(value) })
      .catch(() => { if (live) setSuggestions({}) })
    return () => { live = false }
  }, [teamId, playerId, periodId, skillsKey, drillsVersion])

  useEffect(() => {
    if (!coach) return
    // Seed from existing confirmations, else from the algorithm's suggestions.
    getPriorities(teamId, playerId, periodId)
      .then(existing => {
        const sorted = [...existing].sort((a, b) => a.rank - b.rank)
        if (existing.length) {
          setRows(sorted.map(e => ({ skill_id: e.skill_id, coach_note: e.coach_note ?? '' })))
        } else {
          setRows(suggested.map(s => ({ skill_id: s.skill_id, coach_note: '' })))
        }
        setSavedSkills(sorted.map(e => e.skill_id))
        setDirty(false)
        onDirtyChange(false)
      })
      .catch(() => { setRows(suggested.map(s => ({ skill_id: s.skill_id, coach_note: '' }))); setSavedSkills([]); setDirty(false); onDirtyChange(false) })
  }, [teamId, periodId, playerId, coach, suggested, onDirtyChange, currentCycle?.id])

  const followUpCard = <FollowUpCard matrix={matrix} followUp={followUp} />
  if (!coach) {
    return <div className="priorities">{followUpCard}<p className="muted">No coach assessment for this player yet — assess them first.</p></div>
  }

  const comp = completeness(matrix, coach.position, ratingMap(coach))
  if (comp.pct < 100) {
    return (
      <div className="priorities">
        {followUpCard}
        <p className="warning">Priorities unlock once the coach assessment is 100% complete.</p>
        <div className="completeness">
          <span className="completeness-label">Coach assessment</span>
          <div className="completeness-bar"><div className="completeness-fill" style={{ width: `${comp.pct}%` }} /></div>
          <span className="completeness-num">{comp.assessed}/{comp.applicable} ({Math.round(comp.pct)}%)</span>
        </div>
      </div>
    )
  }

  const updateRow = (i, patch) => { setRows(rs => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r))); setDirty(true); onDirtyChange(true); setStatus('idle') }

  const save = async () => {
    setStatus('saving')
    const priorities = rows.map((r, i) => ({
        skill_id: r.skill_id,
        rank: i + 1,
        // True only if it matches the algorithm's suggestion at this rank.
        algorithm_suggested: suggested[i]?.skill_id === r.skill_id,
        coach_note: r.coach_note?.trim() || null,
      }))
    try {
      await setPriorities(teamId, playerId, periodId, priorities)
      setStatus('saved')
      setSavedSkills(priorities.map(p => p.skill_id))
      setDirty(false)
      onDirtyChange(false)
    } catch {
      setStatus('error')
    }
  }

  const chosen = new Set(rows.map(r => r.skill_id))
  // In a later cycle, the last cycle's focus areas can be kept; in the first, last period's.
  const previousIds = previousCycle ? previousCycle.priorities.map(p => p.skill_id) : followUp?.items.map(item => item.skill_id) ?? []
  const openCheckin = () => {
    if (dirty && !window.confirm('Your unsaved priority changes will be lost. Start the next cycle anyway?')) return
    setCheckingIn(true)
  }
  // Starting the next cycle keeps this one, its plan and its check-in (if any) as history.
  const startNextCycle = async checkin => {
    try { await startCycle(teamId, playerId, periodId, checkin); setCheckingIn(false); setCyclesVersion(v => v + 1) } catch (e) { setDrillError(errorMessage(e)) }
  }
  const keep = skillId => { setRows(rs => keepPriority(rs, skillId, previousIds)); setDirty(true); onDirtyChange(true); setStatus('idle') }

  return (
    <div className="priorities">
      {currentCycle && <p className="cycle-line"><strong>Cycle {currentCycle.number}</strong> · started {shortDay(currentCycle.started_at)}</p>}
      {previousCycle
        ? <LastCycleCard matrix={matrix} cycle={previousCycle} chosen={chosen} canKeep={skillId => Boolean(byId[skillId])} onKeep={readOnly ? null : keep} />
        : <FollowUpCard matrix={matrix} followUp={followUp} chosen={chosen} canKeep={skillId => Boolean(byId[skillId])} onKeep={readOnly ? null : keep} />}
      <div className="priorities-toolbar"><button type="button" className="priority-help-button" aria-label="How priorities work" onClick={() => helpDialog.current?.showModal()}>?</button></div>
      <dialog ref={helpDialog} className="priority-help-dialog" aria-labelledby="priority-help-title">
        <form method="dialog">
          <div className="priority-help-heading"><h3 id="priority-help-title">How priorities work</h3><button type="submit" aria-label="Close instructions">×</button></div>
          <p>The algorithm suggests the three highest-urgency skills. Keep them or choose other skills from the ranked list. Tap an urgency score to see how it was calculated, then save your choices.</p>
          <button type="submit" className="priority-help-done">Got it</button>
        </form>
      </dialog>

      {rows.map((row, i) => {
        const info = byId[row.skill_id]
        const tag = priorityTag(row.skill_id, suggested[i]?.skill_id, previousIds)
        return (
          <div key={i} className="priority-row">
            <div className="priority-rank">{i + 1}</div>
            <div className="priority-body">
              <div className="priority-select-line">
                <div className="priority-select-wrap"><select
                  aria-label={`Priority ${i + 1} skill`}
                  disabled={readOnly}
                  value={row.skill_id}
                  onChange={e => updateRow(i, { skill_id: e.target.value })}
                >
                  {ranked.map(r => (
                    <option
                      key={r.skill_id}
                      value={r.skill_id}
                      disabled={chosen.has(r.skill_id) && r.skill_id !== row.skill_id}
                    >
                      {r.label}
                    </option>
                  ))}
                </select></div>
              </div>
              {info && (
                <details className="priority-breakdown">
                  <summary aria-label={`Urgency ${fmt1(info.score)}, ${PRIORITY_TAGS[tag]}. Show score breakdown`}><span>Urgency <strong>{fmt1(info.score)}</strong></span><span className="priority-breakdown-action"><span className={`alg-tag ${tag}`}>{PRIORITY_TAGS[tag]}</span><span aria-hidden="true" className="priority-breakdown-chevron">⌄</span></span></summary>
                  <div className="priority-breakdown-body">
                    <div><span>Assessment score</span><strong>{fmt1(info.avg)} / 5</strong></div>
                    <div><span>Position weight</span><strong>{fmt1(info.weight)}</strong></div>
                    {info.bonus > 0 && <div><span>Dependency bonus</span><strong>+{fmt1(info.bonus)}</strong></div>}
                  </div>
                </details>
              )}
              <input
                type="text"
                className="priority-note"
                placeholder="Optional note on why this is a priority…"
                readOnly={readOnly}
                value={row.coach_note}
                onChange={e => updateRow(i, { coach_note: e.target.value })}
              />
              <PriorityDrills suggestion={suggestions[row.skill_id]} onOpen={(slug, variationId) => { setDrillError(''); setOpenDrill({ slug, variationId }) }} />
            </div>
          </div>
        )
      })}

      {!readOnly && <button type="button" className="submit-btn" onClick={save} disabled={status === 'saving'}>
        {status === 'saving' ? 'Saving…' : 'Save priorities'}
      </button>}
      {openDrill && <DrillDialog drill={openDrill} onMessage={setDrillError} onClose={() => { setOpenDrill(null); setDrillsVersion(v => v + 1) }} />}
      <DevelopmentPlan key={currentCycle?.id ?? 'none'} teamId={teamId} playerId={playerId} periodId={periodId} skills={savedSkills} unsaved={dirty} readOnly={readOnly} onSaved={() => setCyclesVersion(v => v + 1)} onOpenDrill={(slug, variationId) => { setDrillError(''); setOpenDrill({ slug, variationId }) }} />
      {!readOnly && currentCycle?.plan && (checkingIn
        ? <CheckinForm cycle={currentCycle} names={skillNames(matrix)} onSubmit={startNextCycle} onSkip={() => startNextCycle([])} onCancel={() => setCheckingIn(false)} />
        : <div className="next-cycle"><button type="button" onClick={openCheckin}>Start cycle {currentCycle.number + 1}</button><span className="muted">When this plan is done: a quick check-in, then new focus areas. This cycle is kept as history.</span></div>)}
      {cycles.length > 1 && <EarlierCycles matrix={matrix} cycles={cycles.slice(1)} />}
      {drillError && <p className="error" role="alert">{drillError}</p>}
      {status === 'saved' && <p className="success">Priorities saved.</p>}
      {status === 'error' && <p className="error">Could not save priorities.</p>}
    </div>
  )
}

const shortDay = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const skillNames = matrix => Object.fromEntries(matrix.sections.flatMap(section => section.skills.map(skill => [skill.id, skill.label])))

// The previous cycle's focus areas, any of which can be kept for this cycle.
function LastCycleCard({ matrix, cycle, chosen, canKeep, onKeep }) {
  const names = skillNames(matrix)
  return <section className="follow-up" aria-labelledby="last-cycle-title">
    <h3 id="last-cycle-title">Last cycle's focus <small>Cycle {cycle.number}, from {shortDay(cycle.started_at)}</small></h3>
    <ol>{cycle.priorities.map(p => {
      const result = cycle.checkin?.[p.skill_id]
      return <li key={p.skill_id} className={`follow-up-item${result ? ` trend-${CHECKIN[result.trend].css}` : ''}`}>
        <span className="follow-up-rank">{p.rank}</span>
        <div className="follow-up-body">
          <div className="follow-up-line"><strong>{names[p.skill_id] ?? p.skill_id}</strong><span className="follow-up-trend">{result ? CHECKIN[result.trend].label : 'No check-in'}</span></div>
          {result?.note && <p className="follow-up-note">{result.note}</p>}
        </div>
        {onKeep && result?.trend !== 'better' && (chosen.has(p.skill_id) ? <span className="follow-up-kept">In this cycle</span>
          : <button type="button" disabled={!canKeep(p.skill_id)} onClick={() => onKeep(p.skill_id)}>Keep</button>)}
      </li>
    })}</ol>
  </section>
}

// Earlier cycles in this period, newest first: focus areas and the drills their plan used.
function EarlierCycles({ matrix, cycles }) {
  const names = skillNames(matrix)
  return <details className="earlier-cycles">
    <summary>Earlier cycles this period ({cycles.length})</summary>
    <ol>{cycles.map(c => <li key={c.id}>
      <strong>Cycle {c.number}</strong> <span className="muted">from {shortDay(c.started_at)}</span>
      <p>{c.priorities.length ? c.priorities.map((p, i) => <span key={p.skill_id}>{i > 0 && ', '}{names[p.skill_id] ?? p.skill_id}{c.checkin?.[p.skill_id] && <span className="muted"> ({CHECKIN[c.checkin[p.skill_id].trend].label.toLowerCase()})</span>}</span>) : 'No focus areas saved'}</p>
      {c.plan && <p className="muted">Plan: {[...new Set(c.plan.slots.map(slot => slot.title))].join(', ')}</p>}
    </li>)}</ol>
  </details>
}

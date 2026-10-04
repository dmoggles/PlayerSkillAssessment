import { useState, useEffect, useMemo, useRef } from 'react'
import { ratingMap, completeness, priorityScores, suggestedPriorities } from './assessment'
import { getPriorities, setPriorities } from './api'
import FollowUpCard from './FollowUpCard'
import { PRIORITY_TAGS, keepPriority, priorityTag } from './followUpModel'

const fmt1 = (v) => (v == null ? '—' : v.toFixed(1))
const noop = () => {}

export default function PrioritiesView({ matrix, coach, player, teamId, periodId, playerId, followUp = null, onDirtyChange = noop, readOnly = false }) {
  const ranked = useMemo(() => priorityScores(matrix, coach, player), [matrix, coach, player])
  const suggested = useMemo(() => suggestedPriorities(matrix, coach, player), [matrix, coach, player])
  const byId = useMemo(() => Object.fromEntries(ranked.map(r => [r.skill_id, r])), [ranked])

  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('idle')
  const helpDialog = useRef(null)

  useEffect(() => {
    if (!coach) return
    // Seed from existing confirmations, else from the algorithm's suggestions.
    getPriorities(teamId, playerId, periodId)
      .then(existing => {
        if (existing.length) {
          setRows(existing
            .sort((a, b) => a.rank - b.rank)
            .map(e => ({ skill_id: e.skill_id, coach_note: e.coach_note ?? '' })))
        } else {
          setRows(suggested.map(s => ({ skill_id: s.skill_id, coach_note: '' })))
        }
        onDirtyChange(false)
      })
      .catch(() => { setRows(suggested.map(s => ({ skill_id: s.skill_id, coach_note: '' }))); onDirtyChange(false) })
  }, [teamId, periodId, playerId, coach, suggested, onDirtyChange])

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

  const updateRow = (i, patch) => { setRows(rs => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r))); onDirtyChange(true); setStatus('idle') }

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
      onDirtyChange(false)
    } catch {
      setStatus('error')
    }
  }

  const chosen = new Set(rows.map(r => r.skill_id))
  const previousIds = followUp?.items.map(item => item.skill_id) ?? []
  const keep = skillId => { setRows(rs => keepPriority(rs, skillId, previousIds)); onDirtyChange(true); setStatus('idle') }

  return (
    <div className="priorities">
      <FollowUpCard matrix={matrix} followUp={followUp} chosen={chosen} canKeep={skillId => Boolean(byId[skillId])} onKeep={readOnly ? null : keep} />
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
            </div>
          </div>
        )
      })}

      {!readOnly && <button type="button" className="submit-btn" onClick={save} disabled={status === 'saving'}>
        {status === 'saving' ? 'Saving…' : 'Save priorities'}
      </button>}
      {status === 'saved' && <p className="success">Priorities saved.</p>}
      {status === 'error' && <p className="error">Could not save priorities.</p>}
    </div>
  )
}

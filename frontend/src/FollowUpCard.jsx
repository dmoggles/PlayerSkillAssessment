import { TRENDS } from './followUpModel'

// "Last period's priorities": how each one moved since it was confirmed. With onKeep,
// priorities that did not improve can be carried into this period's choices.
export default function FollowUpCard({ matrix, followUp, chosen = new Set(), canKeep = () => false, onKeep = null }) {
  if (!followUp) return null
  const names = Object.fromEntries(matrix.sections.flatMap(section => section.skills.map(skill => [skill.id, skill.label])))
  return <section className="follow-up" aria-labelledby="follow-up-title">
    <h3 id="follow-up-title">Last period's priorities <small>{followUp.periodLabel}</small></h3>
    <ol>{followUp.items.map(item => <li key={item.skill_id} className={`follow-up-item trend-${item.trend}`}>
      <span className="follow-up-rank">{item.rank}</span>
      <div className="follow-up-body">
        <div className="follow-up-line"><strong>{names[item.skill_id] ?? item.skill_id}</strong><span className="follow-up-trend">{TRENDS[item.trend]}</span></div>
        <span className="follow-up-scores">Coach score {item.before ?? '—'} → {item.now ?? '—'}</span>
        {item.coach_note && <p className="follow-up-note">{item.coach_note}</p>}
      </div>
      {onKeep && item.trend !== 'improved' && (chosen.has(item.skill_id)
        ? <span className="follow-up-kept">In this period</span>
        : <button type="button" disabled={!canKeep(item.skill_id)} title={canKeep(item.skill_id) ? undefined : 'Not available for the current position or assessment'} onClick={() => onKeep(item.skill_id)}>Keep</button>)}
    </li>)}</ol>
  </section>
}

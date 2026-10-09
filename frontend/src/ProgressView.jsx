import { CHANGE_LABELS, RATING_CHANGES, changesBetween, historyLabels } from './comparabilityModel'

// Coach scores per skill across periods, marking matrix changes (*), carried scores (~) and playing-group moves (†).
export default function ProgressView({ matrix, history }) {
  const assessed = history.map((row, index) => ({ row, index })).filter(({ row }) => row.assessments.coach)
  if (!assessed.length) return <p className="muted">No coach assessments recorded yet.</p>
  const periods = assessed.map(({ row }) => row)
  const skillIds = [...new Set(periods.flatMap(row => row.assessments.coach.ratings.map(r => r.skill_id)))]
  const names = historyLabels(history, matrix)
  const score = (row, id) => row.assessments.coach.ratings.find(r => r.skill_id === id)?.score
  // The skill matrix change (if any) that separates this period from the previous assessed one.
  const marker = (k, id) => {
    if (k === 0) return null
    const kind = changesBetween(history, assessed[k - 1].index, assessed[k].index)[id]
    return RATING_CHANGES.includes(kind) ? kind : null
  }
  const crossesChange = id => periods.some((_, k) => marker(k, id))
  const change = id => {
    const first = score(periods[0], id)
    const last = score(periods[periods.length - 1], id)
    if (first == null || last == null || periods.length < 2) return '—'
    return `${last - first > 0 ? '+' : ''}${last - first}${crossesChange(id) ? '*' : ''}`
  }
  // A score carried from the previous period and never reviewed is not a fresh rating.
  const isCarried = (row, id) => Boolean(row.assessments.coach.ratings.find(r => r.skill_id === id)?.carried)
  const anyCarried = periods.some(row => row.assessments.coach.ratings.some(r => r.carried))
  const cell = (k, row, id) => {
    const kind = marker(k, id)
    return <>{score(row, id) ?? '—'}{isCarried(row, id) && <sup className="carried-sup" title={`Carried from the previous period and not re-rated in ${row.label}.`}>~</sup>}{kind && <sup className="matrix-change" title={`Skill matrix: ${CHANGE_LABELS[kind]} in ${row.label}. Not directly comparable with earlier periods.`}>*</sup>}</>
  }
  const anyMarker = skillIds.some(crossesChange)
  // A move to another playing group: later ratings are judged against a different cohort.
  const moved = k => k > 0 && periods[k].age_group && periods[k - 1].age_group && periods[k].age_group !== periods[k - 1].age_group
  const anyMove = periods.some((_, k) => moved(k))
  const heading = (row, k) => <>{row.label}{row.age_group && <small>U{row.age_group}{moved(k) && <sup className="matrix-change" title={`Moved from U${periods[k - 1].age_group} to U${row.age_group}: rated against a different age group from here.`}>†</sup>}</small>}</>
  return <div className="history">
    <h3>Progress across periods</h3>
    <div className="desktop-data"><div className="heatmap-scroll"><table className="heatmap-table"><thead><tr><th>Skill</th>{periods.map((row, k) => <th key={row.period_id}>{heading(row, k)}</th>)}<th>Change{anyMove && <sup className="matrix-change">†</sup>}</th></tr></thead><tbody>{skillIds.map(id => <tr key={id}><td>{names[id] ?? id}</td>{periods.map((row, k) => <td key={row.period_id}>{cell(k, row, id)}</td>)}<td>{change(id)}</td></tr>)}</tbody></table></div></div>
    <div className="mobile-data mobile-card-list">{skillIds.map(id => <article className="data-card" key={id}><h4>{names[id] ?? id}</h4><dl>{periods.map((row, k) => <div key={row.period_id}><dt>{heading(row, k)}</dt><dd>{cell(k, row, id)}</dd></div>)}<div className="data-card-total"><dt>Change</dt><dd>{change(id)}</dd></div></dl></article>)}</div>
    {anyMarker && <p className="muted matrix-change-note">* The skill matrix changed for this skill (wording, added or retired), so scores before and after are not directly comparable. Hover a marked score for details.</p>}
    {anyCarried && <p className="muted matrix-change-note">~ Carried from the previous period and not re-rated yet, so it is not a fresh rating.</p>}
    {anyMove && <p className="muted matrix-change-note">† The player moved to another playing group, so ratings from that period are judged against a different age group and are not directly comparable with earlier ones.</p>}
  </div>
}

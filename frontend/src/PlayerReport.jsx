import { PlanCards } from './DevelopmentPlan'
import { PLAN_NAME } from './brand'
import { REPORT_TRENDS } from './reportModel'

const fmt = value => (value == null ? '—' : value.toFixed(1))

// The player-facing report. Pure rendering, shared by the coach preview and the shared link; onOpenDrill opens a
// plan drill (without it, the plan's drills are listed but not openable).
export default function PlayerReport({ report, onOpenDrill }) {
  return <article className="player-report">
    <header className="report-header">
      <p className="eyebrow">{report.plan ? PLAN_NAME : 'Player report'}</p>
      <h2>{report.player}</h2>
      <p>{[report.team, report.period, report.position].filter(Boolean).join(' · ')}</p>
    </header>
    {report.message && <section><h3>From your coach</h3><p className="report-message">{report.message}</p></section>}
    {!report.assessed ? <p className="muted">There is no coach assessment for this period yet.</p> : <>
      <section><h3>Skill areas</h3>
        <div className="report-bars">{report.sections.map(section => <div className="report-bar" key={section.id}>
          <span>{section.label}</span>
          <div className="report-bar-track" aria-hidden="true"><div className="report-bar-fill" style={{ width: `${((section.score ?? 0) / 5) * 100}%` }} /></div>
          <strong>{fmt(section.score)} / 5</strong>
        </div>)}</div>
      </section>
      <section><h3>Strengths</h3><ol className="report-list">{report.strengths.map(skill => <li key={skill.label}>{skill.label}</li>)}</ol></section>
      <section><h3>Focus for next period</h3>{report.priorities.length
        ? <ol className="report-list">{report.priorities.map(p => <li key={p.rank}><strong>{p.label}</strong>{p.note && <p>{p.note}</p>}</li>)}</ol>
        : <p className="muted">Focus areas will be agreed with your coach.</p>}
        {report.earlierFocus?.length > 0 && <p className="report-earlier-focus">Earlier this period: {report.earlierFocus.join(', ')}</p>}</section>
    </>}
    {report.plan && <section className="report-plan"><h3>Practice at home <small>{report.plan.weeks} weeks</small></h3>
      <p className="muted">A drill to practise at home for each focus area, getting a little harder after two weeks. Tap a week to see that version of the drill.</p>
      <PlanCards plan={report.plan} onOpenDrill={onOpenDrill ?? (() => {})} />
    </section>}
    {report.followUp && <section><h3>Last period's focus <small>{report.followUp.label}</small></h3>
      <ul className="report-follow-up">{report.followUp.items.map(item => <li key={item.skill_id}><span>{item.label}{item.change === 'reworded' && <sup className="matrix-change" title="The skill's wording changed since then">*</sup>}</span><span className={`report-trend trend-${item.trend}`}>{REPORT_TRENDS[item.trend]}</span><small>{item.before ?? '—'} → {item.now ?? '—'}</small></li>)}</ul>
    </section>}
    {report.assessed && report.trend.periods.length > 1 && <section><h3>Progress</h3>
      <div className="report-table-scroll"><table className="report-table"><thead><tr><th>Skill area</th>{report.trend.periods.map((label, i) => <th key={label}>{label}{report.trend.groups?.[i]?.age && <small> U{report.trend.groups[i].age}{report.trend.groups[i].moved && <sup className="matrix-change">†</sup>}</small>}</th>)}</tr></thead>
        <tbody>{report.trend.rows.map(row => <tr key={row.label}><td>{row.label}</td>{row.values.map((value, i) => <td key={i}>{fmt(value)}{row.changed?.[i] && <sup className="matrix-change">*</sup>}</td>)}</tr>)}</tbody></table></div>
      {report.trend.groups?.some(g => g.moved) && <p className="report-footnote">† Moved to another age group: from here, ratings are compared with that age group.</p>}
      {report.trend.rows.some(row => row.changed?.some(Boolean)) && <p className="report-footnote">* The skills in this area changed from this period, so it is not directly comparable with earlier periods.</p>}
    </section>}
    {report.scale && <footer className="report-footer">Ratings use a 1–5 scale: {report.scale}.</footer>}
  </article>
}

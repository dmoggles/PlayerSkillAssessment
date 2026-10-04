import { REPORT_TRENDS } from './reportModel'

const fmt = value => (value == null ? '—' : value.toFixed(1))

// The player-facing report. Pure rendering, shared by the coach preview and (later) the shared link.
export default function PlayerReport({ report }) {
  return <article className="player-report">
    <header className="report-header">
      <p className="eyebrow">Player report</p>
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
        : <p className="muted">Focus areas will be agreed with your coach.</p>}</section>
    </>}
    {report.followUp && <section><h3>Last period's focus <small>{report.followUp.label}</small></h3>
      <ul className="report-follow-up">{report.followUp.items.map(item => <li key={item.skill_id}><span>{item.label}</span><span className={`report-trend trend-${item.trend}`}>{REPORT_TRENDS[item.trend]}</span><small>{item.before ?? '—'} → {item.now ?? '—'}</small></li>)}</ul>
    </section>}
    {report.assessed && report.trend.periods.length > 1 && <section><h3>Progress</h3>
      <div className="report-table-scroll"><table className="report-table"><thead><tr><th>Skill area</th>{report.trend.periods.map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{report.trend.rows.map(row => <tr key={row.label}><td>{row.label}</td>{row.values.map((value, i) => <td key={i}>{fmt(value)}</td>)}</tr>)}</tbody></table></div>
    </section>}
    {report.scale && <footer className="report-footer">Ratings use a 1–5 scale: {report.scale}.</footer>}
  </article>
}

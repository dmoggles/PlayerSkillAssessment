import { useEffect, useState } from 'react'
import { errorMessage, getInsights } from './api'
import TrendChart from './TrendChart'
import { AREA_LABELS, POSITION_FILTERS, SHOWN_PLAYERS, fmt, groupName, positionLabel, priorityCount, sectionSeries, sortByRank, tagPositionRows, tagTrendRows } from './insightsModel'

const CHANGE_NOTE = '* Skills in this area changed in the skill matrix from this period, so it is not directly comparable with earlier periods.'

// Squad-level views for Team Data: trends across periods, common priorities, and position groups.
// position filters Trends and Priorities; Positions always compares the whole squad.
export default function TeamInsights({ teamId, periodId, view, position, onPositionChange, onMessage }) {
  const [data, setData] = useState(null)
  const filter = view === 'positions' ? '' : position
  useEffect(() => {
    let live = true
    getInsights(teamId, periodId, filter).then(value => { if (live) setData(value) }).catch(e => onMessage(errorMessage(e)))
    return () => { live = false }
  }, [teamId, periodId, filter, onMessage])
  const control = view !== 'positions' && <label className="field insights-filter">Position<select value={position} onChange={e => { setData(null); onPositionChange(e.target.value) }}>
    {POSITION_FILTERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
  const stale = !data || (data.position ?? '') !== filter
  return <>
    {control}
    {stale ? <p className="muted" role="status">Loading squad insights…</p>
      : view === 'trends' ? <Trends data={data} /> : view === 'priorities' ? <Priorities data={data} /> : <Positions data={data} />}
  </>
}

function Trends({ data }) {
  if (!data.trend.length) return <p className="muted">{data.position ? `No ${groupName(data.position)} have coach assessments yet.` : 'No coach assessments yet.'}</p>
  const series = sectionSeries(data)
  const periods = data.trend.map(p => p.label)
  const tags = tagTrendRows(data)
  const anyChange = series.some(s => s.changed.some(Boolean))
  return <div className="insights">
    <p className="muted">{data.position ? `Average of coach ratings for ${groupName(data.position)}: players whose primary position in each period was ${positionLabel(data.position).toLowerCase()}.` : 'Squad average of coach ratings. Each player counts once per period; a period includes everyone assessed in it.'}</p>
    <TrendChart periods={periods} series={series} />
    {anyChange && <p className="matrix-change-note">{CHANGE_NOTE}</p>}
    <h3>By skill area</h3>
    <div className="heatmap-scroll"><table className="heatmap-table insights-table"><thead><tr><th>Skill area</th>{data.trend.map(p => <th key={p.period_id}>{p.label}<small>{p.players} {p.players === 1 ? 'player' : 'players'}</small></th>)}</tr></thead>
      <tbody>{series.map(s => <tr key={s.id}><td><span className="legend-key" style={{ background: s.color }} aria-hidden="true" />{s.label}</td>{s.values.map((v, i) => <td key={i}>{fmt(v)}{s.changed[i] && <sup className="matrix-change">*</sup>}</td>)}</tr>)}</tbody></table></div>
    <h3>By skill tag</h3>
    <p className="muted">Tags compare across skill matrix versions, so these stay comparable even when the team's skills change.</p>
    <TagTable rows={tags} columns={periods} />
  </div>
}

function TagTable({ rows, columns }) {
  return <div className="heatmap-scroll"><table className="heatmap-table insights-table"><thead><tr><th>Skill tag</th>{columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
    <tbody>{rows.flatMap((row, index) => [
      (index === 0 || rows[index - 1].area !== row.area) && <tr key={`area-${row.area}`} className="area-row"><th colSpan={columns.length + 1} scope="colgroup">{AREA_LABELS[row.area] ?? row.area}</th></tr>,
      <tr key={row.id}><td>{row.label}</td>{row.values.map((v, i) => <td key={i}>{fmt(v)}</td>)}</tr>,
    ])}</tbody></table></div>
}

// Names sorted by rank; long lists show the first few with a control to expand the rest.
export function PlayerList({ players }) {
  const [open, setOpen] = useState(false)
  const sorted = sortByRank(players)
  const shown = open ? sorted : sorted.slice(0, SHOWN_PLAYERS)
  const hidden = sorted.length - shown.length
  return <span className="insight-players">
    {shown.map(p => `${p.player} (#${p.rank})`).join(', ')}
    {hidden > 0 && <> <button type="button" className="link-btn" aria-expanded="false" onClick={() => setOpen(true)}>+{hidden} more</button></>}
    {open && sorted.length > SHOWN_PLAYERS && <> <button type="button" className="link-btn" aria-expanded="true" onClick={() => setOpen(false)}>Show fewer</button></>}
  </span>
}

function Priorities({ data }) {
  const period = data.period
  if (!period) return <p className="muted">Choose a period to see its priorities.</p>
  if (!period.priorities.length) return <p className="muted">{data.position ? `No ${groupName(data.position)} have confirmed priorities in ${period.label}.` : `No confirmed priorities in ${period.label} yet. Confirm them per player in Development.`}</p>
  const max = Math.max(...period.priority_tags.map(t => t.players.length), 1)
  return <div className="insights">
    <p className="muted">{period.priority_players} of {period.assessed} assessed {data.position ? groupName(data.position) : 'players'} have confirmed priorities in {period.label}.</p>
    <h3>By training focus</h3>
    <p className="muted">Each priority counts toward its Main skill tag: useful for planning group sessions.</p>
    <ul className="insight-bars">{period.priority_tags.map(t => <li key={t.tag_id}>
      <div className="insight-bar-head"><strong>{data.tags[t.tag_id]?.label ?? t.tag_id}</strong><span>{priorityCount(t.players)}</span></div>
      <div className="insight-bar-track" aria-hidden="true"><div className="insight-bar-fill" style={{ width: `${(t.players.length / max) * 100}%` }} /></div>
      <PlayerList players={t.players} />
    </li>)}</ul>
    <h3>By skill</h3>
    <ul className="insight-list">{period.priorities.map(p => <li key={p.skill_id}><strong>{p.label}</strong> <span className="muted">{priorityCount(p.players)}</span><br /><PlayerList players={p.players} /></li>)}</ul>
  </div>
}

function Positions({ data }) {
  const period = data.period
  if (!period?.positions.length) return <p className="muted">No coach assessments in this period yet.</p>
  const groups = period.positions
  const header = <tr><th>{''}</th>{groups.map(g => <th key={g.position}>{positionLabel(g.position)}<small>{g.players} {g.players === 1 ? 'player' : 'players'}</small></th>)}</tr>
  const sectionIds = [...new Set(groups.flatMap(g => Object.keys(g.sections)))]
  return <div className="insights">
    <p className="muted">Average coach ratings in {period.label}, grouped by each player's primary position.</p>
    <h3>By skill area</h3>
    <div className="heatmap-scroll"><table className="heatmap-table insights-table"><thead>{header}</thead>
      <tbody>{sectionIds.map(id => <tr key={id}><td>{data.section_labels[id] ?? id}</td>{groups.map(g => <td key={g.position}>{fmt(g.sections[id]?.average)}</td>)}</tr>)}</tbody></table></div>
    <h3>By skill tag</h3>
    <TagTable rows={tagPositionRows(data, groups)} columns={groups.map(g => positionLabel(g.position))} />
  </div>
}

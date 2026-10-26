import { useEffect, useState } from 'react'
import { errorMessage, getPlayerProfile } from './api'
import { fmt } from './insightsModel'
import { LEVELS, axisAngle, canDrawWeb, labelLines, labelPlacement, profileSeries, radarPoint, webSegments } from './profileModel'

const W = 480, H = 360, GEOMETRY = { cx: W / 2, cy: H / 2, r: 120 }

// The player's level per skill category as a web: coach and self-assessment for the period, and the coach's
// levels from the previous period. The table underneath holds the same values.
// A coach can lay another player from the team over it, to compare the two players' coach levels.
export default function ProfileView({ teamId, playerId, periodId, selfAssessmentOn, playerName, players = [] }) {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [compareId, setCompareId] = useState('')
  const [compare, setCompare] = useState(null)  // { id, name, profile } once loaded

  useEffect(() => {
    let live = true
    getPlayerProfile(teamId, playerId, periodId).then(value => { if (live) setProfile(value) }).catch(e => { if (live) setError(errorMessage(e)) })
    return () => { live = false }
  }, [teamId, playerId, periodId])
  useEffect(() => {
    if (!compareId) return undefined
    let live = true
    const name = players.find(p => String(p.id) === compareId)?.name ?? 'Other player'
    getPlayerProfile(teamId, compareId, periodId).then(value => { if (live) setCompare({ id: compareId, name, profile: value }) })
      .catch(e => { if (live) setError(errorMessage(e)) })
    return () => { live = false }
  }, [teamId, compareId, periodId, players])

  if (error) return <p className="error" role="alert">{error}</p>
  if (!profile) return <p className="muted" role="status">Loading profile…</p>
  const others = players.filter(p => String(p.id) !== String(playerId) && (p.active || String(p.id) === compareId)).sort((a, b) => a.name.localeCompare(b.name))
  const shown = compareId && compare?.id === compareId ? compare : null
  return <>
    {others.length > 0 && <label className="field profile-compare">Compare with
      <select value={compareId} onChange={e => setCompareId(e.target.value)}>
        <option value="">Nobody</option>
        {others.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>}
    {compareId && !shown && <p className="muted" role="status">Loading…</p>}
    <ProfileChart profile={{ ...profile, name: playerName }} compare={shown} selfAssessmentOn={selfAssessmentOn} />
  </>
}

export function ProfileChart({ profile, selfAssessmentOn, compare = null }) {
  const [hover, setHover] = useState(null)
  if (!profile.coach && !profile.player) return <p className="muted">No assessments recorded for this player yet.</p>
  const { categories } = profile
  const series = profileSeries(profile, compare)
  const n = categories.length

  const nearest = event => {
    const box = event.currentTarget.getBoundingClientRect()
    const px = ((event.clientX - box.left) / box.width) * W - GEOMETRY.cx, py = ((event.clientY - box.top) / box.height) * H - GEOMETRY.cy
    const angle = Math.atan2(py, px)
    let best = 0
    categories.forEach((_, i) => {
      const gap = a => Math.abs(Math.atan2(Math.sin(a - angle), Math.cos(a - angle)))
      if (gap(axisAngle(i, n)) < gap(axisAngle(best, n))) best = i
    })
    setHover(best)
  }

  return <div className="profile">
    {!profile.coach && <p className="warning">You haven't saved a coach assessment yet.</p>}
    {!compare && selfAssessmentOn && profile.coach && !profile.player && <p className="warning">No player self-assessment submitted yet.</p>}
    {compare && !compare.profile.coach && <p className="warning">{compare.name} has no coach assessment this period.</p>}
    {compare?.profile.coach && compare.profile.position !== profile.position && <p className="muted hint">
      {compare.name} is assessed as {compare.profile.position === 'goalkeeper' ? 'a goalkeeper' : 'an outfield player'}, so only the categories they share are compared.</p>}
    <ul className="chart-legend">{series.map(s => <li key={s.id}><span className={`legend-key${s.dashed ? ' legend-key-dashed' : ''}`} style={{ background: s.dashed ? 'none' : s.color, borderColor: s.color }} aria-hidden="true" />{s.label}</li>)}</ul>
    {canDrawWeb(categories)
      ? <div className="profile-plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Level per skill category, from 1 at the centre to 5 at the edge. The same values are in the table below."
          onPointerMove={nearest} onPointerLeave={() => setHover(null)}>
          {LEVELS.map(level => <polygon key={level} className="chart-grid" fill="none"
            points={categories.map((_, i) => radarPoint(i, n, level, GEOMETRY).join(',')).join(' ')} />)}
          {categories.map((c, i) => {
            const [x, y] = radarPoint(i, n, LEVELS.length, GEOMETRY)
            return <line key={c.id} x1={GEOMETRY.cx} y1={GEOMETRY.cy} x2={x} y2={y} className={hover === i ? 'chart-crosshair' : 'chart-grid'} />
          })}
          {LEVELS.map(level => <text key={level} x={GEOMETRY.cx + 4} y={radarPoint(0, n, level, GEOMETRY)[1] + 4} className="chart-axis">{level}</text>)}
          {series.map(s => {
            const { closed, runs } = webSegments(s.values, GEOMETRY)
            const points = run => run.map(p => p.join(',')).join(' ')
            return <g key={s.id}>
              {runs.map((run, k) => closed
                ? <polygon key={k} points={points(run)} fill={s.filled ? s.color : 'none'} fillOpacity={s.filled ? 0.18 : undefined} stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeDasharray={s.dashed ? '5 4' : undefined} />
                : <polyline key={k} points={points(run)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" strokeDasharray={s.dashed ? '5 4' : undefined} />)}
              {!s.dashed && s.values.map((v, i) => v != null && <circle key={i} cx={radarPoint(i, n, v, GEOMETRY)[0]} cy={radarPoint(i, n, v, GEOMETRY)[1]} r={hover === i ? 5 : 3.5} fill={s.color} className="chart-point" />)}
            </g>
          })}
          {categories.map((c, i) => {
            const place = labelPlacement(i, n, GEOMETRY), lines = labelLines(c.label)
            const top = place.below ? place.y + 10 : place.above ? place.y - (lines.length - 1) * 15 : place.y + 4 - ((lines.length - 1) * 15) / 2
            return <text key={c.id} x={place.x} y={top} textAnchor={place.anchor} className={`profile-label${hover === i ? ' active' : ''}`}>
              {lines.map((line, k) => <tspan key={k} x={place.x} dy={k ? 15 : 0}>{line}</tspan>)}
            </text>
          })}
        </svg>
        {hover != null && <div className="chart-tooltip profile-tooltip" role="status">
          <strong>{categories[hover].label}</strong>
          {[...series].reverse().map(s => <div key={s.id}><span className="legend-key" style={{ background: s.color }} aria-hidden="true" /><b>{fmt(s.values[hover])}</b> {s.label}</div>)}
        </div>}
      </div>
      : <p className="muted">Too few skill categories are rated to draw a web; the levels are below.</p>}
    {n > 0 && <table className="data-table profile-table">
      <thead><tr><th scope="col">Category</th>{[...series].reverse().map(s => <th scope="col" className="num" key={s.id}>
        <span className="legend-key" style={{ background: s.color }} aria-hidden="true" />{s.short}{s.sub && <small>{s.sub}</small>}</th>)}</tr></thead>
      <tbody>{categories.map((c, i) => <tr key={c.id}><th scope="row">{c.label}</th>{[...series].reverse().map(s => <td className="num" key={s.id}>{fmt(s.values[i])}</td>)}</tr>)}</tbody>
    </table>}
  </div>
}

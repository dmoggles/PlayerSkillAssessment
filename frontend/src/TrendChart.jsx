import { useState } from 'react'
import { fmt, placeEndLabels } from './insightsModel'

const W = 640, H = 260, PAD = { left: 56, right: 130, top: 16, bottom: 36 }

// Squad average per skill area across periods: one 2px line per area, crosshair + tooltip on hover.
export default function TrendChart({ periods, series }) {
  const [hover, setHover] = useState(null)
  const plotW = W - PAD.left - PAD.right, plotH = H - PAD.top - PAD.bottom
  const x = i => PAD.left + (periods.length === 1 ? plotW / 2 : (plotW * i) / (periods.length - 1))
  const y = v => PAD.top + plotH * (1 - (v - 1) / 4)
  const segments = values => {
    const parts = []
    let current = []
    values.forEach((v, i) => { if (v == null) { if (current.length) parts.push(current); current = [] } else current.push([x(i), y(v)]) })
    if (current.length) parts.push(current)
    return parts
  }
  const nearest = event => {
    const box = event.currentTarget.getBoundingClientRect()
    const px = ((event.clientX - box.left) / box.width) * W
    let best = 0
    periods.forEach((_, i) => { if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i })
    setHover(best)
  }
  const lastIndex = values => values.reduce((last, v, i) => (v != null ? i : last), -1)
  const endLabels = placeEndLabels(series.filter(s => lastIndex(s.values) >= 0).map(s => {
    const i = lastIndex(s.values)
    return { id: s.id, label: s.label, x: x(i), y: y(s.values[i]) }
  }), PAD.top + 4, PAD.top + plotH + 4)

  return <div className="trend-chart">
    <ul className="chart-legend">{series.map(s => <li key={s.id}><span className="legend-key" style={{ background: s.color }} aria-hidden="true" />{s.label}</li>)}</ul>
    <div className="trend-chart-plot">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Squad average by skill area across periods. The same values are in the table below."
        onPointerMove={nearest} onPointerLeave={() => setHover(null)}>
        {[1, 2, 3, 4, 5].map(v => <g key={v}><line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} className="chart-grid" /><text x={PAD.left - 10} y={y(v) + 4} textAnchor="end" className="chart-axis">{v}</text></g>)}
        {periods.map((label, i) => <text key={label + i} x={x(i)} y={H - 12} textAnchor="middle" className="chart-axis">{label}</text>)}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} className="chart-crosshair" />}
        {series.map(s => <g key={s.id}>
          {segments(s.values).map((points, k) => <polyline key={k} points={points.map(p => p.join(',')).join(' ')} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />)}
          {s.values.map((v, i) => v != null && <circle key={i} cx={x(i)} cy={y(v)} r={hover === i ? 5 : 4} fill={s.color} className="chart-point" />)}
          {s.values.map((v, i) => v != null && s.changed[i] && <text key={`c${i}`} x={x(i) + 7} y={y(v) - 7} className="chart-change">*</text>)}
        </g>)}
        {endLabels.map(label => <text key={label.id} x={label.x + 10} y={label.labelY + 4} className="chart-direct-label">{label.label}</text>)}
      </svg>
      {hover != null && <div className="chart-tooltip" style={{ left: `${(x(hover) / W) * 100}%` }} role="status">
        <strong>{periods[hover]}</strong>
        {series.map(s => <div key={s.id}><span className="legend-key" style={{ background: s.color }} aria-hidden="true" /><b>{fmt(s.values[hover])}</b> {s.label}{s.changed[hover] ? ' *' : ''}</div>)}
      </div>}
    </div>
  </div>
}

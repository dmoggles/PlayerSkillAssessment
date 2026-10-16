// Geometry and series for the player profile web: one spoke per skill category, levels 1–5 out from the centre.
import { SERIES_COLORS } from './insightsModel'

export const MIN_AXES = 3
export const LEVELS = [1, 2, 3, 4, 5]

// A web needs at least three spokes; with fewer, the view falls back to the table alone.
export const canDrawWeb = categories => categories.length >= MIN_AXES

// Spoke i of n, starting at the top and going clockwise.
export const axisAngle = (i, n) => -Math.PI / 2 + (2 * Math.PI * i) / n

export function radarPoint(i, n, value, { cx, cy, r }) {
  const angle = axisAngle(i, n), distance = (r * value) / LEVELS.length
  return [cx + distance * Math.cos(angle), cy + distance * Math.sin(angle)]
}

// The shape's outline as runs of consecutive spokes that have a value. A spoke without one breaks the outline
// rather than pulling it to the centre; the outline closes only when every spoke has a value.
export function webSegments(values, geometry) {
  const n = values.length
  const point = i => radarPoint(i, n, values[i], geometry)
  if (values.every(v => v != null)) return { closed: true, runs: [values.map((_, i) => point(i))] }
  const runs = []
  let current = []
  values.forEach((v, i) => { if (v == null) { if (current.length) runs.push(current); current = [] } else current.push(point(i)) })
  if (current.length) runs.push(current)
  // Join the last run onto the first when the outline wraps past the top spoke.
  if (runs.length > 1 && values[0] != null && values[n - 1] != null) runs[0] = [...runs.pop(), ...runs[0]]
  return { closed: false, runs }
}

// Where a spoke's label sits, and which way it reads, so labels clear the web on every side.
export function labelPlacement(i, n, { cx, cy, r }, gap = 14) {
  const angle = axisAngle(i, n), cos = Math.cos(angle), sin = Math.sin(angle)
  const anchor = Math.abs(cos) < 0.2 ? 'middle' : cos > 0 ? 'start' : 'end'
  return { x: cx + (r + gap) * cos, y: cy + (r + gap) * sin, anchor, below: sin > 0.2, above: sin < -0.2 }
}

// Long labels wrap onto two lines at the space nearest the middle.
export function labelLines(label, max = 12) {
  if (label.length <= max || !label.includes(' ')) return [label]
  const middle = label.length / 2
  const spaces = [...label].map((c, i) => (c === ' ' ? i : -1)).filter(i => i >= 0)
  const cut = spaces.reduce((best, i) => (Math.abs(i - middle) < Math.abs(best - middle) ? i : best))
  return [label.slice(0, cut), label.slice(cut + 1)]
}

// The shapes drawn on the web, back to front: last period's coach levels, then this period's player and coach.
export function profileSeries(profile) {
  const values = levels => profile.categories.map(c => levels?.[c.id] ?? null)
  const series = []
  if (profile.previous) series.push({ id: 'previous', label: `Coach, ${profile.previous.period_label}`, color: '#8795a1', dashed: true, values: values(profile.previous.coach) })
  if (profile.player) series.push({ id: 'player', label: 'Player', color: SERIES_COLORS[1], values: values(profile.player) })
  if (profile.coach) series.push({ id: 'coach', label: 'Coach', color: SERIES_COLORS[0], filled: true, values: values(profile.coach) })
  return series
}

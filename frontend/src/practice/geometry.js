// Pitch geometry for practice scenarios, in metres. x runs from our goal line (0) up the pitch and y across it,
// so our goal's centre is (0, width / 2) whatever the format.

export const goalOf = pitch => ({ x: 0, y: pitch.width / 2 })
export const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y)

// The angle in degrees between the line from `from` to `a` and the line from `from` to `b`.
export function angleAt(from, a, b) {
  const u = { x: a.x - from.x, y: a.y - from.y }, v = { x: b.x - from.x, y: b.y - from.y }
  const lengths = Math.hypot(u.x, u.y) * Math.hypot(v.x, v.y)
  if (!lengths) return 0
  return (Math.acos(Math.max(-1, Math.min(1, (u.x * v.x + u.y * v.y) / lengths))) * 180) / Math.PI
}

// Which side of the line from `a` through `b` a point is on (positive one way, negative the other), and how far.
export const sideOf = (a, b, point) => Math.sign((b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x))
export function distanceToLine(a, b, point) {
  const length = distance(a, b)
  return length ? Math.abs((b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x)) / length : distance(a, point)
}

export function inZone(zone, point) {
  if (zone.type === 'ellipse') return ((point.x - zone.cx) / zone.rx) ** 2 + ((point.y - zone.cy) / zone.ry) ** 2 <= 1
  // A polygon: count crossings of a ray from the point.
  let inside = false
  const corners = zone.corners
  for (let i = 0, j = corners.length - 1; i < corners.length; j = i++) {
    const [xi, yi] = corners[i], [xj, yj] = corners[j]
    if ((yi > point.y) !== (yj > point.y) && point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

export function zoneCentre(zone) {
  if (zone.type === 'ellipse') return { x: zone.cx, y: zone.cy }
  const n = zone.corners.length
  return { x: zone.corners.reduce((sum, c) => sum + c[0], 0) / n, y: zone.corners.reduce((sum, c) => sum + c[1], 0) / n }
}

// How much of the pitch a scenario shows, from our goal line up: its own view, or the half and a bit.
export const viewDepth = scenario => Math.min(scenario.pitch.length, scenario.view?.depth ?? scenario.pitch.length / 2 + 5)

// Phones are held upright, so the pitch is drawn with our goal at the bottom: across the pitch is across the
// screen. These turn pitch metres into drawing units (still metres) and back.
export const toScreen = (point, depth) => [point.y, depth - point.x]
export const toPitch = ([sx, sy], depth) => ({ x: depth - sy, y: sx })
export const clampToView = (point, pitch, depth) => ({ x: Math.min(depth, Math.max(0, point.x)), y: Math.min(pitch.width, Math.max(0, point.y)) })

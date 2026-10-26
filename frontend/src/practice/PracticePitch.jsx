import { useRef } from 'react'
import { clampToView, goalOf, toPitch, toScreen, viewDepth } from './geometry'

const PAD = 1.5  // metres of margin around the drawn pitch
const R = 1.35  // a player's drawn radius, in metres: bigger than life, to see and to touch
const STEP = 0.5, BIG_STEP = 2  // metres an arrow key moves your player, without and with Shift

// The pitch for a practice frame, upright with our goal at the bottom, drawn in metres. Your player can be dragged,
// placed with a tap, or moved with the arrow keys; everything else shows where it is. Which attacker is theirs to
// mark isn't shown: working that out is part of it. `shown` holds the positions
// to draw (they move between frames), `position` is your player's.
export default function PracticePitch({ scenario, shown, position, onMove, disabled = false, ghost = null, lines = false }) {
  const svg = useRef(null)
  const dragging = useRef(false)
  const { pitch } = scenario
  const depth = viewDepth(scenario)
  const at = point => toScreen(point, depth)
  const [gx, gy] = at(goalOf(pitch))
  const area = pitch.penaltyArea

  const pointFrom = event => {
    const matrix = svg.current.getScreenCTM()
    if (!matrix) return null
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return clampToView(toPitch([p.x, p.y], depth), pitch, depth)
  }
  const down = event => {
    if (disabled) return
    const point = pointFrom(event)
    if (!point) return
    dragging.current = true
    svg.current.setPointerCapture?.(event.pointerId)
    onMove(point)
  }
  const move = event => { if (dragging.current && !disabled) { const point = pointFrom(event); if (point) onMove(point) } }
  const up = event => { dragging.current = false; svg.current.releasePointerCapture?.(event.pointerId) }
  const key = event => {
    if (disabled) return
    const step = event.shiftKey ? BIG_STEP : STEP
    // Up the screen is up the pitch; left and right are across it.
    const delta = { ArrowUp: [step, 0], ArrowDown: [-step, 0], ArrowLeft: [0, -step], ArrowRight: [0, step] }[event.key]
    if (!delta) return
    event.preventDefault()
    onMove(clampToView({ x: position.x + delta[0], y: position.y + delta[1] }, pitch, depth))
  }

  const ball = at(shown.ball)
  const presser = shown.team.find(p => p.action === 'PRESS')
  return <svg ref={svg} className="practice-pitch" viewBox={`${-PAD} ${-PAD} ${pitch.width + 2 * PAD} ${depth + 2 * PAD + 1}`}
    role="application" aria-label="Pitch with your goal at the bottom. Drag your player, tap where they should stand, or use the arrow keys."
    onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
    <rect x={0} y={0} width={pitch.width} height={depth} className="practice-grass" />
    <line x1={0} y1={depth} x2={pitch.width} y2={depth} className="practice-line" />
    <line x1={0} y1={0} x2={0} y2={depth} className="practice-line" />
    <line x1={pitch.width} y1={0} x2={pitch.width} y2={depth} className="practice-line" />
    {depth < pitch.length && <line x1={0} y1={0} x2={pitch.width} y2={0} className="practice-line practice-cut" />}
    {pitch.length / 2 <= depth && <line x1={0} y1={depth - pitch.length / 2} x2={pitch.width} y2={depth - pitch.length / 2} className="practice-line" />}
    <rect x={gx - area.width / 2} y={depth - area.depth} width={area.width} height={area.depth} className="practice-line" fill="none" />
    <circle cx={gx} cy={depth - pitch.penaltySpot} r={0.25} className="practice-spot" />
    <rect x={gx - pitch.goalWidth / 2} y={depth} width={pitch.goalWidth} height={1} className="practice-goal" />

    {lines && <g className="practice-guides" aria-hidden="true">
      <line x1={ball[0]} y1={ball[1]} x2={gx} y2={gy} />
      {shown.opponents.map(p => { const [x, y] = at(p); return <line key={p.id} x1={x} y1={y} x2={gx} y2={gy} /> })}
    </g>}
    {presser && (() => {
      const [x, y] = at(presser), dx = ball[0] - x, dy = ball[1] - y, length = Math.hypot(dx, dy)
      if (length < 2) return null
      const end = [x + (dx * (length - 1.4)) / length, y + (dy * (length - 1.4)) / length]
      return <g className="practice-press" aria-hidden="true"><line x1={x} y1={y} x2={end[0]} y2={end[1]} markerEnd="url(#practice-arrow)" />
        <text x={x} y={y + R + 1.6} textAnchor="middle" className="practice-tag">Press</text></g>
    })()}
    <defs><marker id="practice-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" className="practice-arrowhead" /></marker></defs>

    {shown.opponents.map(p => {
      const [x, y] = at(p)
      return <path key={p.id} d={`M${x},${y - R * 1.2} L${x + R * 1.1},${y + R * 0.8} L${x - R * 1.1},${y + R * 0.8} Z`} className="practice-opponent" />
    })}
    {shown.team.filter(p => p.id !== scenario.controlled).map(p => {
      const [x, y] = at(p)
      return <g key={p.id}><circle cx={x} cy={y} r={R} className="practice-teammate" />
        {p.id === 'gk' && <text x={x} y={y + 0.45} textAnchor="middle" className="practice-label">GK</text>}</g>
    })}
    {ghost && (() => { const [x, y] = at(ghost); return <g className="practice-ghost"><circle cx={x} cy={y} r={R * 1.2} />
      <text x={x} y={y + R + 1.8} textAnchor="middle" className="practice-tag">Best spot</text></g> })()}
    <circle cx={ball[0] + 0.7} cy={ball[1] - 0.5} r={0.6} className="practice-ball" />
    {(() => {
      const [x, y] = at(position)
      return <g className={`practice-you${disabled ? '' : ' movable'}`} tabIndex={disabled ? -1 : 0} role="button" onKeyDown={key}
        aria-label={`Your player, ${position.x.toFixed(1)} metres from your goal line. Arrow keys move them.`}>
        {/* A bigger, invisible circle makes an easy target for a finger. */}
        <circle cx={x} cy={y} r={R * 2.6} className="practice-target" />
        <circle cx={x} cy={y} r={R * 1.25} className="practice-you-dot" />
        <text x={x} y={y + 0.45} textAnchor="middle" className="practice-label">You</text>
      </g>
    })()}
  </svg>
}

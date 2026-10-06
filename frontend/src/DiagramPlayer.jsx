import { useEffect, useMemo, useRef, useState } from 'react'
import { buildTimeline, frameAt, stepArrows } from './diagramModel'

const TEAM_COLORS = { A: '#2a78d6', B: '#eb6834', N: '#6b7785' }
const LONG_SIDE_PX = 320
const PAD = 14

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Arrows stop short of the player or ball they point at, so the arrowhead is not hidden under it.
const ARROW_GAP = { run: 13, dribble: 13, pass: 7, shot: 2 }

// A wavy line for dribbles; straight for passes, shots and runs.
function arrowPath(arrow, k) {
  const [x1, y1] = [arrow.from[0] * k + PAD, arrow.from[1] * k + PAD]
  const [fx2, fy2] = [arrow.to[0] * k + PAD, arrow.to[1] * k + PAD]
  const full = Math.hypot(fx2 - x1, fy2 - y1) || 1
  const gap = Math.min(ARROW_GAP[arrow.kind] ?? 0, full * 0.4)
  const [x2, y2] = [fx2 - ((fx2 - x1) / full) * gap, fy2 - ((fy2 - y1) / full) * gap]
  if (arrow.kind !== 'dribble') return `M${x1} ${y1}L${x2} ${y2}`
  const length = Math.hypot(x2 - x1, y2 - y1)
  const waves = Math.max(2, Math.round(length / 12))
  const [ux, uy, nx, ny] = [(x2 - x1) / length, (y2 - y1) / length, -(y2 - y1) / length, (x2 - x1) / length]
  let d = `M${x1} ${y1}`
  for (let i = 1; i <= waves * 4; i++) {
    const along = (length * i) / (waves * 4)
    const side = [0, 3, 0, -3][i % 4]
    d += `L${x1 + ux * along + nx * side} ${y1 + uy * along + ny * side}`
  }
  return d
}

// Animated drill diagram: pitch, players, cones and ball, played step by step.
export default function DiagramPlayer({ diagram, caption }) {
  const timeline = useMemo(() => buildTimeline(diagram), [diagram])
  // Opens at the start of step 1, so the first Play animates it. Stepping with the arrows shows each step's end.
  const [index, setIndex] = useState(0)
  const [progress, setProgress] = useState(0)
  const [playing, setPlaying] = useState(false)
  const frame = useRef(null)
  const total = timeline.steps.length
  const { width, length } = diagram.pitch
  const k = LONG_SIDE_PX / Math.max(width, length)
  const W = width * k + PAD * 2, H = length * k + PAD * 2
  const px = point => [point[0] * k + PAD, point[1] * k + PAD]

  useEffect(() => {
    if (!playing) return
    const started = performance.now()
    const duration = timeline.steps[index].duration * 1000
    const tick = now => {
      const t = Math.min((now - started) / duration, 1)
      setProgress(t)
      if (t < 1) frame.current = requestAnimationFrame(tick)
      else if (index < total - 1) { setIndex(index + 1); setProgress(0) }
      else setPlaying(false)
    }
    frame.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame.current)
  }, [playing, index, total, timeline])

  const current = frameAt(timeline, index, progress)
  const play = () => {
    // With reduced motion, Play steps forward one position at a time instead of animating.
    if (reducedMotion()) {
      if (progress < 1) setProgress(1)
      else { setIndex(index === total - 1 ? 0 : index + 1); setProgress(1) }
      return
    }
    if (index === total - 1 && progress >= 1) { setIndex(0); setProgress(0) } else if (progress >= 1 && index < total - 1) { setIndex(index + 1); setProgress(0) }
    setPlaying(true)
  }
  const go = next => { setPlaying(false); setIndex(Math.min(Math.max(next, 0), total - 1)); setProgress(1) }

  return <figure className="diagram-player">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${caption || 'Drill diagram'}. Step ${index + 1} of ${total}: ${timeline.steps[index].label}`}>
      <defs>{['pass', 'shot', 'run', 'dribble'].map(kind => <marker key={kind} id={`arrow-${kind}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={kind === 'run' ? '#ffffff' : '#ffe08a'} /></marker>)}</defs>
      <rect x="0" y="0" width={W} height={H} rx="10" className="diagram-pitch" />
      <rect x={PAD} y={PAD} width={width * k} height={length * k} className="diagram-lines" />
      {(diagram.pitch.goals ?? []).map(goal => { const [gx, gy] = px(goal.at); const gw = (goal.width ?? 3) * k; return <rect key={goal.id} x={gx - gw / 2} y={gy - 4} width={gw} height="8" className="diagram-goal" /> })}
      {/* The current step's arrows, with the previous step's faded behind them for context. */}
      {[index - 1, index].filter(i => i >= 0).map(i => <g key={i} opacity={i === index ? 1 : 0.3}>{stepArrows(timeline, i).map((arrow, j) =>
        <path key={j} d={arrowPath(arrow, k)} className={`diagram-arrow diagram-arrow-${arrow.kind}`} markerEnd={`url(#arrow-${arrow.kind})`} />)}</g>)}
      {/* Cones and mannequins first, so players are never hidden underneath them. */}
      {Object.entries(diagram.objects).sort(([, a], [, b]) => (a.type === 'player') - (b.type === 'player')).map(([name, obj]) => {
        if (obj.type === 'ball') return null
        const [x, y] = px(current.positions[name])
        if (obj.type === 'cone') return <path key={name} d={`M${x} ${y - 6}L${x + 5} ${y + 4}L${x - 5} ${y + 4}Z`} className="diagram-cone" />
        if (obj.type === 'mannequin') return <rect key={name} x={x - 4} y={y - 9} width="8" height="18" rx="3" className="diagram-mannequin" />
        return <g key={name}><circle cx={x} cy={y} r="10" fill={TEAM_COLORS[obj.team] ?? TEAM_COLORS.N} className="diagram-player-dot" /><text x={x} y={y + 3.5} textAnchor="middle" className="diagram-player-label">{obj.label ?? name}</text></g>
      })}
      {current.ball && (() => { const [x, y] = px(current.ball); return <circle cx={x} cy={y} r="4.5" className="diagram-ball" /> })()}
    </svg>
    <figcaption>
      <div className="diagram-controls">
        <button type="button" onClick={() => go(index - 1)} disabled={index === 0} aria-label="Previous step">◀</button>
        <button type="button" onClick={() => (playing ? setPlaying(false) : play())}>{playing ? 'Pause' : index === total - 1 && progress >= 1 ? 'Replay' : 'Play'}</button>
        <button type="button" onClick={() => go(index + 1)} disabled={index === total - 1} aria-label="Next step">▶</button>
        <span className="muted">Step {index + 1} of {total}</span>
      </div>
      <p className="diagram-step" aria-live="polite">{timeline.steps[index].label}</p>
      {caption && <p className="muted diagram-caption">{caption}</p>}
    </figcaption>
  </figure>
}

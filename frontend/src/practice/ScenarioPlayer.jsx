import { useEffect, useRef, useState } from 'react'
import PracticePitch from './PracticePitch'
import { controlledIn, feedbackFor, idealPosition, scoreFrame, stars, startPosition } from './practiceModel'

const MOVE_MS = 450

const positionsOf = frame => ({ ball: frame.ball, team: frame.team, opponents: frame.opponents })
const lerp = (a, b, t) => ({ ...b, x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
// Everyone and the ball part-way from one frame to the next, matched by id.
function between(from, to, t) {
  const match = (list, other) => list.map(p => { const was = other.find(q => q.id === p.id); return was ? lerp(was, p, t) : p })
  return { ball: lerp(from.ball, to.ball, t), team: match(to.team, from.team), opponents: match(to.opponents, from.opponents) }
}
const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// One scenario, frame by frame: place your player, check, see why, then try again or go on. `onAttempt`, when given,
// hears every check (a coach's preview doesn't save them).
export default function ScenarioPlayer({ scenario, onAttempt, onDone, onExit }) {
  const [index, setIndex] = useState(0)
  const frame = scenario.frames[index]
  const [position, setPosition] = useState(() => startPosition(scenario, scenario.frames[0]))
  const [moved, setMoved] = useState(false)
  const [result, setResult] = useState(null)
  const [feedback, setFeedback] = useState(null)  // what to say about the last check, and whether to show the best spot
  const [tries, setTries] = useState(0)  // checks on this frame so far
  const [firstTries, setFirstTries] = useState([])  // points of each frame's first check
  const [shown, setShown] = useState(() => positionsOf(scenario.frames[0]))
  const [lines, setLines] = useState(frame.lines ?? scenario.lines ?? scenario.stage === 1)
  const [finished, setFinished] = useState(false)
  const started = useRef(0)  // when this try began, for how long it took
  const animation = useRef(null)
  useEffect(() => { started.current = Date.now(); return () => cancelAnimationFrame(animation.current) }, [])

  const move = point => { setPosition(point); setMoved(true) }
  const check = () => {
    const scored = scoreFrame(scenario, frame, position)
    const attempt = tries + 1
    const said = feedbackFor(frame, scored, attempt)
    setResult(scored)
    setFeedback(said)
    if (said.lines) setLines(true)
    setTries(attempt)
    if (attempt === 1) setFirstTries(previous => [...previous, scored.points])
    onAttempt?.({ scenario_id: scenario.id, frame_id: frame.id, attempt_no: attempt, x: round(position.x), y: round(position.y),
      points: scored.points, zone_hit: scored.zoneHit, failed_checks: scored.failed, duration_ms: Date.now() - started.current })
  }
  const again = () => { setResult(null); setFeedback(null); setMoved(false); started.current = Date.now() }
  const next = () => {
    const following = scenario.frames[index + 1]
    if (!following) { setFinished(true); onDone?.({ stars: stars(firstTries), firstTries }); return }
    const from = positionsOf(frame), to = positionsOf(following)
    setPosition(startPosition(scenario, following, position, frame))
    setIndex(index + 1)
    setResult(null)
    setFeedback(null)
    setMoved(false)
    setTries(0)
    if (following.lines != null) setLines(following.lines)
    started.current = Date.now()
    if (reducedMotion()) { setShown(to); return }
    const begin = performance.now()
    const step = now => {
      const t = Math.min(1, (now - begin) / MOVE_MS)
      setShown(between(from, to, t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2))
      if (t < 1) animation.current = requestAnimationFrame(step)
    }
    animation.current = requestAnimationFrame(step)
  }

  if (finished) {
    const earned = stars(firstTries)
    return <div className="practice-done" role="status">
      <p className="practice-stars" aria-label={`${earned} of 3 stars`}>{[1, 2, 3].map(n => <span key={n} className={n <= earned ? 'earned' : ''} aria-hidden="true">★</span>)}</p>
      <p>{earned === 3 ? 'Great positions all the way through.' : earned === 2 ? 'Good work. Try it again to get all three stars.' : 'Well done for finishing. Have another go!'}</p>
      <div className="practice-actions">
        <button type="button" className="secondary-btn" onClick={() => restart()}>Play again</button>
        {onExit && <button type="button" className="primary-btn" onClick={onExit}>Done</button>}
      </div>
    </div>
  }
  function restart() {
    setIndex(0); setPosition(startPosition(scenario, scenario.frames[0])); setMoved(false); setResult(null); setFeedback(null); setTries(0); setFirstTries([])
    setShown(positionsOf(scenario.frames[0])); setFinished(false); started.current = Date.now()
  }

  const last = index === scenario.frames.length - 1
  return <div className="practice-player">
    <div className="practice-head">
      {scenario.frames.length > 1 && <p className="practice-step">Step {index + 1} of {scenario.frames.length}</p>}
      <p className="practice-prompt">{frame.prompt}</p>
    </div>
    <PracticePitch scenario={scenario} controlled={controlledIn(scenario, frame)} shown={shown} position={position} onMove={move} disabled={Boolean(result)}
      ghost={feedback?.ghost ? idealPosition(frame) : null} lines={lines} />
    <label className="checkbox practice-lines"><input type="checkbox" checked={lines} onChange={e => setLines(e.target.checked)} /> Show lines to goal</label>
    {result
      ? <div className={`practice-feedback points-${result.points >= 100 ? 'best' : result.points > 0 ? 'some' : 'none'}`} role="status">
        <p className="practice-headline"><strong>{result.headline}</strong> <span>{result.points} points</span></p>
        <p>{feedback.message}</p>
        {/* Until the best spot is shown, trying again is the way on; moving on is there for anyone stuck. */}
        <div className="practice-actions">
          {result.points < 100 && !feedback.ghost
            ? <><button type="button" className="primary-btn" onClick={again}>Try again</button>
              <button type="button" className="link-btn" onClick={next}>{last ? 'Finish anyway' : 'Skip this step'}</button></>
            : <>{result.points < 100 && <button type="button" className="secondary-btn" onClick={again}>Try again</button>}
              <button type="button" className="primary-btn" onClick={next}>{last ? 'Finish' : 'Next'}</button></>}
        </div>
      </div>
      : <div className="practice-actions">
        <button type="button" className="primary-btn" disabled={!moved} onClick={check}>Check</button>
        {!moved && <span className="muted">Move your player first.</span>}
      </div>}
  </div>
}

const round = n => Math.round(n * 100) / 100

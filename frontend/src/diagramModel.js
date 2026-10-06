// Turns an animated drill diagram (pitch, objects, steps of actions) into positions over time.
// The server has already checked the diagram by replaying it, so this only computes.

export const STEP_SECONDS = 1.2
const BALL_OFFSET = [0.45, 0.35]  // metres: the ball sits just in front of the player who has it

const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
export const ease = t => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)

// Positions at the start of every step (and after the last), plus what moves during each step.
export function buildTimeline(diagram) {
  const goals = Object.fromEntries((diagram.pitch.goals ?? []).map(goal => [goal.id, goal]))
  const ballName = Object.keys(diagram.objects).find(name => diagram.objects[name].type === 'ball') ?? null
  const positions = {}
  for (const [name, obj] of Object.entries(diagram.objects)) if (obj.type !== 'ball') positions[name] = [...obj.at]
  let holder = ballName ? diagram.objects[ballName].with ?? null : null
  const near = name => [positions[name][0] + BALL_OFFSET[0], positions[name][1] + BALL_OFFSET[1]]
  let ball = ballName ? (holder ? near(holder) : [...diagram.objects[ballName].at]) : null

  const states = [{ positions: { ...positions }, ball, holder }]
  const steps = diagram.steps.map(step => {
    const moves = []
    const ends = {}
    for (const action of step.actions) {
      const [kind, spec] = Object.entries(action)[0]
      if (kind === 'run' || kind === 'move' || kind === 'dribble') ends[spec.who] = spec.to
    }
    for (const [name, to] of Object.entries(ends)) moves.push({ kind: step.actions.some(a => a.dribble?.who === name) ? 'dribble' : (step.actions.some(a => a.move?.who === name) ? 'move' : 'run'), who: name, from: positions[name], to: [...to] })
    let ballMove = null
    for (const action of step.actions) {
      const [kind, spec] = Object.entries(action)[0]
      if (kind === 'pass') {
        const target = ends[spec.to] ?? positions[spec.to]
        ballMove = { kind: 'pass', from: ball, to: [target[0] + BALL_OFFSET[0], target[1] + BALL_OFFSET[1]], receiver: spec.to }
      } else if (kind === 'shot') {
        ballMove = { kind: 'shot', from: ball, to: Array.isArray(spec.to) ? [...spec.to] : [...goals[spec.to].at], receiver: null }
      }
    }
    for (const [name, to] of Object.entries(ends)) positions[name] = [...to]
    if (ballMove) { holder = ballMove.receiver; ball = ballMove.to }
    else if (holder) ball = near(holder)
    states.push({ positions: { ...positions }, ball, holder })
    return { label: step.label, duration: step.duration ?? STEP_SECONDS, moves, ballMove }
  })
  return { states, steps }
}

// Where everything is during step `index` at progress `t` (0..1); index === steps.length means the end.
export function frameAt(timeline, index, t) {
  if (index >= timeline.steps.length) return timeline.states[timeline.steps.length]
  const start = timeline.states[index], end = timeline.states[index + 1], step = timeline.steps[index]
  const k = ease(Math.min(Math.max(t, 0), 1))
  const positions = { ...start.positions }
  for (const move of step.moves) positions[move.who] = lerp(move.from, move.to, k)
  let ball = start.ball
  if (step.ballMove) ball = lerp(step.ballMove.from, step.ballMove.to, k)
  else if (start.holder && end.ball) ball = lerp(start.ball, end.ball, k)
  return { positions, ball }
}

// Arrow paths for one step, in metres: passes and shots for the ball, runs and dribbles for players.
export function stepArrows(timeline, index) {
  const step = timeline.steps[index]
  const arrows = step.moves.filter(m => m.kind !== 'move').map(m => ({ kind: m.kind, from: m.from, to: m.to }))
  if (step.ballMove) arrows.push({ kind: step.ballMove.kind, from: step.ballMove.from, to: step.ballMove.to })
  return arrows
}

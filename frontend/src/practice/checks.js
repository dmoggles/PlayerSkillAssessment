// Diagnostic checks: why a position isn't quite right, whatever zone it's in. Each takes the player's position and
// the frame, and says whether it passes (null when it doesn't apply to this frame) with a reason. A frame lists the
// checks that apply to it in target.checks; when the position misses the best zone, the first failing check by
// priority gives the hint. A new topic adds its checks here, and lists them in backend/app/practice.py's TOPICS.
import { angleAt, distance, distanceToLine, goalOf, sideOf } from './geometry'

const opponent = (frame, id) => frame.opponents.find(p => p.id === id)
const presser = frame => frame.team.find(p => p.action === 'PRESS')
const result = (pass, reason = null) => ({ pass, reason })

export const CHECKS = {
  GOAL_SIDE: {
    priority: 1,
    label: 'Not goal-side',
    messages: { not_goal_side: 'Get between your attacker and the goal.' },
    run(position, frame, { pitch, thresholds }) {
      const attacker = opponent(frame, frame.mark), goal = goalOf(pitch)
      const closer = distance(position, goal) < distance(attacker, goal)
      return result(closer && angleAt(attacker, goal, position) <= thresholds.goalSideAngle, 'not_goal_side')
    },
  },
  BALL_SIDE: {
    priority: 2,
    label: 'Not ball-side',
    messages: { not_ball_side: 'Shift a little towards the side the ball is on.' },
    run(position, frame, { pitch, thresholds }) {
      const attacker = opponent(frame, frame.mark), goal = goalOf(pitch)
      // With the ball on the line from the attacker to goal (or at their feet), neither side is the ball side.
      if (distanceToLine(attacker, goal, frame.ball) < thresholds.lineTolerance) return result(null)
      return result(sideOf(attacker, goal, position) === sideOf(attacker, goal, frame.ball), 'not_ball_side')
    },
  },
  DISTANCE_TIGHT: {
    priority: 3,
    label: 'Too far off',
    messages: { too_far: 'The ball is near your attacker. Get closer to them.' },
    run(position, frame, { thresholds }) {
      const attacker = opponent(frame, frame.mark)
      if (distance(frame.ball, attacker) > thresholds.tightBallRange) return result(null)
      return result(distance(position, attacker) <= thresholds.tightDistance, 'too_far')
    },
  },
  DISTANCE_DROP: {
    priority: 3,
    label: 'Too tight',
    messages: { too_close: 'The ball is far away. Drop off so you can see ball and attacker.' },
    run(position, frame, { thresholds }) {
      const attacker = opponent(frame, frame.mark)
      if (distance(frame.ball, attacker) < thresholds.dropBallRange) return result(null)
      return result(distance(position, attacker) >= thresholds.dropDistance, 'too_close')
    },
  },
  BEHIND_PRESSER: {
    priority: 4,
    label: 'Not covering the presser',
    messages: {
      not_behind: 'Stay behind your partner, between the ball and the goal.',
      too_close: 'Give your partner a little room. Drop a few steps behind.',
      too_far: 'Come closer behind your partner, so you can help.',
    },
    run(position, frame, { pitch, thresholds }) {
      const partner = presser(frame), goal = goalOf(pitch), gap = distance(position, partner)
      if (distance(position, goal) >= distance(partner, goal) || angleAt(partner, goal, position) > thresholds.coverAngle) return result(false, 'not_behind')
      if (gap < thresholds.coverBackMin) return result(false, 'too_close')
      if (gap > thresholds.coverBackMax) return result(false, 'too_far')
      return result(true)
    },
  },
  NEAREST_THREAT: {
    priority: 5,
    label: 'Marking the wrong attacker',
    messages: { wrong_player: 'Pick up the most dangerous attacker nobody is marking.' },
    run(position, frame) {
      const threat = opponent(frame, frame.mark)
      const others = frame.opponents.filter(p => p.id !== frame.mark)
      return result(others.every(p => distance(position, threat) < distance(position, p)), 'wrong_player')
    },
  },
}

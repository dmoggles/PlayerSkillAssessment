// Diagnostic checks: why a position isn't quite right, whatever zone it's in. Each takes the player's position and
// the frame, and says whether it passes (null when it doesn't apply to this frame) with a reason. A frame lists the
// checks that apply to it in target.checks; when the position misses the best zone, the first failing check by
// priority gives the clue. A new topic adds its checks here, and lists them in backend/app/practice.py's TOPICS.
//
// Each reason has two clues: first a question that gets the player thinking about the idea, then, if they miss
// again, a plainer pointer to what to change. The best spot itself is only shown after that (see feedbackFor).
import { angleAt, distance, distanceToLine, goalOf, sideOf } from './geometry'

const opponent = (frame, id) => frame.opponents.find(p => p.id === id)
const presser = frame => frame.team.find(p => p.action === 'PRESS')
const result = (pass, reason = null) => ({ pass, reason })

export const CHECKS = {
  NEAREST_THREAT: {
    // Nobody is told which attacker is theirs, so picking the right one comes first.
    priority: 0,
    label: 'Marking the wrong attacker',
    clues: { wrong_player: ['Look around: which attacker has nobody near them?', 'Pick up the free attacker nearest the ball and your goal.'] },
    run(position, frame) {
      const threat = opponent(frame, frame.mark)
      const others = frame.opponents.filter(p => p.id !== frame.mark)
      return result(others.every(p => distance(position, threat) < distance(position, p)), 'wrong_player')
    },
  },
  KEEP_IN_FRONT: {
    // Outnumbered: goal-side of every attacker who matters (the frame's threats), so none can get in behind.
    priority: 0.5,
    label: 'Let an attacker get behind',
    clues: {
      behind_you: ['Can you see both attackers without turning your head?', 'Drop back until both attackers are in front of you.'],
      too_deep: ['If they get the ball, could you get out to them in time?', 'Step up a little: stay close enough to reach either attacker.'],
    },
    run(position, frame, { pitch, thresholds }) {
      const goal = goalOf(pitch), threats = frame.threats.map(id => opponent(frame, id))
      const inFront = threats.every(a => distance(position, goal) < distance(a, goal) && angleAt(a, goal, position) <= thresholds.goalSideAngle)
      if (!inFront) return result(false, 'behind_you')
      return result(Math.min(...threats.map(a => distance(position, a))) <= thresholds.keepInFrontReach, 'too_deep')
    },
  },
  GOAL_SIDE: {
    priority: 1,
    label: 'Not goal-side',
    clues: { not_goal_side: ['If they got the ball now, could they run straight at goal?', 'Stand on the line from the attacker to the middle of your goal.'] },
    run(position, frame, { pitch, thresholds }) {
      const attacker = opponent(frame, frame.mark), goal = goalOf(pitch)
      const closer = distance(position, goal) < distance(attacker, goal)
      return result(closer && angleAt(attacker, goal, position) <= thresholds.goalSideAngle, 'not_goal_side')
    },
  },
  BALL_SIDE: {
    priority: 2,
    label: 'Not ball-side',
    clues: { not_ball_side: ['Which side would a pass to the attacker come from?', 'Take a step off their line to goal, towards the ball.'] },
    run(position, frame, { pitch, thresholds }) {
      const attacker = opponent(frame, frame.mark), goal = goalOf(pitch)
      // With the ball on the line from the attacker to goal (or at their feet), neither side is the ball side.
      if (distanceToLine(attacker, goal, frame.ball) < thresholds.lineTolerance) return result(null)
      return result(sideOf(attacker, goal, position) === sideOf(attacker, goal, frame.ball), 'not_ball_side')
    },
  },
  DISTANCE_TIGHT: {
    priority: 3,
    label: 'Wrong distance with the ball near',
    clues: {
      too_far: ['The ball is close to the attacker. Could you stop them turning?', 'Get closer: about three big steps from them.'],
      too_close: ['Could they spin round you from there?', 'Give yourself room: about three big steps away, still goal-side.'],
    },
    run(position, frame, { thresholds }) {
      const attacker = opponent(frame, frame.mark)
      if (distance(frame.ball, attacker) > thresholds.tightBallRange) return result(null)
      const gap = distance(position, attacker)
      if (gap < thresholds.tightMin) return result(false, 'too_close')
      return result(gap <= thresholds.tightDistance, 'too_far')
    },
  },
  DISTANCE_DROP: {
    priority: 3,
    label: 'Too tight',
    clues: { too_close: ['The ball is far away. Can you see it and the attacker together?', 'Drop off a few steps, so a ball over the top can\'t beat you.'] },
    run(position, frame, { thresholds }) {
      const attacker = opponent(frame, frame.mark)
      if (distance(frame.ball, attacker) < thresholds.dropBallRange) return result(null)
      return result(distance(position, attacker) >= thresholds.dropDistance, 'too_close')
    },
  },
  BEHIND_PRESSER: {
    priority: 4,
    label: 'Not covering the presser',
    clues: {
      not_behind: ['If your partner gets beaten, who stops the attacker next?', 'Stand behind your partner, between them and the goal.'],
      too_close: ['If you\'re right next to your partner, could one dribble beat you both?', 'Drop a few steps behind your partner.'],
      too_far: ['If your partner gets beaten, could you get there in time?', 'Come closer: a few steps behind your partner.'],
    },
    run(position, frame, { pitch, thresholds }) {
      const partner = presser(frame), goal = goalOf(pitch), gap = distance(position, partner)
      if (distance(position, goal) >= distance(partner, goal) || angleAt(partner, goal, position) > thresholds.coverAngle) return result(false, 'not_behind')
      if (gap < thresholds.coverBackMin) return result(false, 'too_close')
      if (gap > thresholds.coverBackMax) return result(false, 'too_far')
      return result(true)
    },
  },
}

// Checks that are about the line from the attacker to goal: the lines to goal help with these.
export const LINE_CHECKS = new Set(['GOAL_SIDE', 'BALL_SIDE'])

// The numbers behind the diagnostic checks, in metres and degrees. They're starting points for coaches to review:
// change one here and every scenario uses it, or give a scenario its own in its `thresholds` (for example, wider
// distances on an 11v11 pitch). backend/app/practice.py lists the names a scenario may override.
export const THRESHOLDS = {
  // Goal-side: closer to our goal than your attacker, and within this angle of the line from them to the goal.
  goalSideAngle: 35,
  // A ball or player this close to a line counts as on it, so neither side.
  lineTolerance: 1,
  // When the ball is this close to your attacker, be within tightDistance of them.
  tightBallRange: 8,
  tightDistance: 3,
  // When the ball is this far from your attacker, drop at least dropDistance off them, to see ball and attacker.
  dropBallRange: 20,
  dropDistance: 4,
  // Covering a teammate who presses: this far behind them, and within this angle of the line from them to the goal.
  coverBackMin: 3,
  coverBackMax: 7,
  coverAngle: 60,
}

export const thresholdsFor = scenario => ({ ...THRESHOLDS, ...(scenario?.thresholds ?? {}) })

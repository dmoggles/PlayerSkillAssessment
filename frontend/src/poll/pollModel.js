// Coaching polls: who's answering (a random id this browser keeps, so they can come back and change answers), and
// how a poll's answers group around its reference spots for the admin's view.

const key = pollId => `poll:${pollId}:respondent`

// This browser's id for a poll, made the first time. Without storage (a private window), answers still save, but
// coming back starts afresh.
export function respondentFor(pollId, storage = globalThis.localStorage) {
  try {
    const kept = storage?.getItem(key(pollId))
    if (kept) return kept
  } catch { /* storage blocked */ }
  const made = globalThis.crypto?.randomUUID?.() ?? `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`
  try { storage?.setItem(key(pollId), made) } catch { /* storage blocked */ }
  return made
}

export const NEAR = 6  // metres: an answer further than this from every reference spot is "Somewhere else"
export const ELSEWHERE = 'Somewhere else'

// Which reference spot an answer is nearest, if any is near enough.
export function groupOf(answer, spots, near = NEAR) {
  let best = null, gap = Infinity
  for (const s of spots) {
    const d = Math.hypot(answer.x - s.x, answer.y - s.y)
    if (d < gap) { best = s.label; gap = d }
  }
  return gap <= near ? best : ELSEWHERE
}

// How many answers to a situation fall in each group, in the spots' order, with any elsewhere last.
export function tally(answers, spots) {
  const counts = Object.fromEntries([...spots.map(s => [s.label, 0]), [ELSEWHERE, 0]])
  for (const a of answers) counts[groupOf(a, spots)] += 1
  return Object.entries(counts).filter(([label, n]) => n > 0 || label !== ELSEWHERE).map(([label, n]) => ({ label, n }))
}

// What to call a respondent: their name, or a short form of their id.
export const respondentName = r => r.name || `Anonymous ${r.id.slice(0, 4)}`

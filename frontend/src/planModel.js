// Shapes a development plan from the server for display: one card per priority, with its club and home drills
// and any gaps, and each drill's weeks folded into runs ("Weeks 1–2: Base").

export function planByPriority(plan) {
  const byRank = new Map()
  const entry = item => {
    if (!byRank.has(item.rank)) byRank.set(item.rank, { rank: item.rank, skillId: item.skill_id, label: item.label, club: null, home: null, gaps: [] })
    return byRank.get(item.rank)
  }
  for (const slot of plan.slots) entry(slot)[slot.slot] = slot
  for (const gap of plan.gaps) entry(gap).gaps.push(gap)
  return [...byRank.values()].sort((a, b) => a.rank - b.rank)
}

export function weekRuns(weeks) {
  const runs = []
  weeks.forEach((variation, i) => {
    const last = runs.at(-1)
    if (last && last.variation.id === variation.id) last.to = i + 1
    else runs.push({ from: i + 1, to: i + 1, variation })
  })
  return runs.map(run => ({ ...run, label: run.from === run.to ? `Week ${run.from}` : `Weeks ${run.from}–${run.to}` }))
}

// A saved plan is out of date once the priorities differ from the ones it was made for (order matters).
export const planIsStale = (saved, skills) => Boolean(saved?.plan) && saved.skills.join(',') !== skills.join(',')

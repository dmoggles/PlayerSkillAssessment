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

const longDay = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

// One line on the shared link: not shared, expired, or when it was made, expires and was opened.
export function planShareSummary(share) {
  if (!share) return 'Not shared. A link lets the player or a parent see this plan and its drills without signing in, until a week after the plan ends.'
  if (share.expired) return `The link expired on ${longDay(share.expires_at)}. Create a new one to share again.`
  return [`Shared ${longDay(share.created_at)}`, `expires ${longDay(share.expires_at)}`, share.opened_at ? `opened ${longDay(share.opened_at)}` : 'not opened yet'].join(' · ')
}

// The shared copy is frozen; it is out of date once the priorities differ from the ones it was made for.
export const shareIsStale = (share, skills) => Boolean(share && !share.expired) && share.skills.join(',') !== skills.join(',')

export const columnsByScore = (columns, skillId, valueFor) => [...columns].sort((a, b) => {
  const aScore = valueFor(skillId, a.key)
  const bScore = valueFor(skillId, b.key)
  if (aScore == null) return bScore == null ? 0 : 1
  if (bScore == null) return -1
  return aScore - bScore
})

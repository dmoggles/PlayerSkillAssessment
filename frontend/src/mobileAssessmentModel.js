export const ratedCount = (section, ratings) => section.skills.filter(skill => typeof ratings[skill.id] === 'number').length

export function horizontalSwipe(start, end) {
  if (!start || !end) return 0
  const dx = end.x - start.x
  const dy = end.y - start.y
  if (Math.abs(dx) < 56 || Math.abs(dx) <= Math.abs(dy) * 1.5) return 0
  return dx < 0 ? 1 : -1
}

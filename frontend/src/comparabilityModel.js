// When periods are rated on different skill matrix versions, some comparisons stop being like for like.
// History rows carry skill_changes: how each skill changed since the previous row's matrix version.

// Changes that make a skill's scores before and after not directly comparable.
export const RATING_CHANGES = ['reworded', 'added', 'retired']
// Changes that also affect a section (skill area) average.
export const SECTION_CHANGES = [...RATING_CHANGES, 'moved']
export const CHANGE_LABELS = { reworded: 'wording changed', added: 'new skill', retired: 'retired', moved: 'moved to another area', retagged: 'tags changed' }

// All skill changes in rows after fromIndex up to and including toIndex (indexes into history).
export function changesBetween(history, fromIndex, toIndex) {
  const changes = {}
  for (let i = fromIndex + 1; i <= toIndex; i++) Object.assign(changes, history[i]?.skill_changes ?? {})
  return changes
}

// Skill names across every version in the history (latest name wins), falling back to the current matrix.
export function historyLabels(history, matrix) {
  const labels = Object.fromEntries((matrix?.sections ?? []).flatMap(section => section.skills.map(skill => [skill.id, skill.label])))
  for (const row of history) Object.assign(labels, row.skill_labels ?? {})
  return labels
}

// Section ids whose average is affected by these changes.
export function changedSections(changes, history) {
  const sectionOf = Object.assign({}, ...history.map(row => row.skill_sections ?? {}))
  return new Set(Object.entries(changes).filter(([, kind]) => SECTION_CHANGES.includes(kind)).map(([skillId]) => sectionOf[skillId]).filter(Boolean))
}

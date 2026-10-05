// Pure helpers for editing a skill matrix draft. Every function returns a new document.
// New sections and skills carry a temporary _key until the server gives them a permanent id.

export const OUTFIELD = ['defender', 'midfielder', 'winger', 'striker']
export const GOALKEEPER = ['goalkeeper']
export const LEVELS = ['1', '3', '5']
export const IMPORTANCE = [['HIGH', 'High'], ['MED', 'Medium'], ['LOW', 'Low']]
export const TAG_WEIGHTS = [[1, 'Main'], [0.5, 'Partial']]
export const CHANGE_GROUPS = [
  ['breaking', 'Breaks comparison', 'Ratings before and after cannot be compared for these skills.'],
  ['wording', 'Wording', 'Ratings before and after are no longer directly comparable.'],
  ['suggestions', 'Suggestions only', 'Only future priority suggestions change.'],
  ['addition', 'Additions', 'Safe: nothing existing changes.'],
  ['layout', 'Layout', 'Order and section names only.'],
]

let counter = 0
const tempKey = () => `new-${Date.now().toString(36)}-${(counter++).toString(36)}`
// Stable key for list items and selection: new items keep their _key even after the server assigns an id.
export const keyOf = item => item._key ?? item.id
export const isGoalkeeperSection = section => section.applies_to.length === 1 && section.applies_to[0] === 'goalkeeper'
const sameType = (a, b) => isGoalkeeperSection(a) === isGoalkeeperSection(b)

export function findSkill(doc, key) {
  for (const section of doc.sections) {
    const skill = section.skills.find(s => keyOf(s) === key)
    if (skill) return { skill, section }
  }
  return null
}

const mapSections = (doc, fn) => ({ ...doc, sections: doc.sections.map(fn) })
const mapSkill = (doc, key, fn) => mapSections(doc, section => ({ ...section, skills: section.skills.map(s => keyOf(s) === key ? fn(s) : s) }))
const move = (list, index, direction) => {
  const target = index + direction
  if (index < 0 || target < 0 || target >= list.length) return list
  const next = [...list]
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}

export function addSection(doc, kind) {
  const section = { _key: tempKey(), id: null, label: kind === 'goalkeeper' ? 'New goalkeeper section' : 'New section', applies_to: kind === 'goalkeeper' ? GOALKEEPER : OUTFIELD, skills: [] }
  return [{ ...doc, sections: [...doc.sections, section] }, section._key]
}

export const renameSection = (doc, key, label) => mapSections(doc, s => keyOf(s) === key ? { ...s, label } : s)
export const moveSection = (doc, key, direction) => ({ ...doc, sections: move(doc.sections, doc.sections.findIndex(s => keyOf(s) === key), direction) })
// Only empty sections can be removed; retiring skills is a separate, deliberate step.
export const removeSection = (doc, key) => ({ ...doc, sections: doc.sections.filter(s => keyOf(s) !== key || s.skills.length) })

export function addSkill(doc, sectionKey) {
  const positions = doc.positions.map(p => p.id)
  let created = null
  const next = mapSections(doc, section => {
    if (keyOf(section) !== sectionKey) return section
    const ids = isGoalkeeperSection(section) ? GOALKEEPER : positions
    created = { _key: tempKey(), id: null, label: 'New skill', descriptors: { 1: '', 3: '', 5: '' }, position_weights: Object.fromEntries(ids.map(p => [p, 'MED'])), is_dependency_root: false, tags: {} }
    return { ...section, skills: [...section.skills, created] }
  })
  return [next, created?._key ?? null]
}

export const updateSkill = (doc, key, patch) => mapSkill(doc, key, skill => ({ ...skill, ...patch }))
export const setDescriptor = (doc, key, level, text) => mapSkill(doc, key, skill => ({ ...skill, descriptors: { ...skill.descriptors, [level]: text } }))
export const setImportance = (doc, key, position, value) => mapSkill(doc, key, skill => ({ ...skill, position_weights: { ...skill.position_weights, [position]: value } }))

export function setTag(doc, key, tagId, weight) {
  return mapSkill(doc, key, skill => {
    const tags = { ...skill.tags }
    if (weight == null) delete tags[tagId]
    else tags[tagId] = weight
    return { ...skill, tags }
  })
}

export function moveSkill(doc, key, direction) {
  return mapSections(doc, section => {
    const index = section.skills.findIndex(s => keyOf(s) === key)
    return index < 0 ? section : { ...section, skills: move(section.skills, index, direction) }
  })
}

export function moveSkillToSection(doc, key, sectionKey) {
  const found = findSkill(doc, key)
  const target = doc.sections.find(s => keyOf(s) === sectionKey)
  if (!found || !target || keyOf(found.section) === sectionKey || !sameType(found.section, target)) return doc
  return mapSections(doc, section => {
    if (section === found.section) return { ...section, skills: section.skills.filter(s => keyOf(s) !== key) }
    if (keyOf(section) === sectionKey) return { ...section, skills: [...section.skills, found.skill] }
    return section
  })
}

// Removes a skill (retiring it if it was published) and every dependency that mentions it.
export function removeSkill(doc, key) {
  const id = findSkill(doc, key)?.skill.id
  const next = mapSections(doc, section => ({ ...section, skills: section.skills.filter(s => keyOf(s) !== key) }))
  if (!id) return next
  const dependencyMap = Object.fromEntries(Object.entries(doc.dependency_map ?? {})
    .filter(([root]) => root !== id).map(([root, targets]) => [root, targets.filter(t => t !== id)]))
  return { ...next, dependency_map: dependencyMap }
}

// "Foundation for": if any of these skills is weak, this skill gets a priority boost.
export function setFoundationFor(doc, rootId, targetIds) {
  const dependencyMap = { ...(doc.dependency_map ?? {}) }
  if (targetIds.length) dependencyMap[rootId] = targetIds
  else delete dependencyMap[rootId]
  return { ...doc, dependency_map: dependencyMap }
}

// After an autosave, give locally-new items the ids the server assigned (matched by _key).
export function adoptServerIds(local, server) {
  const assigned = new Map()
  for (const section of server.sections) for (const item of [section, ...section.skills]) if (item._key && item.id) assigned.set(item._key, item.id)
  const withId = item => (!item.id && assigned.has(item._key) ? { ...item, id: assigned.get(item._key) } : item)
  return mapSections(local, section => ({ ...withId(section), skills: section.skills.map(withId) }))
}

const PLACEHOLDER = /\{(?:[Tt]hey|[Tt]hem|[Tt]heir|[Tt]heirs|[Tt]hemself|[^{}|]+\|[^{}|]+)\}/g
const LITERAL_PRONOUN = /\b(she|her|hers|herself|he|him|his|himself|they|them|their|theirs|themselves|themself|they're|she's|he's)\b/gi
// Pronouns typed as plain words, which would not follow the team's Players setting.
export const literalPronouns = text => [...new Set((text.replace(PLACEHOLDER, '').match(LITERAL_PRONOUN) ?? []).map(w => w.toLowerCase()))]

export const changeCount = changes => Object.values(changes ?? {}).reduce((total, items) => total + items.length, 0)

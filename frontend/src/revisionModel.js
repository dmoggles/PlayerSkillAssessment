// Describes what each saved coach-assessment version changed, by comparing its
// snapshot with the previous version's snapshot.
import { POSITION_LABELS, FREQUENCIES, norm } from './matrix'

const positionLabel = id => POSITION_LABELS[norm(id)] ?? id
const frequencyLabel = id => FREQUENCIES.find(f => f.id === id)?.label.toLowerCase() ?? id
const secondaryLabel = snapshot => snapshot.secondary_position
  ? `${positionLabel(snapshot.secondary_position)}${snapshot.secondary_position_frequency ? ` (${frequencyLabel(snapshot.secondary_position_frequency)})` : ''}`
  : 'None'
const scores = snapshot => Object.fromEntries((snapshot.ratings ?? []).map(r => [r.skill_id, r.score]))
const shown = score => score ?? '—'

export const skillLabels = matrix => Object.fromEntries(matrix.sections.flatMap(section => section.skills.map(skill => [skill.id, skill.label])))

export function revisionChanges(previous, current, labels = {}) {
  if (!previous) {
    const rated = (current.ratings ?? []).filter(r => r.score != null).length
    return [`Created as ${positionLabel(current.primary_position)} with ${rated} ${rated === 1 ? 'skill' : 'skills'} rated`]
  }
  const changes = []
  if (norm(previous.primary_position) !== norm(current.primary_position)) changes.push(`Primary position: ${positionLabel(previous.primary_position)} → ${positionLabel(current.primary_position)}`)
  if (secondaryLabel(previous) !== secondaryLabel(current)) changes.push(`Secondary position: ${secondaryLabel(previous)} → ${secondaryLabel(current)}`)
  const before = scores(previous)
  const after = scores(current)
  const ids = [...Object.keys(after), ...Object.keys(before).filter(id => !(id in after))]
  for (const id of ids) {
    if ((before[id] ?? null) !== (after[id] ?? null)) changes.push(`${labels[id] ?? id}: ${shown(before[id])} → ${shown(after[id])}`)
  }
  return changes
}

// Newest first, each with the list of changes from the version before it.
export function revisionTimeline(revisions, labels = {}) {
  const ordered = [...revisions].sort((a, b) => a.version - b.version)
  return ordered.map((revision, i) => ({ ...revision, changes: revisionChanges(ordered[i - 1]?.snapshot, revision.snapshot, labels) })).reverse()
}

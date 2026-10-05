// Shapes the squad insights payload for the Team Data tabs.
import { POSITION_LABELS } from './matrix'

// Categorical slots in fixed order (validated palette); a section keeps its colour wherever it appears.
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
export const AREA_LABELS = { technical: 'Technical', tactical: 'Tactical', mental: 'Mental', goalkeeping: 'Goalkeeping', physical: 'Physical' }
export const AREA_ORDER = Object.keys(AREA_LABELS)

export const fmt = value => (value == null ? '—' : value.toFixed(1))
export const positionLabel = id => POSITION_LABELS[id] ?? id
// Players holding a priority, highest priority (rank 1) first, then by name.
export const sortByRank = players => [...players].sort((a, b) => a.rank - b.rank || a.player.localeCompare(b.player))
export const SHOWN_PLAYERS = 4

// "12 players (5 as #1)"
export function priorityCount(players) {
  const first = players.filter(p => p.rank === 1).length
  return `${players.length} ${players.length === 1 ? 'player' : 'players'}${first && players.length > 1 ? ` (${first} as #1)` : ''}`
}

export const POSITION_FILTERS = [['', 'All positions'], ['goalkeeper', 'Goalkeepers'], ['defender', 'Defenders'], ['midfielder', 'Midfielders'], ['winger', 'Wingers'], ['striker', 'Strikers']]
export const groupName = position => (POSITION_FILTERS.find(([id]) => id === position)?.[1] ?? 'players').toLowerCase()

// One series per section, in order of first appearance, each with a value (or null) per period.
export function sectionSeries(insights) {
  const ids = []
  for (const period of insights.trend) for (const id of Object.keys(period.sections)) if (!ids.includes(id)) ids.push(id)
  return ids.map((id, i) => ({
    id,
    label: insights.section_labels[id] ?? id,
    color: SERIES_COLORS[Math.min(i, SERIES_COLORS.length - 1)],
    values: insights.trend.map(period => period.sections[id]?.average ?? null),
    changed: insights.trend.map(period => period.changed_sections.includes(id)),
  }))
}

// Tags that appear in any period, grouped by area then sorted by name.
export function tagRows(insights, valuesFor) {
  return Object.keys(insights.tags)
    .map(id => ({ id, ...insights.tags[id], values: valuesFor(id) }))
    .filter(row => row.values.some(v => v != null))
    .sort((a, b) => AREA_ORDER.indexOf(a.area) - AREA_ORDER.indexOf(b.area) || a.label.localeCompare(b.label))
}

export const tagTrendRows = insights => tagRows(insights, id => insights.trend.map(period => period.tags[id]?.average ?? null))
export const tagPositionRows = (insights, positions) => tagRows(insights, id => positions.map(group => group.tags[id]?.average ?? null))

const LABEL_GAP = 13

// Direct labels at line ends, nudged apart vertically so equal end values do not overprint.
export function placeEndLabels(ends, top, bottom) {
  const placed = [...ends].sort((a, b) => a.y - b.y)
  placed.forEach((label, i) => { label.labelY = Math.max(label.y, i ? placed[i - 1].labelY + LABEL_GAP : top) })
  const overflow = placed.length ? placed[placed.length - 1].labelY - bottom : 0
  if (overflow > 0) placed.forEach(label => { label.labelY -= overflow })
  return placed
}

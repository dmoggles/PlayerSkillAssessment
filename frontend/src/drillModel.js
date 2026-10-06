// Labels and small formatting helpers for drills.
export const FORMAT_LABELS = { individual: 'Individual', small_group: 'Small group', unit: 'Unit', team: 'Whole team' }
export const PHASE_LABELS = { warm_up: 'Warm-up', technical: 'Technical', opposed: 'Opposed', small_sided_game: 'Small-sided game', cool_down: 'Cool-down' }
export const levelRange = ([min, max]) => (min === max ? `Level ${min}` : `Levels ${min}–${max}`)
export const playersText = ([min, , max]) => (min === max ? `${min} ${min === 1 ? 'player' : 'players'}` : `${min}–${max} players`)

// Privacy-enhanced embed URL for a YouTube or Vimeo link (null for anything else).
export function videoEmbedUrl(url, start) {
  try {
    const u = new URL(url)
    const path = u.pathname.split('/').filter(Boolean)
    const id = u.hostname === 'youtu.be' ? path[0]
      : u.hostname.endsWith('youtube.com') ? (['shorts', 'embed', 'live'].includes(path[0]) ? path[1] : u.searchParams.get('v'))
      : null
    if (id) return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?autoplay=1${start ? `&start=${start}` : ''}`
    const vimeo = u.hostname.endsWith('vimeo.com') ? u.pathname.split('/').filter(Boolean).pop() : null
    if (vimeo && /^\d+$/.test(vimeo)) return `https://player.vimeo.com/video/${vimeo}?autoplay=1&dnt=1${start ? `#t=${start}s` : ''}`
  } catch { /* not a valid URL */ }
  return null
}

// The diagram for a variation: its own if it has one. Otherwise work outward from the base version:
// an escalator inherits from the variation below it, a regression from the one above it, and the base
// uses the drill's first diagram.
export function variationDiagram(drill, variation) {
  const diagrams = drill.media.filter(m => m.kind === 'diagram')
  const byId = id => diagrams.find(m => m.id === id)
  let index = drill.variations.findIndex(v => v.id === variation?.id)
  while (index >= 0 && index < drill.variations.length) {
    const current = drill.variations[index]
    if (byId(current.diagram_media_id)) return byId(current.diagram_media_id)
    if (current.kind === 'escalator') index -= 1
    else if (current.kind === 'regression') index += 1
    else break
  }
  return diagrams[0] ?? null
}

const OVERRIDABLE = ['setup', 'equipment', 'instructions', 'coaching_points', 'players', 'space']

// What a coach sees for a chosen variation: its overrides where it has them, the drill's own content otherwise.
// `changed` lists the fields that differ from the drill, so the view can label them.
export function effectiveDrill(drill, variation) {
  const effective = { changed: new Set() }
  for (const field of OVERRIDABLE) {
    const override = variation?.[field]
    effective[field] = override ?? drill[field]
    if (override != null && JSON.stringify(override) !== JSON.stringify(drill[field])) effective.changed.add(field)
  }
  return effective
}

// YouTube Shorts are vertical, so they get a portrait frame.
export const isVerticalVideo = url => { try { return new URL(url).pathname.startsWith('/shorts/') } catch { return false } }

// Videos to show for a variation: its own video first (flagged), then drill-wide videos that no variation claims.
export function visibleVideos(drill, variation) {
  const videos = drill.media.filter(m => m.kind === 'video')
  const claimed = new Set(drill.variations.map(v => v.video_media_id).filter(Boolean))
  const own = videos.find(m => m.id === variation?.video_media_id)
  return [...(own ? [{ ...own, forVariation: true }] : []), ...videos.filter(m => !claimed.has(m.id))]
}

export const AREA_LABELS = { technical: 'Technical', tactical: 'Tactical', mental: 'Mental', goalkeeping: 'Goalkeeping', physical: 'Physical' }
export const INTENSITY_LABELS = { low: 'Low', medium: 'Medium', high: 'High' }
export const DISLIKE_REASONS = { too_advanced: 'Too advanced', too_easy: 'Too easy', unclear: 'Unclear', equipment_or_space: 'Needs equipment or space we lack', did_not_work: 'Did not work in practice', other: 'Other' }
export const equipmentLabel = item => item.replace('_', ' ')

// Empty values mean "any". Numbers are kept as strings, as the inputs give them.
export const EMPTY_FILTERS = { text: '', area: '', tag: '', format: '', players: '', age: '', level: '', duration: '', intensity: '', equipment: [], home: false, liked: false }

export const activeFilterCount = filters => Object.entries(filters)
  .filter(([key, value]) => key !== 'text' && (Array.isArray(value) ? value.length : value)).length

// The tags and equipment that appear in the library, for the filter choices.
export function filterOptions(drills) {
  const tags = new Map()
  const equipment = new Set()
  for (const drill of drills) {
    for (const tag of drill.tags) tags.set(tag.id, tag)
    for (const item of drill.equipment_items ?? []) equipment.add(item)
  }
  return { tags: [...tags.values()].sort((a, b) => a.label.localeCompare(b.label)), equipment: [...equipment].sort() }
}

const within = (value, [min, max]) => value === '' || (Number(value) >= min && Number(value) <= max)

export function matchesFilters(drill, filters) {
  const text = filters.text.trim().toLowerCase()
  if (text && ![drill.title, drill.summary, ...drill.tags.map(t => t.label)].some(s => s.toLowerCase().includes(text))) return false
  if (filters.area && !drill.tags.some(t => t.area === filters.area)) return false
  if (filters.tag && !drill.tags.some(t => t.id === filters.tag)) return false
  if (filters.format && drill.format !== filters.format) return false
  if (filters.intensity && drill.intensity !== filters.intensity) return false
  if (!within(filters.players, [drill.players[0], drill.players[2]])) return false
  if (!within(filters.age, drill.ages) || !within(filters.level, drill.levels)) return false
  // Fits in the time: the drill's shortest useful run is no longer than the time available.
  if (filters.duration !== '' && drill.duration[0] > Number(filters.duration)) return false
  // Equipment lists what the coach has; the drill must need nothing else.
  if (filters.equipment.length && !(drill.equipment_items ?? []).every(item => filters.equipment.includes(item))) return false
  if (filters.home && !drill.home_friendly) return false
  if (filters.liked && drill.votes.mine !== 1) return false
  return true
}

// The coach's own vote outranks everyone else's: liked first, disliked last, then most liked overall, then by title.
export function sortDrills(drills) {
  const rank = d => -d.votes.mine
  const net = d => d.votes.likes - d.votes.dislikes
  return [...drills].sort((a, b) => rank(a) - rank(b) || net(b) - net(a) || a.title.localeCompare(b.title))
}

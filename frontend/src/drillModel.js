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

// Shared helpers so the skill matrix (v2) drives the UI, with a single source
// of truth for positions, the rating scale, and section filtering.

export const POSITION_LABELS = {
  goalkeeper: 'Goalkeeper',
  defender: 'Defender',
  midfielder: 'Midfielder',
  winger: 'Winger',
  striker: 'Striker',
}

export const POSITION_ABBR = {
  goalkeeper: 'GK',
  defender: 'DEF',
  midfielder: 'MID',
  winger: 'WNG',
  striker: 'ST',
}

export const OUTFIELD_POSITIONS = ['defender', 'midfielder', 'winger', 'striker']
export const ALL_POSITIONS = ['goalkeeper', ...OUTFIELD_POSITIONS]

export const FREQUENCIES = [
  { id: 'rarely', label: 'Rarely' },
  { id: 'sometimes', label: 'Sometimes' },
  { id: 'often', label: 'Often' },
]

// Normalise a stored position to its canonical lowercase id (older rows stored
// capitalised values like "Defender").
export const norm = (p) => (p ? String(p).toLowerCase() : p)

// Which skill set a position uses: goalkeeper -> goalkeeper, anything else -> outfield.
export const skillSetFor = (position) => (norm(position) === 'goalkeeper' ? 'goalkeeper' : 'outfield')

// Sections applicable to a position. Accepts a granular id ('defender'),
// the 'outfield' alias, or 'goalkeeper'. All outfield positions share the same
// technical + tactical sections.
export function sectionsFor(matrix, position) {
  const p = norm(position)
  if (p === 'goalkeeper') return matrix.sections.filter(s => s.applies_to.includes('goalkeeper'))
  const target = p === 'outfield' || !p ? OUTFIELD_POSITIONS : [p]
  return matrix.sections.filter(s => s.applies_to.some(a => target.includes(a)))
}

export const scalePoints = (matrix) => matrix?.meta?.scale?.points ?? [1, 2, 3, 4, 5]
export const scaleAnchors = (matrix) => matrix?.meta?.scale?.anchors ?? {}

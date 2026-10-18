// A team's own drill in the editor: the form's state, the drill it came from, and what the server is sent.
// Numbers and list items are kept as text while editing; formBody turns them into the drill's fields.

// What a coach can choose beyond balls, bibs and cones (the server's EQUIPMENT list).
export const EQUIPMENT_ITEMS = ['balls', 'bibs', 'cones', 'goals', 'mini_goals', 'mannequins', 'hurdles', 'ladders', 'poles', 'other']
export const GENERAL_PHASES = ['warm_up', 'cool_down']  // may train no particular skill

const text = value => (value === null || value === undefined ? '' : String(value))

export function emptyForm() {
  return {
    title: '', summary: '', session_phase: 'technical', format: 'small_group', players: ['4', '8', '12'], ages: ['8', '14'],
    duration: ['10', '15'], intensity: 'medium', space: ['', ''], equipment: {}, setup: '', instructions: [''], coaching_points: [''],
    tags: {}, home_friendly: false, indoors: '', easier: null, harder: null, video_url: '',
  }
}

// The editor's state for a drill as the drill page has it.
export function formFromDrill(drill) {
  const version = kind => { const v = drill.variations.find(x => x.kind === kind); return v ? { title: v.title, change: v.change } : null }
  return {
    title: drill.title, summary: drill.summary ?? '', session_phase: drill.session_phase, format: drill.format,
    players: drill.players.map(text), ages: drill.ages.map(text), duration: drill.duration.map(text), intensity: drill.intensity,
    space: drill.space ? drill.space.map(text) : ['', ''],
    equipment: Object.fromEntries((drill.equipment ?? []).map(e => [e.item, text(e.quantity ?? 1)])),
    setup: drill.setup ?? '', instructions: drill.instructions?.length ? [...drill.instructions] : [''],
    coaching_points: drill.coaching_points?.length ? [...drill.coaching_points] : [''],
    tags: Object.fromEntries(drill.tags.map(t => [t.id, t.weight])), home_friendly: drill.home_friendly, indoors: drill.indoors ?? '',
    easier: version('regression'), harder: version('escalator'), video_url: drill.media.find(m => m.kind === 'video')?.url ?? '',
  }
}

// A copy of a library drill's words, to start the team's own version from. Only its text: no diagrams or videos.
// Library drills can have several easier or harder versions; the copy takes the ones nearest the base.
export function formFromLibrary(drill) {
  const base = drill.variations.findIndex(v => v.kind === 'base')
  const near = v => (v ? { title: v.title, change: v.change } : null)
  return { ...formFromDrill(drill), easier: near(drill.variations[base - 1]?.kind === 'regression' ? drill.variations[base - 1] : null),
    harder: near(drill.variations[base + 1]?.kind === 'escalator' ? drill.variations[base + 1] : null), video_url: '' }
}

const numbers = values => values.map(v => Number(v))

// What the server is sent: numbers as numbers, empty list items and an empty space left out.
export function formBody(form) {
  const space = form.space.every(v => String(v).trim() !== '') ? numbers(form.space) : null
  const version = v => (v && (v.title.trim() || v.change.trim()) ? { title: v.title.trim(), change: v.change.trim() } : null)
  return {
    title: form.title.trim(), summary: form.summary.trim(), session_phase: form.session_phase, format: form.format,
    players: numbers(form.players), ages: numbers(form.ages), duration: numbers(form.duration), intensity: form.intensity, space,
    equipment: Object.entries(form.equipment).filter(([, q]) => q !== '' && Number(q) > 0).map(([item, q]) => ({ item, quantity: Number(q) })),
    setup: form.setup.trim(), instructions: form.instructions.map(s => s.trim()).filter(Boolean),
    coaching_points: form.coaching_points.map(s => s.trim()).filter(Boolean), tags: form.tags,
    home_friendly: form.home_friendly, indoors: form.home_friendly && form.indoors.trim() ? form.indoors.trim() : null,
    easier: version(form.easier), harder: version(form.harder), video_url: form.video_url.trim() || null,
    ...(form.shadows ? { shadows: form.shadows } : {}),
  }
}

// What stops the form from being saved; the server checks again and has the last word.
export function formProblems(form) {
  const body = formBody(form)
  const problems = []
  if (!body.title) problems.push('Give the drill a name.')
  if (!body.setup) problems.push('Describe the set-up.')
  if (!body.instructions.length) problems.push('Add at least one step.')
  const [low, ideal, high] = body.players
  if (![low, ideal, high].every(Number.isInteger) || low < 1 || low > ideal || ideal > high) problems.push('Players: the smallest number, the best number and the most, in that order.')
  const [young, old] = body.ages
  if (!Number.isInteger(young) || !Number.isInteger(old) || young < 4 || young > old || old > 23) problems.push('Ages: the youngest and oldest age group, from U4 to U23.')
  const [shortest, usual] = body.duration
  if (!Number.isInteger(shortest) || !Number.isInteger(usual) || shortest < 1 || shortest > usual) problems.push('Minutes: the shortest useful run and the usual length, shortest first.')
  if (!GENERAL_PHASES.includes(body.session_phase) && !Object.values(body.tags).includes(1)) problems.push('Choose at least one skill this drill mainly trains.')
  for (const [name, v] of [['easier', body.easier], ['harder', body.harder]]) {
    if (v && (!v.title || !v.change)) problems.push(`The ${name} version needs a name and what changes.`)
  }
  return problems
}

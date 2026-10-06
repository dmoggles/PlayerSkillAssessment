import { useCallback, useEffect, useMemo, useState } from 'react'
import { errorMessage, getDrill, getDrills, voteOnDrill } from './api'
import DiagramPlayer from './DiagramPlayer'
import { AREA_LABELS, DISLIKE_REASONS, EMPTY_FILTERS, FORMAT_LABELS, INTENSITY_LABELS, PHASE_LABELS, activeFilterCount, effectiveDrill, equipmentLabel, filterOptions, matchesFilters, sortDrills, isVerticalVideo, levelRange, playersText, variationDiagram, videoEmbedUrl, visibleVideos } from './drillModel'

// Settings card: how big the library is, and the way in.
export function DrillLibrarySummary({ onOpen }) {
  const [count, setCount] = useState(null)
  useEffect(() => {
    let live = true
    getDrills().then(value => { if (live) setCount(value.length) }).catch(() => { if (live) setCount(false) })
    return () => { live = false }
  }, [])
  return <div className="matrix-card">
    <p>{count === null ? 'Loading…' : count === false ? 'Could not load the drill library.' : `${count} ${count === 1 ? 'drill' : 'drills'}, each tagged to skills with easier and harder variations.`}</p>
    <button type="button" onClick={onOpen}>Browse drill library</button>
  </div>
}

// The shared drill library: a filterable list of drills and a detail view with the variation ladder and diagrams.
// Filters live here, so they survive opening a drill and coming back.
export default function DrillLibrary({ onMessage }) {
  const [drills, setDrills] = useState(null)
  const [open, setOpen] = useState(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  useEffect(() => {
    let live = true
    getDrills().then(value => { if (live) setDrills(value) }).catch(e => onMessage(errorMessage(e)))
    return () => { live = false }
  }, [onMessage])
  const onVoted = useCallback((slug, votes) => setDrills(previous => previous?.map(d => d.slug === slug ? { ...d, votes } : d)), [])
  const options = useMemo(() => filterOptions(drills ?? []), [drills])
  if (open) return <DrillDetail slug={open} onBack={() => setOpen(null)} onOpen={setOpen} onVoted={onVoted} onMessage={onMessage} />
  if (!drills) return <p className="muted" role="status">Loading drills…</p>
  if (!drills.length) return <p className="muted">The drill library is empty.</p>
  const shown = sortDrills(drills.filter(d => matchesFilters(d, filters)))
  return <>
    <DrillFilters filters={filters} options={options} onChange={setFilters} />
    <p className="muted drill-count" role="status">{shown.length === drills.length ? `${drills.length} drills` : `${shown.length} of ${drills.length} drills`}</p>
    {shown.length === 0 && <p className="muted">No drills match these filters.</p>}
    <ul className="drill-list">{shown.map(d => <li key={d.slug}>
      <button type="button" className={`drill-card${d.votes.mine === -1 ? ' disliked' : ''}`} onClick={() => setOpen(d.slug)}>
        <strong>{d.title}</strong>
        <span className="drill-card-summary">{d.summary}</span>
        <span className="drill-facts">{FORMAT_LABELS[d.format]} · {playersText(d.players)} · {d.duration[1]} min · {levelRange(d.levels)}</span>
        <span className="drill-tags">{d.tags.map(t => <span key={t.id} className={`status-pill ${t.weight === 1 ? 'info-pill' : 'muted-pill'}`}>{t.label}</span>)}</span>
        <VoteSummary votes={d.votes} />
      </button>
    </li>)}</ul>
  </>
}

function VoteSummary({ votes }) {
  return <span className="drill-votes">
    <span aria-label={`${votes.likes} ${votes.likes === 1 ? 'like' : 'likes'}`}>👍 {votes.likes}</span>
    <span aria-label={`${votes.dislikes} ${votes.dislikes === 1 ? 'dislike' : 'dislikes'}`}>👎 {votes.dislikes}</span>
    {votes.mine === 1 && <span className="status-pill info-pill">You like this</span>}
    {votes.mine === -1 && <span className="status-pill muted-pill">You disliked this</span>}
  </span>
}

function DrillFilters({ filters, options, onChange }) {
  const set = (key, value) => onChange({ ...filters, [key]: value })
  const select = (key, label, choices) => <label className="field">{label}<select value={filters[key]} onChange={e => set(key, e.target.value)}>
    <option value="">Any</option>{choices.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
  </select></label>
  const number = (key, label, min, max, hint) => <label className="field">{label}<input type="number" inputMode="numeric" min={min} max={max} placeholder="Any" value={filters[key]} onChange={e => set(key, e.target.value)} />{hint && <small>{hint}</small>}</label>
  const count = activeFilterCount(filters)
  const toggleItem = item => set('equipment', filters.equipment.includes(item) ? filters.equipment.filter(i => i !== item) : [...filters.equipment, item])
  return <div className="drill-filters">
    <div className="drill-search">
      <input type="search" aria-label="Search drills" placeholder="Search drills or skills" value={filters.text} onChange={e => set('text', e.target.value)} />
      {(count > 0 || filters.text) && <button type="button" className="link-btn" onClick={() => onChange(EMPTY_FILTERS)}>Clear filters</button>}
    </div>
    <details open={count > 0 || undefined}>
      <summary>Filters{count ? ` (${count})` : ''}</summary>
      <div className="drill-filter-grid">
        {select('area', 'Area', Object.entries(AREA_LABELS))}
        {select('tag', 'Skill', options.tags.filter(t => !filters.area || t.area === filters.area).map(t => [t.id, t.label]))}
        {select('format', 'Format', Object.entries(FORMAT_LABELS))}
        {select('intensity', 'Intensity', Object.entries(INTENSITY_LABELS))}
        {number('players', 'Players', 1, 40, 'How many you have')}
        {number('age', 'Age group (U)', 5, 21, 'For example 12 for U12')}
        {number('level', 'Player level', 1, 5, '1–5 skill scale')}
        {number('duration', 'Time available (min)', 1, 120)}
      </div>
      {options.equipment.length > 0 && <fieldset className="drill-equipment">
        <legend>Equipment you have <small>(shows drills that need nothing else)</small></legend>
        {options.equipment.map(item => <label key={item} className="checkbox"><input type="checkbox" checked={filters.equipment.includes(item)} onChange={() => toggleItem(item)} /> {equipmentLabel(item)}</label>)}
      </fieldset>}
      <div className="drill-equipment">
        <label className="checkbox"><input type="checkbox" checked={filters.home} onChange={e => set('home', e.target.checked)} /> Can be done at home</label>
        <label className="checkbox"><input type="checkbox" checked={filters.liked} onChange={e => set('liked', e.target.checked)} /> Only drills I like</label>
      </div>
    </details>
  </div>
}

function DrillDetail({ slug, onBack, onOpen, onVoted, onMessage }) {
  const [drill, setDrill] = useState(null)
  const [variationId, setVariationId] = useState(null)
  useEffect(() => {
    let live = true
    getDrill(slug).then(value => { if (live) setDrill(value) }).catch(e => onMessage(errorMessage(e)))
    return () => { live = false }
  }, [slug, onMessage])
  const vote = useCallback(async (value, reason = null) => {
    try {
      const votes = await voteOnDrill(slug, value, reason)
      setDrill(previous => ({ ...previous, votes }))
      onVoted(slug, votes)
    } catch (e) { onMessage(errorMessage(e)) }
  }, [slug, onVoted, onMessage])
  if (!drill) return <p className="muted" role="status">Loading drill…</p>

  const selected = drill.variations.find(v => v.id === variationId) ?? drill.variations.find(v => v.kind === 'base')
  const shown = variationDiagram(drill, selected)
  const videos = visibleVideos(drill, selected)
  const links = drill.media.filter(m => m.kind === 'link')
  const view = effectiveDrill(drill, selected)
  const changedTag = field => view.changed.has(field) && <span className="status-pill warn-pill variation-changed">Changed for this variation</span>

  return <article className="drill-detail">
    <button type="button" className="link-btn back-link" onClick={onBack}>← All drills</button>
    <header><h3>{drill.title}</h3><p>{drill.summary}</p>
      <p className="drill-facts">{FORMAT_LABELS[drill.format]} · {playersText(view.players)} · U{drill.ages[0]}–U{drill.ages[1]} · {drill.duration[0]}–{drill.duration[1]} min · {PHASE_LABELS[drill.session_phase]} · {drill.intensity} intensity{view.space ? ` · ${view.space[0]}×${view.space[1]} m` : ''}{drill.home_friendly ? ' · can be done at home' : ''}</p>
      <p className="drill-tags">{drill.tags.map(t => <span key={t.id} className={`status-pill ${t.weight === 1 ? 'info-pill' : 'muted-pill'}`}>{t.label}{t.weight === 1 ? '' : ' (partial)'}</span>)}</p>
      <DrillVote votes={drill.votes} onVote={vote} />
    </header>
    <div className="drill-detail-body">
      <section className="drill-ladder" aria-labelledby="ladder-title">
        <h4 id="ladder-title">Variations</h4>
        <p className="muted hint">From easiest to hardest. Levels use the 1–5 skill scale; choose the one that matches the player.</p>
        <ol>{drill.variations.map(v => <li key={v.id}><button type="button" className={selected?.id === v.id ? 'active' : ''} aria-pressed={selected?.id === v.id} onClick={() => setVariationId(v.id)}>
          <span className={`ladder-kind ladder-${v.kind}`}>{v.kind === 'base' ? 'Base' : v.kind === 'regression' ? 'Easier' : 'Harder'}</span>
          <strong>{v.title}</strong><span className="ladder-levels">Levels {v.levels[0]}–{v.levels[1]}</span>
          <span className="ladder-change">{v.change}</span>
        </button></li>)}</ol>
      </section>
      {shown && <DiagramPlayer key={shown.id} diagram={shown.diagram} caption={shown.caption} />}
    </div>
    {videos.map(v => <VideoLink key={v.id} video={v} />)}
    <p className="muted variation-note" aria-live="polite">Showing: <strong>{selected?.title}</strong>{view.changed.size ? '. Sections marked below differ from the base version.' : ''}</p>
    {view.setup && <section><h4>Setup {changedTag('setup')}</h4><p>{view.setup}</p></section>}
    {view.equipment.length > 0 && <section><h4>Equipment {changedTag('equipment')}</h4><p>{view.equipment.map(e => `${e.quantity} ${equipmentLabel(e.item)}`).join(', ')}</p></section>}
    <section><h4>How it runs {changedTag('instructions')}</h4><ol>{view.instructions.map(i => <li key={i}>{i}</li>)}</ol></section>
    <section><h4>Coaching points {changedTag('coaching_points')}</h4><ul>{view.coaching_points.map(c => <li key={c}>{c}</li>)}</ul></section>
    {links.length > 0 && <section><h4>Links</h4><ul>{links.map(l => <li key={l.id}><a href={l.url} target="_blank" rel="noreferrer">{l.caption || l.url}</a></li>)}</ul></section>}
    {drill.links.length > 0 && <section><h4>Related drills</h4><ul>{drill.links.map(l => <li key={l.slug}><button type="button" className="link-btn" onClick={() => onOpen(l.slug)}>{l.title}</button> <span className="muted">({l.relation.replace('_', ' ')})</span></li>)}</ul></section>}
  </article>
}

// Pressing the active button again clears the vote. A dislike may say why; the reason is optional.
function DrillVote({ votes, onVote }) {
  return <div className="drill-vote">
    <button type="button" aria-pressed={votes.mine === 1} className={votes.mine === 1 ? 'active' : ''} onClick={() => onVote(votes.mine === 1 ? 0 : 1)}>👍 Like <span className="muted">{votes.likes}</span></button>
    <button type="button" aria-pressed={votes.mine === -1} className={votes.mine === -1 ? 'active' : ''} onClick={() => onVote(votes.mine === -1 ? 0 : -1)}>👎 Dislike <span className="muted">{votes.dislikes}</span></button>
    {votes.mine === -1 && <label className="drill-vote-reason">Why? <span className="muted">(optional)</span>
      <select value={votes.reason ?? ''} onChange={e => onVote(-1, e.target.value || null)}>
        <option value="">No reason given</option>{Object.entries(DISLIKE_REASONS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select></label>}
    <small className="muted">{votes.mine === -1 ? 'Disliked drills go to the end of your list and will not be suggested to you.' : 'Votes are anonymous; other coaches see only the totals.'}</small>
  </div>
}

// Videos load only when asked for, using YouTube's privacy-enhanced domain.
function VideoLink({ video }) {
  const [playing, setPlaying] = useState(false)
  const embed = videoEmbedUrl(video.url, video.start_seconds)
  if (!embed) return <p><a href={video.url} target="_blank" rel="noreferrer">{video.caption || 'Watch the video'}</a></p>
  return <section className="drill-video">
    <div className="drill-video-head">
      <button type="button" aria-expanded={playing} onClick={() => setPlaying(!playing)}>{playing ? 'Close video' : '▶ Play video'}</button>
      {video.forVariation && <span className="status-pill warn-pill variation-changed">For this variation</span>}
      {video.caption && <p>{video.caption}</p>}
    </div>
    {/* Closing removes the player entirely, which also stops the video. */}
    {playing && <iframe className={isVerticalVideo(video.url) ? 'vertical' : undefined} src={embed} title={video.caption || 'Drill video'} allow="encrypted-media; picture-in-picture; fullscreen" referrerPolicy="strict-origin-when-cross-origin" />}
  </section>
}

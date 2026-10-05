import { useEffect, useState } from 'react'
import { errorMessage, getDrill, getDrills } from './api'
import DiagramPlayer from './DiagramPlayer'
import { FORMAT_LABELS, PHASE_LABELS, effectiveDrill, isVerticalVideo, levelRange, playersText, variationDiagram, videoEmbedUrl, visibleVideos } from './drillModel'

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

// The shared drill library: a list of drills and a detail view with the variation ladder and diagrams.
export default function DrillLibrary({ onMessage }) {
  const [drills, setDrills] = useState(null)
  const [open, setOpen] = useState(null)
  useEffect(() => {
    let live = true
    getDrills().then(value => { if (live) setDrills(value) }).catch(e => onMessage(errorMessage(e)))
    return () => { live = false }
  }, [onMessage])
  if (open) return <DrillDetail slug={open} onBack={() => setOpen(null)} onOpen={setOpen} onMessage={onMessage} />
  if (!drills) return <p className="muted" role="status">Loading drills…</p>
  if (!drills.length) return <p className="muted">The drill library is empty.</p>
  return <ul className="drill-list">{drills.map(d => <li key={d.slug}>
    <button type="button" className="drill-card" onClick={() => setOpen(d.slug)}>
      <strong>{d.title}</strong>
      <span className="drill-card-summary">{d.summary}</span>
      <span className="drill-facts">{FORMAT_LABELS[d.format]} · {playersText(d.players)} · {d.duration[1]} min · {levelRange(d.levels)}</span>
      <span className="drill-tags">{d.tags.map(t => <span key={t.id} className={`status-pill ${t.weight === 1 ? 'info-pill' : 'muted-pill'}`}>{t.label}</span>)}</span>
    </button>
  </li>)}</ul>
}

function DrillDetail({ slug, onBack, onOpen, onMessage }) {
  const [drill, setDrill] = useState(null)
  const [variationId, setVariationId] = useState(null)
  useEffect(() => {
    let live = true
    getDrill(slug).then(value => { if (live) setDrill(value) }).catch(e => onMessage(errorMessage(e)))
    return () => { live = false }
  }, [slug, onMessage])
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
    {view.equipment.length > 0 && <section><h4>Equipment {changedTag('equipment')}</h4><p>{view.equipment.map(e => `${e.quantity} ${e.item.replace('_', ' ')}`).join(', ')}</p></section>}
    <section><h4>How it runs {changedTag('instructions')}</h4><ol>{view.instructions.map(i => <li key={i}>{i}</li>)}</ol></section>
    <section><h4>Coaching points {changedTag('coaching_points')}</h4><ul>{view.coaching_points.map(c => <li key={c}>{c}</li>)}</ul></section>
    {links.length > 0 && <section><h4>Links</h4><ul>{links.map(l => <li key={l.id}><a href={l.url} target="_blank" rel="noreferrer">{l.caption || l.url}</a></li>)}</ul></section>}
    {drill.links.length > 0 && <section><h4>Related drills</h4><ul>{drill.links.map(l => <li key={l.slug}><button type="button" className="link-btn" onClick={() => onOpen(l.slug)}>{l.title}</button> <span className="muted">({l.relation.replace('_', ' ')})</span></li>)}</ul></section>}
  </article>
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

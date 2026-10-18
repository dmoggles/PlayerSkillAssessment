import { useEffect, useState } from 'react'
import { createTeamDrill, errorMessage, getSkillTags, updateTeamDrill } from './api'
import { AREA_LABELS, FORMAT_LABELS, INTENSITY_LABELS, PHASE_LABELS, equipmentLabel, videoEmbedUrl } from './drillModel'
import { EQUIPMENT_ITEMS, GENERAL_PHASES, emptyForm, formBody, formFromDrill, formProblems } from './teamDrillModel'

// Writing or editing one of the team's own drills. Team drills have no diagram: the set-up, the steps and, if the
// coach has one, a video link describe them. `drill` is the drill being edited (none for a new one).
export default function TeamDrillForm({ teamId, drill = null, onSaved, onCancel, onMessage, initialTags = null }) {
  const [form, setForm] = useState(() => (drill ? formFromDrill(drill) : emptyForm()))
  const [tags, setTags] = useState(initialTags ?? [])
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (initialTags) return undefined
    let live = true
    getSkillTags().then(value => { if (live) setTags(value.filter(t => t.active)) }).catch(() => {})
    return () => { live = false }
  }, [initialTags])
  const set = (key, value) => setForm(f => ({ ...f, [key]: value }))
  const setAt = (key, i, value) => setForm(f => ({ ...f, [key]: f[key].map((v, j) => (j === i ? value : v)) }))
  const problems = formProblems(form)
  const general = GENERAL_PHASES.includes(form.session_phase)
  const labels = Object.fromEntries(tags.map(t => [t.id, t.label]))
  const embed = form.video_url.trim() ? videoEmbedUrl(form.video_url.trim()) : null

  async function submit(event) {
    event.preventDefault()
    if (problems.length) return
    setBusy(true)
    try { onSaved(drill ? await updateTeamDrill(teamId, drill.slug, formBody(form)) : await createTeamDrill(teamId, formBody(form))) }
    catch (e) { onMessage(errorMessage(e, 'Could not save the drill.')); setBusy(false) }
  }

  const triple = (key, names, hint, optional = false) => <fieldset className="team-drill-numbers"><legend>{hint}</legend>
    {names.map((name, i) => <label key={name} className="field">{name}<input type="number" inputMode="numeric" required={!optional} min={0} value={form[key][i]} onChange={e => setAt(key, i, e.target.value)} /></label>)}
  </fieldset>
  const list = (key, label, placeholder) => <fieldset className="team-drill-list"><legend>{label}</legend>
    {form[key].map((value, i) => <div key={i} className="team-drill-item">
      <span className="muted">{i + 1}.</span>
      <textarea rows={2} maxLength={500} aria-label={`${label} ${i + 1}`} placeholder={placeholder} value={value} onChange={e => setAt(key, i, e.target.value)} />
      {form[key].length > 1 && <button type="button" className="link-btn" aria-label={`Remove ${label.toLowerCase()} ${i + 1}`} onClick={() => set(key, form[key].filter((_, j) => j !== i))}>Remove</button>}
    </div>)}
    {form[key].length < 12 && <button type="button" className="link-btn" onClick={() => set(key, [...form[key], ''])}>+ Add another</button>}
  </fieldset>
  const version = (key, label, hint) => form[key]
    ? <fieldset className="team-drill-version"><legend>{label}</legend>
      <label className="field">Name<input maxLength={120} value={form[key].title} onChange={e => set(key, { ...form[key], title: e.target.value })} /></label>
      <label className="field">What changes<textarea rows={2} maxLength={500} value={form[key].change} placeholder={hint} onChange={e => set(key, { ...form[key], change: e.target.value })} /></label>
      <button type="button" className="link-btn" onClick={() => set(key, null)}>Remove this version</button>
    </fieldset>
    : <button type="button" className="link-btn" onClick={() => set(key, { title: '', change: '' })}>+ Add {label.toLowerCase()}</button>

  return <form className="session-form team-drill-form" onSubmit={submit}>
    <h3>{drill ? `Edit ${drill.title}` : 'Add a drill'}</h3>
    <p className="muted hint">Only your team's coaches see this drill. It can be chosen for sessions and plans like any drill in the library.</p>
    <label className="field">Name<input required maxLength={120} value={form.title} onChange={e => set('title', e.target.value)} placeholder="Say what players do, for example Four-corner passing" /></label>
    <label className="field"><span>Summary <span className="muted">(optional)</span></span><input maxLength={300} value={form.summary} onChange={e => set('summary', e.target.value)} /></label>
    <div className="session-form-row">
      <label className="field">Part of the session<select value={form.session_phase} onChange={e => set('session_phase', e.target.value)}>{Object.entries(PHASE_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label className="field">Format<select value={form.format} onChange={e => set('format', e.target.value)}>{Object.entries(FORMAT_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label className="field">Intensity<select value={form.intensity} onChange={e => set('intensity', e.target.value)}>{Object.entries(INTENSITY_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
    </div>
    <div className="team-drill-row">
      {triple('players', ['Fewest', 'Best', 'Most'], 'Players')}
      {triple('ages', ['Youngest (U)', 'Oldest (U)'], 'Age groups')}
      {triple('duration', ['Shortest', 'Usual'], 'Minutes')}
      {triple('space', ['Width (m)', 'Length (m)'], 'Space (optional)', true)}
    </div>

    <fieldset className="team-drill-tags"><legend>Skills it trains</legend>
      <p className="muted hint">{general ? 'Optional for a warm-up or cool-down. ' : ''}Main: what the drill is for. Partial: it helps a little.</p>
      {Object.entries(form.tags).map(([id, weight]) => <div key={id} className="team-drill-item">
        <strong>{labels[id] ?? id}</strong>
        <select aria-label={`How much it trains ${labels[id] ?? id}`} value={weight} onChange={e => set('tags', { ...form.tags, [id]: Number(e.target.value) })}><option value={1}>Main</option><option value={0.5}>Partial</option></select>
        <button type="button" className="link-btn" onClick={() => { const next = { ...form.tags }; delete next[id]; set('tags', next) }}>Remove</button>
      </div>)}
      {Object.keys(form.tags).length < 6 && <label className="field">Add a skill<select value="" onChange={e => e.target.value && set('tags', { ...form.tags, [e.target.value]: Object.keys(form.tags).length ? 0.5 : 1 })}>
        <option value="">Choose a skill…</option>
        {Object.entries(AREA_LABELS).map(([area, label]) => <optgroup key={area} label={label}>{tags.filter(t => t.area === area && !(t.id in form.tags)).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</optgroup>)}
      </select></label>}
    </fieldset>

    <fieldset className="team-drill-equipment"><legend>Equipment <span className="muted">(leave empty what you don't need)</span></legend>
      <div className="template-parts">{EQUIPMENT_ITEMS.map(item => <label key={item} className="field">{equipmentLabel(item)}
        <input type="number" inputMode="numeric" min={0} max={99} placeholder="None" value={form.equipment[item] ?? ''} onChange={e => set('equipment', { ...form.equipment, [item]: e.target.value })} /></label>)}</div>
    </fieldset>

    <label className="field">Set-up<textarea required rows={3} maxLength={2000} value={form.setup} onChange={e => set('setup', e.target.value)} placeholder="The area, where the cones and players go, who has a ball" /></label>
    {list('instructions', 'Steps', 'What players do, in order')}
    {list('coaching_points', 'Coaching points', 'What to look for and say')}

    <fieldset className="team-drill-version-group"><legend>Easier and harder versions <span className="muted">(optional)</span></legend>
      <p className="muted hint">Level groups and players' plans use these: the easier version for players rated 1–2, the harder for 4–5.</p>
      {version('easier', 'Easier version', 'For example: a bigger area, two touches allowed')}
      {version('harder', 'Harder version', 'For example: one touch, a defender added')}
    </fieldset>

    <label className="checkbox"><input type="checkbox" checked={form.home_friendly} onChange={e => set('home_friendly', e.target.checked)} /> Can be done at home, alone or with a parent</label>
    {form.home_friendly && <label className="field"><span>Indoors <span className="muted">(optional)</span></span><textarea rows={2} maxLength={1000} value={form.indoors} onChange={e => set('indoors', e.target.value)} placeholder="How to do it safely indoors: a soft ball, household items" /></label>}

    <label className="field"><span>Video <span className="muted">(optional YouTube or Vimeo link)</span></span><input type="url" maxLength={300} value={form.video_url} onChange={e => set('video_url', e.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
      {form.video_url.trim() && !embed && <small className="warning">Use a YouTube or Vimeo link.</small>}</label>

    {problems.length > 0 && <ul className="muted hint team-drill-problems">{problems.map(p => <li key={p}>{p}</li>)}</ul>}
    <div className="inline-row">
      <button type="submit" className="primary-btn" disabled={busy || problems.length > 0}>{busy ? 'Saving…' : drill ? 'Save changes' : 'Save drill'}</button>
      <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>
    </div>
  </form>
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { addSessionBlock, createSession, createSessionTemplate, deleteSession, deleteSessionBlock, deleteSessionTemplate, errorMessage, getBlockAlternatives, getDrill, getSession,
  getSessionFocus, getSessions, getSessionTemplates, getSkillTags, regenerateSession, setMatchTeams, setSessionAttendance, setSessionGroups, suggestMatchTeams, updateSession,
  updateSessionBlock, updateSessionTemplate } from '../api'
import { DrillDialog } from '../DrillLibrary'
import SessionReport from '../SessionReport'
import { AREA_LABELS } from '../drillModel'
import { DEFAULT_BREAKDOWNS, PHASE_NAMES, SESSION_LENGTHS, blockTimes, breakdownText, focusChip, sessionDate, splitSessions, teamSummary, templateProblems,
  templateTotal, versionLabel } from '../sessionModel'
import { Section } from './DashboardParts'

const tomorrow = () => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10) }

// Sessions: the team's training sessions, planning a new one, one session's plan, and the team's session templates.
export default function SessionsArea({ team, period, players, onMessage }) {
  const [view, setView] = useState({ kind: 'list' })
  if (view.kind === 'new') return <NewSession team={team} period={period} players={players} onMessage={onMessage}
    onCancel={() => setView({ kind: 'list' })} onCreated={session => setView({ kind: 'session', id: session.id })} />
  if (view.kind === 'templates') return <TemplatesView team={team} onMessage={onMessage} onBack={() => setView({ kind: 'list' })} />
  if (view.kind === 'session') return <SessionView key={view.id} teamId={team.id} teamName={team.name} sessionId={view.id} players={players} onMessage={onMessage} onBack={() => setView({ kind: 'list' })} />
  return <SessionList team={team} period={period} onMessage={onMessage} onNew={() => setView({ kind: 'new' })} onOpen={id => setView({ kind: 'session', id })}
    onTemplates={() => setView({ kind: 'templates' })} />
}

function SessionList({ team, period, onNew, onOpen, onTemplates, onMessage }) {
  const [sessions, setSessions] = useState(null)
  useEffect(() => {
    let live = true
    getSessions(team.id).then(value => { if (live) setSessions(value) }).catch(e => onMessage(errorMessage(e, 'Could not load sessions.')))
    return () => { live = false }
  }, [team.id, onMessage])
  const { upcoming, past } = useMemo(() => splitSessions(sessions ?? []), [sessions])
  const card = s => <li key={s.id}><button type="button" className="session-card" onClick={() => onOpen(s.id)}>
    <span className="session-card-date">{sessionDate(s.date, s.start_time)}</span>
    <strong>{s.title}</strong>
    <span className="muted">{s.length} min{s.template ? ` (${s.template.name})` : ''} · {s.focus.map(f => f.label).join(', ')} · {s.attended ? `${s.attended} came` : `${s.expected} expected`}{s.versions === 'groups' ? ' · level groups' : ''}</span>
  </button></li>
  return <Section title="Training sessions" description="Team sessions planned around what your players are working on">
    <div className="inline-row session-list-actions">
      {period ? <button type="button" className="primary-btn session-new" onClick={onNew}>Plan a session</button>
        : <p className="muted">Add a period in Settings to plan sessions.</p>}
      <button type="button" className="secondary-btn session-new" onClick={onTemplates}>Templates</button>
    </div>
    {sessions === null ? <p className="muted" role="status">Loading sessions…</p> : <>
      <h3 className="session-list-heading">Upcoming</h3>
      {upcoming.length ? <ul className="session-list">{upcoming.map(card)}</ul> : <p className="muted">No sessions planned.</p>}
      {past.length > 0 && <><h3 className="session-list-heading">Past</h3><ul className="session-list">{past.map(card)}</ul></>}
    </>}
  </Section>
}

function NewSession({ team, period, players, onCreated, onCancel, onMessage }) {
  const squad = useMemo(() => players.filter(p => p.active), [players])
  const [date, setDate] = useState(tomorrow())
  const [time, setTime] = useState('')
  const [length, setLength] = useState(60)
  const [templates, setTemplates] = useState([])
  const [templateId, setTemplateId] = useState('')
  const [suggested, setSuggested] = useState(null)
  const [tags, setTags] = useState([])
  const [focus, setFocus] = useState(null)
  const [expected, setExpected] = useState(() => new Set(squad.map(p => p.id)))
  const [versions, setVersions] = useState('single')
  const [groupCount, setGroupCount] = useState(2)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let live = true
    getSessionFocus(team.id, period.id).then(value => { if (live) setSuggested(value) }).catch(() => { if (live) setSuggested([]) })
    getSkillTags().then(value => { if (live) setTags(value.filter(t => t.active)) }).catch(() => {})
    getSessionTemplates(team.id).then(value => { if (live) setTemplates(value) }).catch(() => {})
    return () => { live = false }
  }, [team.id, period.id])
  // Until the coach changes it, the focus is the top suggestion.
  const chosen = focus ?? (suggested?.length ? [suggested[0].tag_id] : [])
  const labels = Object.fromEntries([...tags.map(t => [t.id, t.label]), ...(suggested ?? []).map(s => [s.tag_id, s.label])])
  const toggleFocus = id => setFocus(chosen.includes(id) ? chosen.filter(t => t !== id) : [...chosen, id].slice(0, 3))
  const template = templates.find(t => String(t.id) === templateId)
  const togglePlayer = id => setExpected(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next })

  async function submit(event) {
    event.preventDefault()
    if (!chosen.length) { onMessage('Choose at least one focus for the session.'); return }
    setBusy(true)
    try {
      onCreated(await createSession(team.id, { period_id: period.id, date, start_time: time || null,
        ...(template ? { template_id: template.id } : { length: Number(length) }), focus_tags: chosen,
        player_ids: [...expected], versions, group_count: Number(groupCount) }))
    } catch (e) { onMessage(errorMessage(e, 'Could not plan the session.')); setBusy(false) }
  }

  return <Section title="Plan a session" description={`For ${team.name}, using ${period.label}'s ratings and priorities`}>
    <form className="session-form" onSubmit={submit}>
      <div className="session-form-row">
        <label className="field">Date<input type="date" required value={date} onChange={e => setDate(e.target.value)} /></label>
        <label className="field"><span>Start time <span className="muted">(optional)</span></span><input type="time" value={time} onChange={e => setTime(e.target.value)} /></label>
      </div>
      <div className="session-form-row">
        <label className="field">Plan<select value={templateId} onChange={e => setTemplateId(e.target.value)}>
          <option value="">Default for the length</option>
          {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select></label>
        {template ? <p className="field session-template-length">Length<strong>{template.length} minutes</strong></p>
          : <label className="field">Length<select value={length} onChange={e => setLength(e.target.value)}>{SESSION_LENGTHS.map(m => <option key={m} value={m}>{m} minutes</option>)}</select></label>}
      </div>
      <p className="muted hint">{breakdownText(template ? template.minutes : DEFAULT_BREAKDOWNS[length])}{!templates.length && ' · Save your own breakdowns under Templates.'}</p>

      <fieldset className="session-focus"><legend>Focus</legend>
        <p className="muted hint">{suggested?.length ? "Suggested from what your players are working on. Choose up to three; the first counts most." : 'No priorities confirmed yet, so choose a focus.'}</p>
        <div className="focus-chips">
          {(suggested ?? []).map(s => <button key={s.tag_id} type="button" aria-pressed={chosen.includes(s.tag_id)} className={chosen.includes(s.tag_id) ? 'active' : ''} onClick={() => toggleFocus(s.tag_id)}>{focusChip(s)}</button>)}
          {chosen.filter(id => !(suggested ?? []).some(s => s.tag_id === id)).map(id => <button key={id} type="button" aria-pressed="true" className="active" onClick={() => toggleFocus(id)}>{labels[id] ?? id} ✕</button>)}
        </div>
        <label className="field">Another focus<select value="" onChange={e => e.target.value && toggleFocus(e.target.value)} disabled={chosen.length >= 3}>
          <option value="">Choose a skill…</option>
          {Object.entries(AREA_LABELS).map(([area, label]) => <optgroup key={area} label={label}>{tags.filter(t => t.area === area && !chosen.includes(t.id)).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</optgroup>)}
        </select></label>
        {chosen.length > 0 && <p className="session-focus-order">Focus, in order: {chosen.map(id => labels[id] ?? id).join(', ')}</p>}
      </fieldset>

      <fieldset className="session-players"><legend>Players expected ({expected.size} of {squad.length})</legend>
        <div className="inline-row"><button type="button" className="link-btn" onClick={() => setExpected(new Set(squad.map(p => p.id)))}>Everyone</button><button type="button" className="link-btn" onClick={() => setExpected(new Set())}>Nobody</button></div>
        <div className="session-player-grid">{squad.map(p => <label key={p.id} className="checkbox"><input type="checkbox" checked={expected.has(p.id)} onChange={() => togglePlayer(p.id)} /> {p.name}</label>)}</div>
      </fieldset>

      <fieldset className="session-versions"><legend>Levels</legend>
        <label className="checkbox"><input type="radio" name="versions" checked={versions === 'single'} onChange={() => setVersions('single')} /> One version for everyone, at the squad's level</label>
        <label className="checkbox"><input type="radio" name="versions" checked={versions === 'groups'} onChange={() => setVersions('groups')} /> Level groups, each running the same drills at its own version
          {versions === 'groups' && <select aria-label="Number of groups" value={groupCount} onChange={e => setGroupCount(e.target.value)}><option value="2">2 groups</option><option value="3">3 groups</option></select>}</label>
      </fieldset>

      <div className="inline-row">
        <button type="submit" className="primary-btn" disabled={busy || !expected.size}>{busy ? 'Planning…' : 'Plan the session'}</button>
        <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  </Section>
}

function SessionView({ teamId, teamName, sessionId, players, onBack, onMessage }) {
  const [session, setSession] = useState(null)
  const [openDrill, setOpenDrill] = useState(null)
  const [editing, setEditing] = useState(null)  // a block id, 'groups', 'teams' or 'add'
  const [drills, setDrills] = useState({})  // each block's drill in full, by slug, for the printed report
  useEffect(() => {
    let live = true
    getSession(teamId, sessionId).then(value => { if (live) setSession(value) }).catch(e => onMessage(errorMessage(e, 'Could not load the session.')))
    return () => { live = false }
  }, [teamId, sessionId, onMessage])
  const slugs = (session?.blocks ?? []).map(b => b.drill?.slug).filter(Boolean).sort().join(' ')
  const requested = useRef(new Set())
  useEffect(() => {
    const missing = slugs.split(' ').filter(slug => slug && !requested.current.has(slug))
    missing.forEach(slug => requested.current.add(slug))
    Promise.all(missing.map(slug => getDrill(slug).then(drill => [slug, drill]).catch(() => null)))
      .then(loaded => { if (loaded.some(Boolean)) setDrills(previous => ({ ...previous, ...Object.fromEntries(loaded.filter(Boolean)) })) })
  }, [slugs])
  if (!session) return <p className="muted" role="status">Loading session…</p>

  const times = blockTimes(session.blocks, session.start_time)
  const groups = session.versions === 'groups' ? session.groups : null
  const total = session.blocks.reduce((sum, b) => sum + b.minutes, 0)
  const matchBlock = session.blocks.find(b => b.phase === 'full_squad_game')?.id
  // Every change returns the whole session, which replaces the one shown.
  const change = async (call, done = () => setEditing(null)) => {
    try { setSession(await call()); done() } catch (e) { onMessage(errorMessage(e, 'Could not save the change.')) }
  }
  const remove = async () => {
    if (!window.confirm(`Delete ${session.title} on ${sessionDate(session.date)}? This can't be undone.`)) return
    try { onMessage((await deleteSession(teamId, session.id)).message); onBack() } catch (e) { onMessage(errorMessage(e)) }
  }
  const replan = () => { if (window.confirm('Plan the session again? Blocks you chose or added are kept.')) change(() => regenerateSession(teamId, session.id)) }

  return <Section className="session-view" title={session.title} description={`${sessionDate(session.date, session.start_time)} · ${session.length} minutes${session.template ? ` (${session.template.name})` : ''} · ${session.expected} players expected`}>
    <div className="session-actions no-print">
      <button type="button" className="link-btn back-link" onClick={onBack}>← All sessions</button>
      <button className="secondary-btn" type="button" onClick={replan}>Re-plan</button>
      <button className="secondary-btn" type="button" onClick={() => window.print()}>Print</button>
      <button type="button" className="danger-btn" onClick={remove}>Delete</button>
    </div>
    <p className="session-focus-pills">{session.focus.map(f => <span key={f.tag_id} className="status-pill info-pill">{f.label}</span>)}
      {total !== session.length && <span className="status-pill warn-pill">{total} of {session.length} minutes planned</span>}</p>

    {groups && <div className="session-groups">{groups.map(g => <div key={g.name} className="session-group"><strong>{g.name}</strong><span>{g.players.map(p => p.name).join(', ') || 'Nobody'}</span></div>)}
      {editing !== 'groups' && <button type="button" className="link-btn no-print" onClick={() => setEditing('groups')}>Change groups</button>}</div>}
    {editing === 'groups' && <GroupsEditor groups={groups} onCancel={() => setEditing(null)} onSave={next => change(() => setSessionGroups(teamId, session.id, next))} />}

    <ol className="session-blocks">{session.blocks.map((block, i) => <li key={block.id} className={`session-block phase-${block.phase}`}>
      <div className="session-block-time"><span>{times[i]}</span><small>{block.minutes} min</small></div>
      <div className="session-block-body">
        <p className="session-block-phase">{PHASE_NAMES[block.phase]}{block.chosen_by === 'coach' && <span className="status-pill muted-pill">Your choice</span>}</p>
        {block.drill
          ? <h4><button type="button" className="link-btn" onClick={() => setOpenDrill({ slug: block.drill.slug, variationId: block.versions[0]?.variation_id ?? null })}>{block.drill.title}</button></h4>
          : <h4 className="session-own">{block.title}</h4>}
        {groups && block.together && <p className="session-block-together">Everyone together</p>}
        {block.drill && (groups && !block.together
          ? <ul className="session-block-versions">{groups.map((g, j) => <li key={g.name}><strong>{g.name}:</strong> {versionLabel(block.versions[j])}</li>)}</ul>
          : <p className="session-block-version">{versionLabel(block.versions[0])}</p>)}
        {block.reasons.length > 0 && <p className="muted session-block-reasons">{block.reasons.join(' ')}</p>}
        {block.id === matchBlock && <MatchTeams match={session.match_teams} editing={editing === 'teams'} onEdit={() => setEditing('teams')} onCancel={() => setEditing(null)}
          onSave={teams => change(() => setMatchTeams(teamId, session.id, teams))}
          onSuggest={() => change(() => suggestMatchTeams(teamId, session.id), () => { setEditing(null); onMessage('Teams balanced again.') })} />}
        <BlockNote note={block.notes} onSave={notes => change(() => updateSessionBlock(teamId, session.id, block.id, { notes }), () => {})} />
        {editing === block.id
          ? <BlockEditor teamId={teamId} sessionId={session.id} block={block} groups={groups} onCancel={() => setEditing(null)}
            onSave={changes => change(() => updateSessionBlock(teamId, session.id, block.id, changes))}
            onRemove={() => change(() => deleteSessionBlock(teamId, session.id, block.id))} onMessage={onMessage} />
          : <button type="button" className="link-btn session-edit no-print" onClick={() => setEditing(block.id)}>Edit</button>}
      </div>
    </li>)}</ol>
    {editing === 'add'
      ? <AddBlock onCancel={() => setEditing(null)} onAdd={block => change(() => addSessionBlock(teamId, session.id, block))} />
      : <button type="button" className="link-btn no-print" onClick={() => setEditing('add')}>+ Add a block</button>}
    <Attendance session={session} players={players} onSave={rows => change(() => setSessionAttendance(teamId, session.id, rows), () => onMessage('Attendance saved.'))} />
    <SessionNotes notes={session.notes} onSave={notes => change(() => updateSession(teamId, session.id, { notes }), () => onMessage('Notes saved.'))} />
    {openDrill && <DrillDialog drill={openDrill} onMessage={onMessage} onClose={() => setOpenDrill(null)} />}
    <SessionReport session={session} teamName={teamName} drills={drills} />
  </Section>
}

// A note on one block, for afterwards: how it went.
function BlockNote({ note, onSave }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState(note)
  if (!open) return note
    ? <p className="session-block-note"><strong>Note:</strong> {note} <button type="button" className="link-btn no-print" onClick={() => setOpen(true)}>Edit note</button></p>
    : <button type="button" className="link-btn session-edit no-print" onClick={() => setOpen(true)}>Add note</button>
  return <form className="block-note-form no-print" onSubmit={event => { event.preventDefault(); onSave(text.trim()); setOpen(false) }}>
    <textarea rows={2} maxLength={1000} aria-label="Note on this block" placeholder="How did it go?" value={text} onChange={e => setText(e.target.value)} />
    <div className="inline-row"><button type="submit" className="primary-btn">Save note</button><button type="button" className="link-btn" onClick={() => { setText(note); setOpen(false) }}>Cancel</button></div>
  </form>
}

// Who is expected (before the session, for planning) and who came (afterwards).
function Attendance({ session, players, onSave }) {
  const rows = useMemo(() => {
    const byId = Object.fromEntries(session.attendance.map(r => [r.player_id, r]))
    const listed = players.filter(p => p.active || byId[p.id]).map(p => ({ id: p.id, name: p.name }))
    return listed.sort((a, b) => a.name.localeCompare(b.name)).map(p => ({ ...p, expected: byId[p.id]?.expected ?? false, attended: byId[p.id]?.attended ?? null }))
  }, [session.attendance, players])
  const [state, setState] = useState(() => Object.fromEntries(rows.map(r => [r.id, { expected: r.expected, attended: r.attended }])))
  const changed = rows.filter(r => state[r.id] && (state[r.id].expected !== r.expected || state[r.id].attended !== r.attended))
  const set = (id, patch) => setState(previous => ({ ...previous, [id]: { ...(previous[id] ?? { expected: false, attended: null }), ...patch } }))
  return <section className="session-attendance">
    <h3>Attendance</h3>
    <p className="muted hint">Tick who's expected before the session; it changes the groups and versions. Afterwards, tick who came.</p>
    <table><thead><tr><th>Player</th><th>Expected</th><th>Came</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.id}><td>{r.name}</td>
        <td><input type="checkbox" aria-label={`${r.name} expected`} checked={state[r.id]?.expected ?? false} onChange={e => set(r.id, { expected: e.target.checked })} /></td>
        <td><input type="checkbox" aria-label={`${r.name} came`} checked={state[r.id]?.attended === true} onChange={e => set(r.id, { attended: e.target.checked })} /></td>
      </tr>)}</tbody></table>
    <button type="button" className="primary-btn no-print" disabled={!changed.length} onClick={() => onSave(changed.map(r => ({ player_id: r.id, ...state[r.id] })))}>Save attendance</button>
  </section>
}

// The session's notes, for afterwards.
function SessionNotes({ notes, onSave }) {
  const [text, setText] = useState(notes)
  return <section className="session-notes">
    <h3>How did it go?</h3>
    <textarea rows={3} maxLength={2000} aria-label="Session notes" placeholder="What worked, what to change next time" value={text} onChange={e => setText(e.target.value)} />
    <button type="button" className="primary-btn no-print" disabled={text === notes} onClick={() => onSave(text.trim())}>Save notes</button>
  </section>
}

const OWN = '__own__'

// Change one block: its minutes, its drill (or your own activity), and its version for each group.
function BlockEditor({ teamId, sessionId, block, groups, onSave, onRemove, onCancel, onMessage }) {
  const [minutes, setMinutes] = useState(block.minutes)
  const [drill, setDrill] = useState(block.drill?.slug ?? OWN)
  const [title, setTitle] = useState(block.drill ? '' : block.title)
  const [versions, setVersions] = useState(block.versions.map(v => v?.variation_id ?? ''))
  const [options, setOptions] = useState(null)
  useEffect(() => {
    let live = true
    getBlockAlternatives(teamId, sessionId, block.id).then(value => { if (live) setOptions(value) }).catch(e => onMessage(errorMessage(e)))
    return () => { live = false }
  }, [teamId, sessionId, block.id, onMessage])
  const sameDrill = drill === (block.drill?.slug ?? OWN)
  const labels = groups && !block.together ? groups.map(g => g.name) : ['Version']

  const save = event => {
    event.preventDefault()
    const changes = { minutes: Number(minutes) }
    if (!sameDrill) Object.assign(changes, drill === OWN ? { drill: null, title } : { drill })
    else if (drill === OWN) changes.title = title
    else if (versions.some(Boolean)) changes.versions = versions.map(Number)
    onSave(changes)
  }
  return <form className="block-editor no-print" onSubmit={save}>
    <div className="block-editor-row">
      <label className="field">Minutes<input type="number" min={1} max={120} required value={minutes} onChange={e => setMinutes(e.target.value)} /></label>
      <label className="field">Drill<select value={drill} onChange={e => setDrill(e.target.value)}>
        {block.drill && <option value={block.drill.slug}>{block.drill.title} (current)</option>}
        {options && <optgroup label="Suggested for this part">{options.ranked.filter(o => o.slug !== block.drill?.slug).map(o => <option key={o.slug} value={o.slug}>{o.title}</option>)}</optgroup>}
        {options && <optgroup label="Any drill">{options.others.filter(o => o.slug !== block.drill?.slug).map(o => <option key={o.slug} value={o.slug}>{o.title} ({PHASE_NAMES[o.phase]})</option>)}</optgroup>}
        <option value={OWN}>Your own activity…</option>
      </select></label>
    </div>
    {drill === OWN && <label className="field">What you'll do<input required maxLength={160} value={title} onChange={e => setTitle(e.target.value)} /></label>}
    {drill !== OWN && sameDrill && block.drill_versions.length > 0 && <div className="block-editor-row">{labels.map((label, j) => <label key={label} className="field">{label}
      <select value={versions[j] ?? ''} onChange={e => setVersions(previous => previous.map((v, k) => (k === j ? e.target.value : v)))}>
        {block.drill_versions.map(v => <option key={v.id} value={v.id}>{versionLabel(v)} (levels {v.levels[0]}–{v.levels[1]})</option>)}
      </select></label>)}</div>}
    {!sameDrill && drill !== OWN && <p className="muted hint">Each group starts at the version that matches its level; you can change it after saving.</p>}
    <div className="inline-row">
      <button type="submit" className="primary-btn">Save</button>
      <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>
      <button type="button" className="link-btn danger-link" onClick={() => { if (window.confirm('Remove this block from the session?')) onRemove() }}>Remove block</button>
    </div>
  </form>
}

// Add your own activity to a part of the session; choose a drill for it afterwards with Edit if you like.
function AddBlock({ onAdd, onCancel }) {
  const [phase, setPhase] = useState('technical')
  const [minutes, setMinutes] = useState(10)
  const [title, setTitle] = useState('')
  return <form className="block-editor no-print" onSubmit={event => { event.preventDefault(); onAdd({ phase, minutes: Number(minutes), title }) }}>
    <div className="block-editor-row">
      <label className="field">Part of the session<select value={phase} onChange={e => setPhase(e.target.value)}>{Object.entries(PHASE_NAMES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label className="field">Minutes<input type="number" min={1} max={120} required value={minutes} onChange={e => setMinutes(e.target.value)} /></label>
    </div>
    <label className="field">What you'll do<input required maxLength={160} placeholder="For example: shooting practice from crosses" value={title} onChange={e => setTitle(e.target.value)} /></label>
    <div className="inline-row"><button type="submit" className="primary-btn">Add block</button><button type="button" className="link-btn" onClick={onCancel}>Cancel</button></div>
  </form>
}

// The two suggested teams for the full squad game, balanced on positions, age group and level. The coach can move
// players; teams they've changed keep their players when attendance changes, and newcomers join the smaller team.
export function MatchTeams({ match, editing, onEdit, onSave, onSuggest, onCancel }) {
  if (!match) return <p className="muted hint">Two teams are suggested here once at least two players are expected.</p>
  const suggest = () => { if (match.by !== 'coach' || window.confirm('Balance the teams again? Your changes to them are replaced.')) onSuggest() }
  return <div className="match-teams">
    <p className="session-block-phase">{match.by === 'coach' ? 'Your teams' : 'Suggested teams'}</p>
    {editing
      ? <TeamsEditor teams={match.teams} onSave={onSave} onCancel={onCancel} />
      : <div className="session-groups">{match.teams.map(t => <div key={t.name} className="session-group">
        <strong>{t.name}</strong>
        <span className="muted">{teamSummary(t)}</span>
        <ul className="match-team-players">{t.players.map(p => <li key={p.id}>{p.name}{p.position_label && <span className="muted"> · {p.position_label}</span>}</li>)}</ul>
      </div>)}</div>}
    {!editing && <div className="inline-row no-print">
      <button type="button" className="link-btn" onClick={onEdit}>Change teams</button>
      <button type="button" className="link-btn" onClick={suggest}>Balance again</button>
    </div>}
  </div>
}

function TeamsEditor({ teams, onSave, onCancel }) {
  const players = teams.flatMap((t, i) => t.players.map(p => ({ ...p, team: i })))
  const [choice, setChoice] = useState(() => Object.fromEntries(players.map(p => [p.id, p.team])))
  const save = event => { event.preventDefault(); onSave(teams.map((_, i) => players.filter(p => choice[p.id] === i).map(p => p.id))) }
  const sizes = teams.map((_, i) => players.filter(p => choice[p.id] === i).length)
  return <form className="block-editor no-print" onSubmit={save}>
    <div className="session-player-grid">{players.map(p => <label key={p.id} className="field">{p.name}{p.position_label ? ` (${p.position_label})` : ''}
      <select value={choice[p.id]} onChange={e => setChoice(c => ({ ...c, [p.id]: Number(e.target.value) }))}>{teams.map((t, i) => <option key={t.name} value={i}>{t.name}</option>)}</select></label>)}</div>
    <p className="muted hint">{teams.map((t, i) => `${t.name}: ${sizes[i]}`).join(' · ')}. Your teams stay as you set them; players who are expected later join the smaller team.</p>
    <div className="inline-row"><button type="submit" className="primary-btn">Save teams</button><button type="button" className="link-btn" onClick={onCancel}>Cancel</button></div>
  </form>
}

// Move players between level groups.
function GroupsEditor({ groups, onSave, onCancel }) {
  const players = groups.flatMap((g, i) => g.players.map(p => ({ ...p, group: i })))
  const [choice, setChoice] = useState(() => Object.fromEntries(players.map(p => [p.id, p.group])))
  const save = event => { event.preventDefault(); onSave(groups.map((_, i) => players.filter(p => choice[p.id] === i).map(p => p.id))) }
  return <form className="block-editor no-print" onSubmit={save}>
    <div className="session-player-grid">{players.map(p => <label key={p.id} className="field">{p.name}
      <select value={choice[p.id]} onChange={e => setChoice(c => ({ ...c, [p.id]: Number(e.target.value) }))}>{groups.map((g, i) => <option key={g.name} value={i}>{g.name}</option>)}</select></label>)}</div>
    <p className="muted hint">Blocks run in groups start again at each group's level.</p>
    <div className="inline-row"><button type="submit" className="primary-btn">Save groups</button><button type="button" className="link-btn" onClick={onCancel}>Cancel</button></div>
  </form>
}

const PARTS = Object.keys(PHASE_NAMES)
const draftFrom = template => ({ name: template?.name ?? '', length: String(template?.length ?? 60),
  minutes: Object.fromEntries(PARTS.map(p => [p, String((template ? template.minutes : DEFAULT_BREAKDOWNS[60])[p] ?? '')])) })

// The team's session templates: a length and the minutes for each part, shared by the team's coaches.
export function TemplatesView({ team, onBack, onMessage, initial = null }) {
  const [templates, setTemplates] = useState(initial)
  const [editing, setEditing] = useState(null)  // a template, or 'new'
  useEffect(() => {
    if (initial) return undefined
    let live = true
    getSessionTemplates(team.id).then(value => { if (live) setTemplates(value) }).catch(e => onMessage(errorMessage(e, 'Could not load the templates.')))
    return () => { live = false }
  }, [team.id, onMessage, initial])
  const saved = template => {
    setTemplates(list => [...(list ?? []).filter(t => t.id !== template.id), template].sort((a, b) => a.name.localeCompare(b.name)))
    setEditing(null)
  }
  const remove = async template => {
    const used = template.used ? ` The ${template.used === 1 ? 'session' : `${template.used} sessions`} planned with it stay as they are.` : ''
    if (!window.confirm(`Delete the template ${template.name}?${used}`)) return
    try {
      onMessage((await deleteSessionTemplate(team.id, template.id)).message)
      setTemplates(list => list.filter(t => t.id !== template.id))
    } catch (e) { onMessage(errorMessage(e)) }
  }
  return <Section title="Session templates" description={`Your own breakdowns of a session for ${team.name}, shared by the team's coaches`}>
    <button type="button" className="link-btn back-link" onClick={onBack}>← All sessions</button>
    {templates === null ? <p className="muted" role="status">Loading templates…</p> : <>
      {templates.length === 0 && editing === null && <p className="muted">No templates yet. A template sets a session's length and how long each part takes; leave out the parts you don't want.</p>}
      <ul className="session-list">{templates.map(t => <li key={t.id}>{editing?.id === t.id
        ? <TemplateEditor teamId={team.id} template={t} onSaved={saved} onCancel={() => setEditing(null)} onMessage={onMessage} />
        : <div className="session-card">
          <strong>{t.name}</strong>
          <span className="muted">{t.length} min · {breakdownText(t.minutes)}{t.used ? ` · used for ${t.used} ${t.used === 1 ? 'session' : 'sessions'}` : ''}</span>
          <span className="inline-row"><button type="button" className="link-btn" onClick={() => setEditing(t)}>Edit</button>
            <button type="button" className="link-btn danger-link" onClick={() => remove(t)}>Delete</button></span>
        </div>}</li>)}</ul>
      {editing === 'new' ? <TemplateEditor teamId={team.id} onSaved={saved} onCancel={() => setEditing(null)} onMessage={onMessage} />
        : <button type="button" className="primary-btn session-new" onClick={() => setEditing('new')}>New template</button>}
    </>}
  </Section>
}

function TemplateEditor({ teamId, template = null, onSaved, onCancel, onMessage }) {
  const [draft, setDraft] = useState(() => draftFrom(template))
  const [busy, setBusy] = useState(false)
  const problems = templateProblems(draft)
  const total = templateTotal(draft.minutes)
  const setPart = (part, value) => setDraft(d => ({ ...d, minutes: { ...d.minutes, [part]: value } }))
  async function submit(event) {
    event.preventDefault()
    if (problems.length) return
    const body = { name: draft.name.trim(), length: Number(draft.length),
      minutes: Object.fromEntries(PARTS.filter(p => Number(draft.minutes[p]) > 0).map(p => [p, Number(draft.minutes[p])])) }
    setBusy(true)
    try { onSaved(template ? await updateSessionTemplate(teamId, template.id, body) : await createSessionTemplate(teamId, body)) }
    catch (e) { onMessage(errorMessage(e, 'Could not save the template.')); setBusy(false) }
  }
  return <form className="session-form template-editor" onSubmit={submit}>
    <div className="session-form-row">
      <label className="field">Name<input required maxLength={60} value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} placeholder="For example Match prep" /></label>
      <label className="field">Length (minutes)<input type="number" inputMode="numeric" min={15} max={150} required value={draft.length} onChange={e => setDraft(d => ({ ...d, length: e.target.value }))} /></label>
    </div>
    <fieldset><legend>Minutes for each part <small className="muted">(leave a part empty to leave it out)</small></legend>
      <div className="template-parts">{PARTS.map(p => <label key={p} className="field">{PHASE_NAMES[p]}
        <input type="number" inputMode="numeric" min={0} max={90} placeholder="Not included" value={draft.minutes[p]} onChange={e => setPart(p, e.target.value)} /></label>)}</div>
      <p className={total === Number(draft.length) ? 'muted' : 'status-pill warn-pill'} role="status">{total} of {Number(draft.length) || 0} minutes</p>
    </fieldset>
    {template?.used > 0 && <p className="muted hint">Sessions already planned with this template keep their breakdown.</p>}
    {problems.length > 0 && <ul className="muted hint">{problems.map(p => <li key={p}>{p}</li>)}</ul>}
    <div className="inline-row">
      <button type="submit" className="primary-btn" disabled={busy || problems.length > 0}>{busy ? 'Saving…' : template ? 'Save changes' : 'Save template'}</button>
      <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>
    </div>
  </form>
}

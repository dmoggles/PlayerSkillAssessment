import { useEffect, useMemo, useState } from 'react'
import { addSessionBlock, createSession, deleteSession, deleteSessionBlock, errorMessage, getBlockAlternatives, getSession, getSessionFocus, getSessions, getSkillTags,
  regenerateSession, setSessionGroups, updateSessionBlock } from '../api'
import { DrillDialog } from '../DrillLibrary'
import { AREA_LABELS } from '../drillModel'
import { PHASE_NAMES, SESSION_LENGTHS, blockTimes, focusChip, sessionDate, splitSessions, versionLabel } from '../sessionModel'
import { Section } from './DashboardParts'

const tomorrow = () => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10) }

// Sessions: the team's training sessions, planning a new one, and one session's plan.
export default function SessionsArea({ team, period, players, onMessage }) {
  const [view, setView] = useState({ kind: 'list' })
  if (view.kind === 'new') return <NewSession team={team} period={period} players={players} onMessage={onMessage}
    onCancel={() => setView({ kind: 'list' })} onCreated={session => setView({ kind: 'session', id: session.id })} />
  if (view.kind === 'session') return <SessionView key={view.id} teamId={team.id} sessionId={view.id} onMessage={onMessage} onBack={() => setView({ kind: 'list' })} />
  return <SessionList team={team} period={period} onMessage={onMessage} onNew={() => setView({ kind: 'new' })} onOpen={id => setView({ kind: 'session', id })} />
}

function SessionList({ team, period, onNew, onOpen, onMessage }) {
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
    <span className="muted">{s.length} min · {s.focus.map(f => f.label).join(', ')} · {s.attended ? `${s.attended} came` : `${s.expected} expected`}{s.versions === 'groups' ? ' · level groups' : ''}</span>
  </button></li>
  return <Section title="Training sessions" description="Team sessions planned around what your players are working on">
    {period ? <button type="button" className="primary-btn session-new" onClick={onNew}>Plan a session</button>
      : <p className="muted">Add a period in Settings to plan sessions.</p>}
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
    return () => { live = false }
  }, [team.id, period.id])
  // Until the coach changes it, the focus is the top suggestion.
  const chosen = focus ?? (suggested?.length ? [suggested[0].tag_id] : [])
  const labels = Object.fromEntries([...tags.map(t => [t.id, t.label]), ...(suggested ?? []).map(s => [s.tag_id, s.label])])
  const toggleFocus = id => setFocus(chosen.includes(id) ? chosen.filter(t => t !== id) : [...chosen, id].slice(0, 3))
  const togglePlayer = id => setExpected(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next })

  async function submit(event) {
    event.preventDefault()
    if (!chosen.length) { onMessage('Choose at least one focus for the session.'); return }
    setBusy(true)
    try {
      onCreated(await createSession(team.id, { period_id: period.id, date, start_time: time || null, length: Number(length), focus_tags: chosen,
        player_ids: [...expected], versions, group_count: Number(groupCount) }))
    } catch (e) { onMessage(errorMessage(e, 'Could not plan the session.')); setBusy(false) }
  }

  return <Section title="Plan a session" description={`For ${team.name}, using ${period.label}'s ratings and priorities`}>
    <form className="session-form" onSubmit={submit}>
      <div className="session-form-row">
        <label className="field">Date<input type="date" required value={date} onChange={e => setDate(e.target.value)} /></label>
        <label className="field"><span>Start time <span className="muted">(optional)</span></span><input type="time" value={time} onChange={e => setTime(e.target.value)} /></label>
        <label className="field">Length<select value={length} onChange={e => setLength(e.target.value)}>{SESSION_LENGTHS.map(m => <option key={m} value={m}>{m} minutes</option>)}</select></label>
      </div>

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

function SessionView({ teamId, sessionId, onBack, onMessage }) {
  const [session, setSession] = useState(null)
  const [openDrill, setOpenDrill] = useState(null)
  const [editing, setEditing] = useState(null)  // a block id, 'groups' or 'add'
  useEffect(() => {
    let live = true
    getSession(teamId, sessionId).then(value => { if (live) setSession(value) }).catch(e => onMessage(errorMessage(e, 'Could not load the session.')))
    return () => { live = false }
  }, [teamId, sessionId, onMessage])
  if (!session) return <p className="muted" role="status">Loading session…</p>

  const times = blockTimes(session.blocks, session.start_time)
  const groups = session.versions === 'groups' ? session.groups : null
  const total = session.blocks.reduce((sum, b) => sum + b.minutes, 0)
  // Every change returns the whole session, which replaces the one shown.
  const change = async (call, done = () => setEditing(null)) => {
    try { setSession(await call()); done() } catch (e) { onMessage(errorMessage(e, 'Could not save the change.')) }
  }
  const remove = async () => {
    if (!window.confirm(`Delete ${session.title} on ${sessionDate(session.date)}? This can't be undone.`)) return
    try { onMessage((await deleteSession(teamId, session.id)).message); onBack() } catch (e) { onMessage(errorMessage(e)) }
  }
  const replan = () => { if (window.confirm('Plan the session again? Blocks you chose or added are kept.')) change(() => regenerateSession(teamId, session.id)) }

  return <Section className="session-view" title={session.title} description={`${sessionDate(session.date, session.start_time)} · ${session.length} minutes · ${session.expected} players expected`}>
    <div className="session-actions no-print">
      <button type="button" className="link-btn back-link" onClick={onBack}>← All sessions</button>
      <button type="button" onClick={replan}>Re-plan</button>
      <button type="button" onClick={() => window.print()}>Print</button>
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
    {openDrill && <DrillDialog drill={openDrill} onMessage={onMessage} onClose={() => setOpenDrill(null)} />}
  </Section>
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

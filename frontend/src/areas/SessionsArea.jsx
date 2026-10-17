import { useEffect, useMemo, useState } from 'react'
import { createSession, deleteSession, errorMessage, getSession, getSessionFocus, getSessions, getSkillTags } from '../api'
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
  useEffect(() => {
    let live = true
    getSession(teamId, sessionId).then(value => { if (live) setSession(value) }).catch(e => onMessage(errorMessage(e, 'Could not load the session.')))
    return () => { live = false }
  }, [teamId, sessionId, onMessage])
  if (!session) return <p className="muted" role="status">Loading session…</p>

  const times = blockTimes(session.blocks, session.start_time)
  const groups = session.versions === 'groups' ? session.groups : null
  const remove = async () => {
    if (!window.confirm(`Delete ${session.title} on ${sessionDate(session.date)}? This can't be undone.`)) return
    try { onMessage((await deleteSession(teamId, session.id)).message); onBack() } catch (e) { onMessage(errorMessage(e)) }
  }

  return <Section className="session-view" title={session.title} description={`${sessionDate(session.date, session.start_time)} · ${session.length} minutes · ${session.expected} players expected`}>
    <div className="session-actions no-print">
      <button type="button" className="link-btn back-link" onClick={onBack}>← All sessions</button>
      <button type="button" onClick={() => window.print()}>Print</button>
      <button type="button" className="danger-btn" onClick={remove}>Delete</button>
    </div>
    <p className="session-focus-pills">{session.focus.map(f => <span key={f.tag_id} className="status-pill info-pill">{f.label}</span>)}</p>

    {groups && <div className="session-groups">{groups.map(g => <div key={g.name} className="session-group"><strong>{g.name}</strong><span>{g.players.map(p => p.name).join(', ') || 'Nobody'}</span></div>)}</div>}

    <ol className="session-blocks">{session.blocks.map((block, i) => <li key={block.id} className={`session-block phase-${block.phase}`}>
      <div className="session-block-time"><span>{times[i]}</span><small>{block.minutes} min</small></div>
      <div className="session-block-body">
        <p className="session-block-phase">{PHASE_NAMES[block.phase]}</p>
        {block.drill
          ? <h4><button type="button" className="link-btn" onClick={() => setOpenDrill({ slug: block.drill.slug, variationId: block.versions[0]?.variation_id ?? null })}>{block.drill.title}</button></h4>
          : <h4 className="session-own">{block.title}</h4>}
        {groups && block.together && <p className="session-block-together">Everyone together</p>}
        {block.drill && (groups && !block.together
          ? <ul className="session-block-versions">{groups.map((g, j) => <li key={g.name}><strong>{g.name}:</strong> {versionLabel(block.versions[j])}</li>)}</ul>
          : <p className="session-block-version">{versionLabel(block.versions[0])}</p>)}
        {block.reasons.length > 0 && <p className="muted session-block-reasons">{block.reasons.join(' ')}</p>}
      </div>
    </li>)}</ol>
    {openDrill && <DrillDialog drill={openDrill} onMessage={onMessage} onClose={() => setOpenDrill(null)} />}
  </Section>
}

import { useEffect, useState } from 'react'
import { assignPractice, errorMessage, getPlayerPractice, getPracticeLibrary, issuePracticeLink, revokePracticeLink, unassignPractice } from '../api'
import { CHECKS } from './checks'
import ScenarioPlayer from './ScenarioPlayer'
import { CONCEPT_LABELS } from './practiceModel'

const day = value => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const weekLabel = value => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

// Player Data → Practice: what the player has been set, their link, and how their practice is going. Practice,
// not assessment: it's the player's own tries, and none of it changes the coach's ratings.
export default function PracticePanel({ teamId, player, onMessage }) {
  const [state, setState] = useState(null)
  const [library, setLibrary] = useState(null)
  const [issued, setIssued] = useState(null)
  const [preview, setPreview] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let live = true
    Promise.all([getPlayerPractice(teamId, player.id), getPracticeLibrary()])
      .then(([value, lib]) => { if (live) { setState(value); setLibrary(lib) } })
      .catch(e => { if (live) { setFailed(true); onMessage(errorMessage(e, 'Could not load practice.')) } })
    return () => { live = false }
  }, [teamId, player.id, onMessage])
  if (failed) return <p className="error" role="alert">Could not load practice. Try again in a moment.</p>
  if (!state || !library) return <p className="muted" role="status">Loading practice…</p>
  const act = async (call, done) => { try { setState(await call()); done?.() } catch (e) { onMessage(errorMessage(e)) } }
  const byId = Object.fromEntries(library.scenarios.map(s => [s.id, s]))
  if (preview) return <div className="practice-preview">
    <button type="button" className="link-btn back-link" onClick={() => setPreview(null)}>← Back to {player.name}'s practice</button>
    <h3>{preview.title}</h3>
    <p className="muted hint">Preview: your answers aren't saved.</p>
    <ScenarioPlayer key={preview.id} scenario={preview} onExit={() => setPreview(null)} />
  </div>

  return <div className="practice-panel">
    <p className="practice-note"><strong>Practice, not assessment.</strong> These are {player.name}'s own tries at practice scenarios on their phone. They don't change your ratings.</p>

    <section>
      <h3>{player.name}'s link</h3>
      {issued
        ? <IssuedLink url={issued.url} name={player.name} expires={issued.expires_at} onDone={() => setIssued(null)} />
        : state.link?.active
          ? <p className="muted">Given {day(state.link.issued_at)}, works until {day(state.link.expires_at)}. {state.link.opened_at ? `Opened ${day(state.link.opened_at)}.` : 'Not opened yet.'}</p>
          : <p className="muted">{state.link ? 'The link has expired.' : `${player.name} doesn't have a link yet.`} They need one to practise: no account, just the link.</p>}
      {!issued && <div className="inline-row">
        {player.active && <button type="button" className="secondary-btn" onClick={async () => {
          if (state.link?.active && !window.confirm('Make a new link? The one you gave before stops working.')) return
          try { const made = await issuePracticeLink(teamId, player.id); setIssued(made); setState(await getPlayerPractice(teamId, player.id)) } catch (e) { onMessage(errorMessage(e)) }
        }}>{state.link?.active ? 'New link' : 'Give a link'}</button>}
        {state.link && <button type="button" className="link-btn danger-link" onClick={() => {
          if (window.confirm('Stop the link working now?')) act(() => revokePracticeLink(teamId, player.id), () => onMessage('Link stopped.'))
        }}>Stop the link</button>}
      </div>}
    </section>

    <section>
      <h3>Set practice</h3>
      {player.active ? <AssignForm library={library} onAssign={body => act(() => assignPractice(teamId, player.id, body), () => onMessage('Practice set.'))} />
        : <p className="muted">Restore {player.name} to set them practice.</p>}
      {state.assignments.length === 0 ? <p className="muted">Nothing set yet.</p>
        : <ul className="practice-scenarios">{state.assignments.map(a => {
          const counted = a.random_count ? state.random_progress[a.id] : { done: a.scenario_ids.filter(id => state.progress[id]?.done).length, of: a.scenario_ids.length }
          return <li key={a.id}>
            <div><strong>{a.label}</strong>
              <small className="muted">{counted.done} of {counted.of} done{a.due_on ? ` · by ${day(a.due_on)}` : ''}</small>
              <small>{a.scenario_ids.map(id => byId[id] && <button key={id} type="button" className="link-btn" onClick={() => setPreview(byId[id])}>
                {byId[id].title}{state.progress[id]?.done ? ` ${'★'.repeat(state.progress[id].stars)}` : ''}</button>)}</small>
            </div>
            <button type="button" className="link-btn danger-link" onClick={() => act(() => unassignPractice(teamId, player.id, a.id))}>Remove</button>
          </li>
        })}</ul>}
    </section>

    <PracticeResults summary={state.summary} />
  </div>
}

// A stage of a topic, or one scenario, with an optional date to do it by.
export function AssignForm({ library, onAssign }) {
  const [choice, setChoice] = useState('')
  const [due, setDue] = useState('')
  const [count, setCount] = useState('5')
  const [format, setFormat] = useState(library.formats?.[0] ?? '7v7')
  const [kind, a, b] = choice.split(':')
  const submit = event => {
    event.preventDefault()
    const target = kind === 'scenario' ? { scenario_id: a } : { topic: a, stage: Number(b), ...(kind === 'random' ? { random_count: Number(count), format } : {}) }
    onAssign({ ...target, due_on: due || null })
    setChoice(''); setDue('')
  }
  return <form className="practice-assign" onSubmit={submit}>
    <label className="field">Practice
      <select required value={choice} onChange={e => setChoice(e.target.value)}>
        <option value="">Choose a stage or a scenario</option>
        {library.topics.map(topic => <optgroup key={topic.id} label={topic.label}>
          {topic.stages.filter(st => library.scenarios.some(s => s.topic === topic.id && s.stage === st.stage)).map(st => <option key={st.stage} value={`stage:${topic.id}:${st.stage}`}>Stage {st.stage}: {st.label} (all)</option>)}
          {topic.stages.filter(st => st.random).map(st => <option key={`r${st.stage}`} value={`random:${topic.id}:${st.stage}`}>Stage {st.stage}: {st.label} (random situations)</option>)}
          {library.scenarios.filter(s => s.topic === topic.id).map(s => <option key={s.id} value={`scenario:${s.id}`}>{`  Stage ${s.stage} · ${s.title}`}</option>)}
        </optgroup>)}
      </select></label>
    {kind === 'random' && <>
      <label className="field practice-small">How many<select value={count} onChange={e => setCount(e.target.value)}>{['3', '5', '10'].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
      <label className="field practice-small">Pitch<select value={format} onChange={e => setFormat(e.target.value)}>{(library.formats ?? ['7v7']).map(f => <option key={f} value={f}>{f}</option>)}</select></label>
    </>}
    <label className="field">Do by (optional)<input type="date" value={due} onChange={e => setDue(e.target.value)} /></label>
    <button type="submit" className="primary-btn" disabled={!choice}>Set</button>
  </form>
}

// How the player's practice is going: tries each week, how they do on each concept, and what they miss most.
export function PracticeResults({ summary }) {
  if (!summary.attempts) return <section><h3>How it's going</h3><p className="muted">No practice yet. Results show here once they've had a go.</p></section>
  const most = Math.max(1, ...summary.weeks.map(w => w.attempts))
  return <section className="practice-results">
    <h3>How it's going</h3>
    <div className="practice-weeks" role="img" aria-label={`Tries each week: ${summary.weeks.map(w => `${weekLabel(w.week_of)} ${w.attempts}`).join(', ')}`}>
      {summary.weeks.map(w => <div key={w.week_of} className="practice-week">
        <span className="practice-week-average">{w.average ?? ''}</span>
        <span className="practice-week-bar" style={{ height: `${Math.round((w.attempts / most) * 100)}%` }} />
        <small>{weekLabel(w.week_of)}</small>
      </div>)}
    </div>
    <p className="muted hint">Bars are tries each week; the number above is the average points on a first try.</p>
    {summary.missed.length > 0 && <>
      <h4>Missed most lately</h4>
      <ul className="practice-missed">{summary.missed.map(m => <li key={m.check}>{CHECKS[m.check]?.label ?? m.check} <span className="muted">({m.count} {m.count === 1 ? 'time' : 'times'})</span></li>)}</ul>
    </>}
    <table className="data-table">
      <thead><tr><th scope="col">Concept</th><th scope="col" className="num">First tries</th><th scope="col" className="num">Average points</th></tr></thead>
      <tbody>{summary.concepts.map(c => <tr key={c.concept}><th scope="row">{CONCEPT_LABELS[c.concept] ?? c.concept}</th><td className="num">{c.tries}</td><td className="num">{c.average}</td></tr>)}</tbody>
    </table>
  </section>
}

function IssuedLink({ url, name, expires, onDone }) {
  const [copied, setCopied] = useState(false)
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'
  return <div className="invite-link" role="status">
    <p><strong>Send {name} this link.</strong> It opens their practice on a phone, with no account, until {day(expires)}.</p>
    <div className="issued-link">
      <input readOnly aria-label={`Practice link for ${name}`} value={url} onFocus={e => e.target.select()} />
      <button className="primary-btn" type="button" onClick={() => navigator.clipboard?.writeText(url).then(() => setCopied(true)).catch(() => {})}>{copied ? 'Copied' : 'Copy link'}</button>
      {canShare && <button className="secondary-btn" type="button" onClick={() => navigator.share({ title: 'Your practice', url }).catch(() => {})}>Share…</button>}
    </div>
    <p className="muted">It won't be shown again. Anyone with it can practise as {name}, so send it to them or a parent only.</p>
    <button type="button" className="link-btn" onClick={onDone}>Done</button>
  </div>
}

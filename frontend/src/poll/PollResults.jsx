import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { clearPollAnswers, errorMessage, getPollResults, removePollRespondent, restoreSession } from '../api'
import PracticePitch from '../practice/PracticePitch'
import { ELSEWHERE, groupOf, respondentName, tally } from './pollModel'

const frameOf = s => ({ ball: s.ball, team: s.team, opponents: s.opponents })

// A poll's answers, for a site admin: every situation on its pitch with everyone's answers as dots, coloured by the
// reference spot each is nearest, and counts. Pick one respondent to pick out their answers.
export default function PollResults() {
  const { pollId } = useParams()
  const [results, setResults] = useState(null)
  const [error, setError] = useState('')
  const [signedOut, setSignedOut] = useState(false)
  const [who, setWho] = useState('')
  const [showSpots, setShowSpots] = useState(true)
  const load = useCallback(() => getPollResults(pollId).then(setResults).catch(e => {
    if (e?.response?.status === 401) setSignedOut(true)
    else setError(errorMessage(e, 'Could not load the results.'))
  }), [pollId])
  useEffect(() => { restoreSession().catch(() => null).finally(load) }, [load])

  const remove = async () => {
    const person = results.respondents.find(r => r.id === who)
    if (!window.confirm(`Take out all of ${respondentName(person)}'s answers? This can't be undone.`)) return
    try { await removePollRespondent(pollId, who); setWho(''); load() } catch (e) { setError(errorMessage(e, 'Could not take those answers out.')) }
  }

  const clearAll = async () => {
    if (!window.confirm(`Clear all ${results.answers.length} answers from everyone? This can't be undone.`)) return
    try { await clearPollAnswers(pollId); setWho(''); load() } catch (e) { setError(errorMessage(e, 'Could not clear the answers.')) }
  }

  if (signedOut) return <div className="page public-page"><section className="public-card"><h1>Poll results</h1>
    <p>Sign in as a site admin, then open this link again.</p><Link className="primary-btn" to="/sign-in">Sign in</Link></section></div>
  if (error) return <div className="page public-page"><section className="public-card"><h1>Poll results</h1><p role="alert">{error}</p></section></div>
  if (!results) return <div className="page public-page"><p className="muted" role="status">Loading results…</p></div>

  const link = `${window.location.origin}/poll/${results.id}`
  return <div className="page poll-results">
    <header className="poll-results-head">
      <h1>Results: {results.title}</h1>
      <p className="muted">{results.context}.</p>
      <p className="muted">{results.respondents.length} {results.respondents.length === 1 ? 'person has' : 'people have'} answered. Link to share: <a href={link}>{link}</a></p>
      <div className="poll-results-controls">
        <label className="field">Pick out
          <select value={who} onChange={e => setWho(e.target.value)}>
            <option value="">Everyone</option>
            {results.respondents.map(r => <option key={r.id} value={r.id}>{respondentName(r)} ({r.answered} of {results.scenarios.length})</option>)}
          </select></label>
        <label className="checkbox"><input type="checkbox" checked={showSpots} onChange={e => setShowSpots(e.target.checked)} /> Show the spots answers are grouped by</label>
        <button type="button" className="secondary-btn" onClick={load}>Refresh</button>
        {who && <button type="button" className="danger-btn" onClick={remove}>Take out their answers</button>}
        {!who && results.answers.length > 0 && <button type="button" className="danger-btn" onClick={clearAll}>Clear all answers</button>}
      </div>
    </header>
    <div className="poll-results-grid">
      {results.scenarios.map((s, i) => {
        const answers = results.answers.filter(a => a.scenario_id === s.id)
        const group = a => groupOf(a, s.references)
        const colour = label => label === ELSEWHERE ? 'group-other' : `group-${s.references.findIndex(r => r.label === label)}`
        const start = s.team.find(p => p.id === s.controlled)
        const marks = [{ key: 'start', x: start.x, y: start.y, r: 1.35, className: 'poll-start', title: 'Where the player started' },
          ...answers.map(a => {
            const person = results.respondents.find(r => r.id === a.respondent)
            const picked = who === a.respondent
            return { key: a.respondent, x: a.x, y: a.y, r: picked ? 1.1 : 0.75, title: `${respondentName(person)}: ${group(a)}`,
              className: `${colour(group(a))}${who && !picked ? ' faded' : ''}${picked ? ' picked' : ''}` }
          })]
        // Picked-out answers go last, so they're drawn on top.
        marks.sort((a, b) => (a.className?.includes('picked') ? 1 : 0) - (b.className?.includes('picked') ? 1 : 0))
        return <section key={s.id} className="poll-result">
          <h2>{i + 1}. {s.title}</h2>
          <p className="muted">{s.prompt} {results.question}</p>
          <PracticePitch scenario={s} controlled={s.controlled} shown={frameOf(s)} position={null} disabled marks={marks}
            spots={showSpots ? s.references.map((r, n) => ({ ...r, className: `group-${n}` })) : []} />
          <ul className="poll-tally">{tally(answers, s.references).map(({ label, n }) => <li key={label}>
            <span className={`poll-swatch ${colour(label)}`} aria-hidden="true" /> {label}: <strong>{n}</strong>
            {answers.length > 0 && <span className="muted"> ({Math.round((100 * n) / answers.length)}%)</span>}</li>)}</ul>
          {answers.length === 0 && <p className="muted">No answers yet.</p>}
        </section>
      })}
    </div>
  </div>
}

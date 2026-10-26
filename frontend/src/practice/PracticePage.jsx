import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage, getMyPractice, savePracticeAttempt } from '../api'
import { MadeWith } from '../brand'
import ScenarioPlayer from './ScenarioPlayer'

const dueText = due => `By ${new Date(`${due}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}`

// A player's practice, opened from the link their coach gave them: no account, no timers, no scores against
// anyone else. Each try is saved for the coach to see.
export default function PracticePage() {
  const { token } = useParams()
  const [practice, setPractice] = useState(null)
  const [error, setError] = useState('')
  const [playing, setPlaying] = useState(null)
  const [notice, setNotice] = useState('')
  const load = useCallback(() => getMyPractice(token).then(setPractice).catch(e => setError(errorMessage(e, 'This link is unavailable.'))), [token])
  useEffect(() => { load() }, [load])
  const save = attempt => savePracticeAttempt(token, attempt).then(() => setNotice('')).catch(e => setNotice(errorMessage(e, 'That try couldn\'t be saved. Check your connection.')))

  return <div className="page public-page practice-page">
    {error ? <section className="public-card"><h1>Practice</h1><p role="alert">{error}</p></section>
      : !practice ? <p className="muted" role="status">Loading your practice…</p>
        : playing ? <section className="public-card practice-card">
          <button type="button" className="link-btn back-link" onClick={() => { setPlaying(null); load() }}>← My practice</button>
          <h1>{playing.title}</h1>
          <ScenarioPlayer key={playing.id} scenario={playing} onAttempt={save} onExit={() => { setPlaying(null); load() }} />
          {notice && <p className="error" role="alert">{notice}</p>}
        </section>
          : <PracticeList practice={practice} onPlay={setPlaying} />}
    <MadeWith />
  </div>
}

export function PracticeList({ practice, onPlay }) {
  return <section className="public-card practice-card">
    <h1>Hi {practice.name}</h1>
    <p>Here's the practice your coach set you. Drag your player to where you'd stand, then press <strong>Check</strong>.</p>
    {practice.assignments.length === 0 && <p className="muted">Nothing to practise yet. Your coach will add some.</p>}
    {practice.assignments.map(a => {
      const done = a.scenarios.filter(s => s.progress.done).length
      return <div key={a.id} className="practice-assignment">
        <h2>{a.label}</h2>
        <p className="muted">{done} of {a.scenarios.length} done{a.due_on ? ` · ${dueText(a.due_on)}` : ''}</p>
        <progress max={a.scenarios.length} value={done} aria-label={`${done} of ${a.scenarios.length} done`} />
        <ul className="practice-scenarios">{a.scenarios.map(s => <li key={s.id}>
          <div><strong>{s.title}</strong>
            {s.progress.done
              ? <small className="practice-mini-stars" aria-label={`${s.progress.stars} of 3 stars`}>{'★'.repeat(s.progress.stars)}<span>{'★'.repeat(3 - s.progress.stars)}</span></small>
              : <small className="muted">{s.frames.length === 1 ? 'One step' : `${s.frames.length} steps`}</small>}</div>
          <button type="button" className={s.progress.done ? 'secondary-btn' : 'primary-btn'} onClick={() => onPlay(s)}>{s.progress.done ? 'Play again' : 'Start'}</button>
        </li>)}</ul>
      </div>
    })}
  </section>
}

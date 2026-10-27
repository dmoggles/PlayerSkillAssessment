import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage, getPoll, savePollAnswer } from '../api'
import { MadeWith } from '../brand'
import PracticePitch from '../practice/PracticePitch'
import { startPosition } from '../practice/practiceModel'
import { respondentFor } from './pollModel'

const frameOf = s => ({ ball: s.ball, team: s.team, opponents: s.opponents })

// A coaching poll, opened from its link: no account and no scoring. Each situation is frozen in time, and the
// respondent puts the highlighted player in the ideal position for that moment (not where they'd run to from there); every answer saves as they go, and coming back shows them again to change.
export default function PollPage() {
  const { pollId } = useParams()
  const respondent = useMemo(() => respondentFor(pollId), [pollId])
  const [poll, setPoll] = useState(null)
  const [error, setError] = useState('')
  const [answers, setAnswers] = useState({})
  const [name, setName] = useState('')
  const [index, setIndex] = useState(null)  // the situation on screen; null for the start, scenarios.length for the end
  const [position, setPosition] = useState(null)
  const [lines, setLines] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [averages, setAverages] = useState(null)  // everyone's average answers, once this respondent has answered all

  useEffect(() => {
    getPoll(pollId, respondent).then(value => {
      setPoll(value); setAnswers(value.answers); setName(value.name ?? ''); setAverages(value.averages)
      // Coming back after finishing: straight to how everyone's answered so far.
      if (value.averages) setIndex(value.scenarios.length)
    }).catch(e => setError(errorMessage(e, 'This poll isn\'t available.')))
  }, [pollId, respondent])

  const open = i => {
    setIndex(i)
    setNotice('')
    if (i < poll.scenarios.length) { const s = poll.scenarios[i]; setPosition(answers[s.id] ?? startPosition(s, s)) }
  }
  const save = async () => {
    const s = poll.scenarios[index]
    setSaving(true)
    try {
      await savePollAnswer(pollId, s.id, { respondent, name: name.trim() || null, x: round(position.x), y: round(position.y) })
      setAnswers(previous => ({ ...previous, [s.id]: position }))
      // Every situation answered now: fetch the averages so far, to show at the end.
      if (poll.scenarios.every(other => other.id === s.id || answers[other.id])) {
        const fresh = await getPoll(pollId, respondent).catch(() => null)
        if (fresh) setAverages(fresh.averages)
      }
      open(index + 1)
    } catch (e) { setNotice(errorMessage(e, 'That answer couldn\'t be saved. Check your connection and try again.')) } finally { setSaving(false) }
  }

  if (error) return <Shell><section className="public-card"><h1>Poll</h1><p role="alert">{error}</p></section></Shell>
  if (!poll) return <Shell><p className="muted" role="status">Loading the poll…</p></Shell>
  const total = poll.scenarios.length, done = poll.scenarios.filter(s => answers[s.id]).length
  const steps = <ol className="poll-steps" aria-label="Situations">{poll.scenarios.map((s, i) => <li key={s.id}>
    <button type="button" className={`poll-step${answers[s.id] ? ' answered' : ''}${i === index ? ' current' : ''}`} aria-current={i === index ? 'step' : undefined}
      aria-label={`Situation ${i + 1}${answers[s.id] ? ', answered' : ''}`} onClick={() => open(i)}>{i + 1}</button></li>)}</ol>

  if (index === null) return <Shell><section className="public-card practice-card">
    <h1>{poll.title}</h1>
    <p>{poll.intro}</p>
    <label className="field">Your name or team (optional)
      <input value={name} maxLength={60} onChange={e => setName(e.target.value)} autoComplete="name" /></label>
    {done > 0 && <p className="muted">You've answered {done} of {total}. You can change any of them.</p>}
    <div className="practice-actions">
      <button type="button" className="primary-btn" onClick={() => open(done > 0 && done < total ? poll.scenarios.findIndex(s => !answers[s.id]) : 0)}>{done === 0 ? 'Start' : done < total ? 'Carry on' : 'Look again'}</button>
    </div>
  </section></Shell>

  if (index >= total) return <Shell><section className="public-card practice-card" role="status">
    <h1>Thank you</h1>
    <p>{done === total ? `All ${total} answers are saved.` : `${done} of ${total} answers are saved. Tap a number to answer the rest.`} You can come back to this link and change any of them.</p>
    {steps}
    {averages && <>
      <h2 className="poll-so-far">How everyone's answered so far</h2>
      <p className="muted">The average position from everyone's answers, next to yours. Come back to this link to see it update.</p>
      {poll.scenarios.map((s, i) => {
        const average = averages[s.id], mine = answers[s.id]
        return <div key={s.id} className="poll-average">
          <h3>{i + 1}. {s.title}</h3>
          <PracticePitch scenario={s} shown={frameOf(s)} position={null} disabled
            marks={mine ? [{ key: 'mine', x: mine.x, y: mine.y, r: 1.1, className: 'poll-mine', title: 'Your answer' }] : []}
            spots={average ? [{ label: 'Average', x: average.x, y: average.y, className: 'poll-average-spot' }] : []} />
          <p className="poll-legend"><span className="poll-swatch poll-mine" aria-hidden="true" /> Your answer
            <span className="poll-ring" aria-hidden="true" /> Average of {average?.count ?? 0} {average?.count === 1 ? 'answer' : 'answers'}
            <button type="button" className="link-btn" onClick={() => open(i)}>Change mine</button></p>
        </div>
      })}
    </>}
  </section></Shell>

  const s = poll.scenarios[index]
  return <Shell><section className="public-card practice-card">
    <button type="button" className="link-btn back-link" onClick={() => setIndex(null)}>← {poll.title}</button>
    {steps}
    <div className="practice-head">
      <p className="practice-step">Situation {index + 1} of {total} · {poll.context}</p>
      <p>{s.prompt}</p>
      <p className="practice-prompt">{poll.question}</p>
    </div>
    <PracticePitch scenario={s} shown={frameOf(s)} position={position} onMove={setPosition} lines={lines} youText="?" />
    <label className="checkbox practice-lines"><input type="checkbox" checked={lines} onChange={e => setLines(e.target.checked)} /> Show lines to goal</label>
    <p className="muted hint">Drag the player marked ? to the ideal spot. How far it is from where they're standing doesn't matter. If they're already there, just save.</p>
    <div className="practice-actions">
      <button type="button" className="primary-btn" disabled={saving} onClick={save}>{index === total - 1 ? 'Save and finish' : 'Save and next'}</button>
      {index > 0 && <button type="button" className="secondary-btn" onClick={() => open(index - 1)}>Back</button>}
    </div>
    {notice && <p className="error" role="alert">{notice}</p>}
  </section></Shell>
}

function Shell({ children }) {
  return <div className="page public-page practice-page">{children}<MadeWith /></div>
}

const round = n => Math.round(n * 100) / 100

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage, getSelfLinkInfo, submitSelfAssessment } from './api'
import SkillForm from './SkillForm'
import { MadeWith } from './brand'
import { sectionsFor } from './matrix'

export default function PlayerPage() {
  const { token } = useParams()
  const [info, setInfo] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [position, setPosition] = useState('outfield')
  const [ratings, setRatings] = useState({})
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    getSelfLinkInfo(token)
      .then(link => { setInfo(link); setMatrix(link.matrix); setStatus('ready') })
      .catch(e => { setError(errorMessage(e, 'This link is unavailable.')); setStatus('error') })
  }, [token])

  async function submit(event) {
    event.preventDefault()
    setStatus('submitting')
    try {
      const skills = sectionsFor(matrix, position).flatMap(section => section.skills)
      await submitSelfAssessment(token, { position, ratings: skills.map(skill => ({ skill_id: skill.id, score: typeof ratings[skill.id] === 'number' ? ratings[skill.id] : null })) })
      setStatus('done')
    } catch (e) {
      setError(errorMessage(e, 'Could not save your assessment.'))
      setStatus('ready')
    }
  }

  if (status === 'loading') return <div className="page public-page"><p className="loading">Loading self-assessment…</p></div>
  if (status === 'error') return <div className="page public-page"><h1>Self-assessment</h1><section className="public-card"><p role="alert" className="error">{error}</p></section><MadeWith /></div>
  if (status === 'done') return <div className="page public-page"><p className="eyebrow">{info.team}</p><h1>Thank you, {info.player}</h1><section className="public-card"><p>Your assessment has been saved.</p></section><MadeWith /></div>
  return <div className="page public-page"><header><p className="eyebrow">{info.team}</p><h1>Self-assessment</h1><p className="subtitle">{info.player} · {info.period}</p></header>
    <form onSubmit={submit}>
      <label className="field">Position<select value={position} onChange={e => { setPosition(e.target.value); setRatings({}) }}><option value="outfield">Outfield</option><option value="goalkeeper">Goalkeeper</option></select></label>
      <p className="notice">Rate each skill from 1 to 5, or choose “I don’t know”.</p>
      <SkillForm matrix={matrix} position={position} ratings={ratings} onChange={(id, score) => setRatings(previous => ({ ...previous, [id]: score }))} allowUnknown />
      {error && <p className="error" role="alert">{error}</p>}
      <button className="submit-btn" disabled={status === 'submitting'}>{status === 'submitting' ? 'Saving…' : 'Submit assessment'}</button>
    </form>
    <MadeWith />
  </div>
}

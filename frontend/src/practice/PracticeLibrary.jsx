import { useEffect, useState } from 'react'
import { errorMessage, getPracticeLibrary } from '../api'
import { AGE_GROUPS } from '../dashboardModel'
import ScenarioPlayer from './ScenarioPlayer'
import { CONCEPT_LABELS, libraryStages } from './practiceModel'

// Practice scenarios for coaches: every topic and stage, to preview as a player would. Previews aren't saved.
export default function PracticeLibrary({ ageGroup = null, onMessage }) {
  const [library, setLibrary] = useState(null)
  const [age, setAge] = useState(ageGroup == null ? '' : String(ageGroup))
  const [playing, setPlaying] = useState(null)
  useEffect(() => {
    let live = true
    getPracticeLibrary().then(value => { if (live) setLibrary(value) }).catch(e => onMessage(errorMessage(e, 'Could not load the practice scenarios.')))
    return () => { live = false }
  }, [onMessage])
  if (!library) return <p className="muted" role="status">Loading scenarios…</p>
  if (playing) return <div className="practice-preview">
    <button type="button" className="link-btn back-link" onClick={() => setPlaying(null)}>← All scenarios</button>
    <h3>{playing.title}</h3>
    <p className="muted hint">Preview: your answers aren't saved.</p>
    <ScenarioPlayer key={playing.id} scenario={playing} onExit={() => setPlaying(null)} />
  </div>

  const topics = libraryStages(library, age === '' ? null : Number(age))
  return <div className="practice-library">
    <label className="field practice-age">Age group
      <select value={age} onChange={e => setAge(e.target.value)}>
        <option value="">All age groups</option>
        {AGE_GROUPS.map(a => <option key={a} value={a}>U{a}</option>)}
      </select></label>
    {topics.length === 0 && <p className="muted">No scenarios for this age group yet.</p>}
    {topics.map(topic => <section key={topic.id} className="practice-topic">
      <h3>{topic.label}</h3>
      {topic.stages.map(stage => <div key={stage.stage} className="practice-stage">
        <h4>Stage {stage.stage}: {stage.label}</h4>
        <ul className="practice-scenarios">{stage.scenarios.map(s => <li key={s.id}>
          <div>
            <strong>{s.title}</strong>
            <small className="muted">{s.format} · U{s.ages[0]}–U{s.ages[1]} · {s.frames.length === 1 ? 'one step' : `${s.frames.length} steps`} · {s.concepts.map(c => CONCEPT_LABELS[c] ?? c).join(', ')}</small>
          </div>
          <button type="button" className="secondary-btn" onClick={() => setPlaying(s)}>Preview</button>
        </li>)}</ul>
      </div>)}
    </section>)}
  </div>
}

// The library in Settings: what's there, and a button to open it.
export function PracticeLibrarySummary({ onOpen }) {
  return <div className="matrix-card">
    <p>Game situations players solve on a pitch: drag their player to where they should stand, and see why. Start with off-ball defending.</p>
    <button className="secondary-btn" type="button" onClick={onOpen}>Browse scenarios</button>
  </div>
}

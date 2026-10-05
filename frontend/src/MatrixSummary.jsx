import { useEffect, useState } from 'react'
import { getMatrixDraft } from './api'
import { changeCount } from './matrixEditorModel'

// Settings card: which matrix the team uses, whether a draft is in progress, and the way into the editor.
export default function MatrixSummary({ teamId, onEdit }) {
  const [state, setState] = useState(null)
  useEffect(() => {
    let live = true
    getMatrixDraft(teamId).then(value => { if (live) setState(value) }).catch(() => { if (live) setState(false) })
    return () => { live = false }
  }, [teamId])
  if (state === null) return <p className="muted">Loading…</p>
  if (state === false) return <p className="muted">Could not load the skill matrix.</p>
  const pending = changeCount(state.changes)
  return <div className="matrix-card">
    <p>Uses <strong>{state.current.name}</strong>, version {state.current.version}{state.current.own ? '' : ' (the shared starter template)'}.</p>
    {state.draft && <p className="muted">Draft in progress: {pending} {pending === 1 ? 'change' : 'changes'} not yet published.</p>}
    <p className="muted">Changing skills makes ratings harder to compare across periods. Adding skills is safe.</p>
    <button type="button" onClick={onEdit}>{state.draft ? 'Continue editing' : 'Edit skill matrix'}</button>
  </div>
}

import { useState } from 'react'
import { errorMessage, generateSquadPlans } from './api'

// Generates plans for every active player with saved priorities in one go. Coaches' own choices are kept.
export default function SquadPlans({ teamId, periodId, onGenerated }) {
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const run = async () => {
    if (replace && !window.confirm('Regenerate every player\'s plan? Drills you chose yourself are kept; the rest may change.')) return
    setBusy(true); setError('')
    try { setResult(await generateSquadPlans(teamId, periodId, !replace)); onGenerated() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const skippedFor = reason => (result?.skipped ?? []).filter(s => s.reason === reason).map(s => s.player)
  return <div className="squad-plans">
    <div className="squad-plans-row">
      <span><strong>Squad plans</strong> <span className="muted">for every player with saved priorities</span></span>
      <label className="checkbox"><input type="checkbox" checked={replace} onChange={e => setReplace(e.target.checked)} /> Replace existing plans</label>
      <button type="button" onClick={run} disabled={busy}>{busy ? 'Generating…' : 'Generate plans for the squad'}</button>
    </div>
    {result && <p className="muted" role="status">
      {result.generated.length ? `Generated ${result.generated.length}: ${result.generated.join(', ')}.` : 'No plans generated.'}
      {skippedFor('already has a plan').length > 0 && ` Already had a plan: ${skippedFor('already has a plan').join(', ')}.`}
      {skippedFor('no saved priorities').length > 0 && ` No saved priorities yet: ${skippedFor('no saved priorities').join(', ')}.`}
    </p>}
    {error && <p className="error" role="alert">{error}</p>}
  </div>
}

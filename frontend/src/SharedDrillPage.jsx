import { useCallback, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getSharedDrill } from './api'
import { DrillDetail } from './DrillLibrary'
import { MadeWith } from './brand'

// Public, read-only drill opened from a coach's share link: the drill in full, with nothing that changes anything.
export default function SharedDrillPage() {
  const { token } = useParams()
  const [error, setError] = useState('')
  const loadDrill = useCallback(() => getSharedDrill(token), [token])
  return <div className="page public-page shared-drill-page">
    {error ? <section className="public-card"><h1>Drill</h1><p role="alert">{error}</p></section>
      : <section className="public-card"><DrillDetail slug={token} loadDrill={loadDrill} onBack={null} onOpen={() => {}} onVoted={() => {}} onMessage={setError} /></section>}
    <MadeWith />
  </div>
}
